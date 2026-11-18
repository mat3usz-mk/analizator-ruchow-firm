"""Plany firm z dokumentów dla regulatora (SEC): czy firmy „mówią” o kraju inaczej, zanim coś się stanie.

Pełnotekstowa wyszukiwarka SEC (od 2001 r.) daje liczbę dokumentów z danymi słowami w danym miesiącu. Dla każdego kraju liczymy:
  wzmianki       raporty 10-K/10-Q/20-F z nazwą kraju (tło, do normalizacji),
  sankcje        te same raporty z nazwą kraju i słowem „sanctions” (opis ryzyk),
  geopolityka    z nazwą kraju i słowem „geopolitical”,
  zawieszenie    raporty bieżące 8-K/6-K z nazwą kraju i „suspend” (zawieszenie działalności, dostaw),
  wycofanie      8-K/6-K z nazwą kraju i „wind down” (wygaszanie, sprzedaż, wyjście).
Sygnał: udział dokumentów o ryzyku wśród dokumentów o kraju (albo liczba 8-K) skacze wyraźnie ponad normę z 12 miesięcy.
Sprawdzenie: czy w ciągu 90 dni od końca takiego miesiąca w kraju nastąpiło wydarzenie, wobec zwykłego miesiąca, z permutacją.

    python -m analizator.sec_slady --od 2018-01 --cache sec_slady.db --out raporty/sec-slady-wyniki.md
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import sqlite3
import threading
import statistics
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

SERIES = {"wzmianki": ("10-K,10-Q,20-F", '"{n}"'), "sankcje": ("10-K,10-Q,20-F", '"{n}" sanctions'),
          "geopolityka": ("10-K,10-Q,20-F", '"{n}" geopolitical'), "zawieszenie": ("8-K,6-K", '"{n}" suspend'),
          "wycofanie": ("8-K,6-K", '"{n}" "wind down"')}


def _months(y0: int, m0: int, end: date):
    y, m = y0, m0
    while date(y, m, 1) <= end:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        yield date(y, m, 1), nxt - timedelta(days=1)
        y, m = nxt.year, nxt.month


_LOCK = threading.Lock()
_LAST = [0.0]


def _pace(per_sec: float = 8.0) -> None:
    """Wspólny ogranicznik dla wszystkich wątków: SEC pozwala na 10 zapytań na sekundę, trzymamy się 8."""
    with _LOCK:
        wait = _LAST[0] + 1 / per_sec - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.monotonic()


def fetch_remote(ua: str, name: str, key: str, start: date, end: date) -> int | None:
    forms, q = SERIES[key]
    params = urllib.parse.urlencode({"q": q.format(n=name), "forms": forms, "dateRange": "custom",
                                     "startdt": start.isoformat(), "enddt": end.isoformat()})
    for i in range(3):
        _pace()
        try:
            data = json.loads(urllib.request.urlopen(urllib.request.Request(
                f"https://efts.sec.gov/LATEST/search-index?{params}", headers={"User-Agent": ua}), timeout=60).read())
            return int(data.get("hits", {}).get("total", {}).get("value", 0))
        except Exception as e:
            print(f"  [sec] {name} {key} {start:%Y-%m}: {e}", flush=True)
            time.sleep(5 * (i + 1))
    return None


def fetch(con, ua: str, country: str, name: str, key: str, start: date, end: date) -> int | None:
    row = con.execute("SELECT n FROM liczby WHERE kraj=? AND seria=? AND miesiac=?", (country, key, start.isoformat())).fetchone()
    if row:
        return row[0]
    n = fetch_remote(ua, name, key, start, end)
    if n is not None:
        con.execute("INSERT OR REPLACE INTO liczby VALUES (?,?,?,?)", (country, key, start.isoformat(), n))
    return n


def prefetch(con, ua: str, jobs: list[tuple[str, str, str, date, date]], workers: int = 6, deadline: float | None = None) -> int:
    """Pobiera brakujące liczby równolegle (kilka wątków, wspólny limit tempa); zapis do bazy tylko w głównym wątku."""
    have = {(k, s_, m) for k, s_, m in con.execute("SELECT kraj, seria, miesiac FROM liczby")}
    todo = [j for j in jobs if (j[0], j[2], j[3].isoformat()) not in have]
    print(f"  do pobrania {len(todo)} z {len(jobs)}", flush=True)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for i in range(0, len(todo), 400):
            if deadline and time.monotonic() > deadline:
                print("  koniec czasu na pobieranie, test na tym, co jest", flush=True)
                break
            batch = todo[i:i + 400]
            for (c, name, k, s, e), n in zip(batch, ex.map(lambda j: fetch_remote(ua, j[1], j[2], j[3], j[4]), batch)):
                if n is not None:
                    con.execute("INSERT OR REPLACE INTO liczby VALUES (?,?,?,?)", (c, k, s.isoformat(), n))
                    done += 1
            con.commit()
            print(f"  pobrano {done} z {len(todo)}", flush=True)
    return done


def flags(ser: dict[date, float], z_thr: float = 2.0, min_ratio: float = 1.5) -> set[date]:
    """Miesiące, w których wartość jest ≥ 1,5× mediany z 12 poprzednich i ≥ 2 odchylenia (odporne) powyżej niej."""
    ms = sorted(ser)
    out = set()
    for i in range(12, len(ms)):
        hist = [ser[m] for m in ms[i - 12:i]]
        med = statistics.median(hist)
        mad = statistics.median(abs(h - med) for h in hist) or max(med * 0.1, 1e-6)
        v = ser[ms[i]]
        if v > 0 and v >= min_ratio * max(med, 1e-6) and (v - med) / (1.4826 * mad) >= z_thr:
            out.add(ms[i])
    return out


def evaluate(fl: dict[str, set[date]], events: list[dict], countries: list[str], start: date, end: date,
             horizon: int = 90, n_perm: int = 1000, seed: int = 5) -> dict:
    """Alarm = koniec miesiąca z flagą; trafny, gdy wydarzenie w kraju w ciągu `horizon` dni."""
    def month_end(m):
        return date(m.year + (m.month == 12), m.month % 12 + 1, 1) - timedelta(days=1)
    evs = [(e["kraj"], e["data"]) for e in events if e["kraj"] in countries and start <= e["data"] <= end + timedelta(days=horizon)]
    def score(ev_list):
        byc = {}
        for c, d in ev_list:
            byc.setdefault(c, []).append(d)
        hit = tot = 0
        for c, ms in fl.items():
            for m in ms:
                t = month_end(m)
                if not (start <= t <= end):
                    continue
                tot += 1
                hit += any(t < d <= t + timedelta(days=horizon) for d in byc.get(c, ()))
        return hit, tot
    hit, tot = score(evs)
    # stopa bazowa: każdy kraj-miesiąc
    byc = {}
    for c, d in evs:
        byc.setdefault(c, []).append(d)
    b_tot = b_pos = 0
    for c in countries:
        for m, _ in _months(start.year, start.month, end):
            t = month_end(m)
            b_tot += 1
            b_pos += any(t < d <= t + timedelta(days=horizon) for d in byc.get(c, ()))
    base = b_pos / b_tot if b_tot else None
    rnd = random.Random(seed)
    span = (end + timedelta(days=horizon) - start).days
    sims = sorted(score([(c, start + timedelta(days=rnd.randrange(span))) for c, _ in evs])[0] for _ in range(n_perm))
    caught = sum(1 for c, d in evs if d <= end and any(month_end(m) < d <= month_end(m) + timedelta(days=horizon) for m in fl.get(c, ())))
    prec = hit / tot if tot else None
    return {"alarmow": tot, "trafnych": hit, "precyzja": prec, "baza": base, "lift": prec / base if prec is not None and base else None,
            "p": sum(1 for x in sims if x >= hit) / n_perm, "wydarzen": sum(1 for _, d in evs if d <= end), "zlapane": caught}


def main(argv=None) -> int:
    from .backtest import load_events
    from .signals import COUNTRIES
    from .sources import sec_user_agent
    ap = argparse.ArgumentParser(prog="analizator.sec_slady")
    ap.add_argument("--od", default="2018-01")
    ap.add_argument("--cache", default="sec_slady.db")
    ap.add_argument("--out", default="raporty/sec-slady-wyniki.md")
    ap.add_argument("--minut", type=float, default=0, help="limit czasu na pobieranie (0 = bez limitu)")
    a = ap.parse_args(argv)
    ua = sec_user_agent()
    if not ua:
        print("brak SEC_USER_AGENT")
        return 2
    con = sqlite3.connect(a.cache)
    con.execute("CREATE TABLE IF NOT EXISTS liczby (kraj TEXT, seria TEXT, miesiac TEXT, n INTEGER, PRIMARY KEY (kraj, seria, miesiac))")
    y0, m0 = map(int, a.od.split("-"))
    last = date.today().replace(day=1) - timedelta(days=1)
    names = {c: re.sub(r"\\[bB]|[()?\\]", "", ns[0]) for c, ns in COUNTRIES.items()}
    months = list(_months(y0, m0, last))
    prefetch(con, ua, [(c, names[c], k, s, e) for c in names for s, e in months for k in SERIES],
             deadline=time.monotonic() + a.minut * 60 if a.minut else None)
    data: dict[str, dict[str, dict[date, int]]] = {c: {k: {} for k in SERIES} for c in names}
    for c, k, m, n in con.execute("SELECT kraj, seria, miesiac, n FROM liczby"):
        if c in data and k in data[c] and date.fromisoformat(m) >= date(y0, m0, 1):
            data[c][k][date.fromisoformat(m)] = n
    for c in data:
        print(f"  {c} ({names[c]}): " + ", ".join(f"{k} {sum(v.values())}" for k, v in data[c].items()), flush=True)
    # sygnały
    variants = {}
    for k in ("sankcje", "geopolityka"):
        variants[f"udział „{k}” wśród raportów o kraju"] = {
            c: flags({m: data[c][k].get(m, 0) / max(data[c]["wzmianki"].get(m, 0), 1) for m in data[c]["wzmianki"]
                      if data[c]["wzmianki"].get(m, 0) >= 20}) for c in data}
    for k in ("zawieszenie", "wycofanie"):
        variants[f"liczba 8-K „{k}”"] = {c: flags({m: float(v) for m, v in data[c][k].items()}) for c in data}
    d = date.fromisoformat
    periods = [("2019–2024", load_events("wydarzenia_2015_2024.csv"), d("2019-01-01"), d("2024-12-31")),
               ("2025–2026 (test)", load_events("wydarzenia.csv"), d("2025-01-01"), last)]
    L = [f"# Plany firm w dokumentach SEC: test historyczny ({date.today().isoformat()})", "",
         "Pełnotekstowa wyszukiwarka SEC, miesięczne liczby dokumentów. Sygnał: miesiąc, w którym wartość jest co najmniej 1,5× mediany "
         "z 12 poprzednich miesięcy i 2 odchylenia ponad nią. Trafny sygnał: wydarzenie w tym kraju w ciągu 90 dni od końca miesiąca. "
         "p: odsetek losowań z losowymi datami wydarzeń, w których trafnych było co najmniej tyle samo.", "",
         "| sygnał | okres | sygnałów | trafnych | precyzja | przewaga nad losowym | p | wydarzeń złapanych |", "|---|---|---|---|---|---|---|---|"]
    for label, evs, s, e in periods:
        for name, fl in variants.items():
            r = evaluate(fl, evs, list(data), s, e)
            print(f"  {label} {name}: {r}", flush=True)
            lift = "brak" if r["lift"] is None else f"{r['lift']:.1f}×"
            prec = "brak" if r["precyzja"] is None else f"{r['precyzja']:.0%}"
            L.append(f"| {name} | {label} | {r['alarmow']} | {r['trafnych']} | {prec} | {lift} | {r['p']:.3f} | {r['zlapane']} z {r['wydarzen']} |")
    # studium przypadku: Rosja i Ukraina 2021-2022
    L += ["", "## Studium przypadku: Rosja przed lutym 2022", "",
          "| miesiąc | raporty o Rosji | z „sanctions” | udział | z „geopolitical” | udział | 8-K „suspend” | 8-K „wind down” | flaga |", "|---|---|---|---|---|---|---|---|---|"]
    ru = data.get("RU", {})
    flagged = {m for v in variants.values() for m in v.get("RU", set())}
    for s_, _ in _months(2021, 1, date(2022, 6, 30)):
        w = ru.get("wzmianki", {}).get(s_, 0)
        sk, g = ru.get("sankcje", {}).get(s_, 0), ru.get("geopolityka", {}).get(s_, 0)
        L.append(f"| {s_:%Y-%m} | {w} | {sk} | {sk / max(w, 1):.0%} | {g} | {g / max(w, 1):.0%} | {ru.get('zawieszenie', {}).get(s_, 0)} | "
                 f"{ru.get('wycofanie', {}).get(s_, 0)} | {'tak' if s_ in flagged else ''} |")
    L += ["", "Pominięte źródła: oferty pracy (brak darmowej historii; serwisy z ofertami nie udostępniają archiwum), patenty i znaki "
          "towarowe (dane są, ale bez związku z krajem i z opóźnieniem publikacji 18 miesięcy), rejestry spółek-córek (w SEC tylko raz "
          "w roku, w załączniku do 10-K). To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna."]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
