"""Nastroje z Reddita na historii: wprost i odwrotnie (kontrariańsko).

Dane: archiwum Arctic Shift (publiczne API z kopią Reddita; Pushshift jest zamknięty dla zwykłych użytkowników od 2023 r.,
Reddit nie daje historii, X/Twitter nie ma darmowego dostępu do archiwum). Liczymy dzienne liczby wpisów z danym słowem w tytule.

A. Uwaga o kraju: r/worldnews i r/geopolitics, wpisy z nazwą kraju w tytule. Skok = co najmniej 3× mediana z 28 dni.
   Wprost: skok zapowiada wydarzenie w tym kraju w 60 dni. Odwrotnie: po skoku wydarzenie jest RZADSZE niż zwykle,
   więc skok może osłabiać alarm. Sprawdzone samo, jako bramka dla alarmów ręcznego indeksu i razem z silnym impulsem 48 h.
B. Giełda: r/wallstreetbets, dzienne wzmianki o aktywach (ropa, złoto, zbrojeniówka, Chiny, Tajwan) i stosunek „puts” do „calls”.
   Wprost: po skoku wzmianek kurs rośnie. Odwrotnie: spada. Kurs ETF po 30 dniach od dnia po skoku, wobec zwykłego dnia.

    python -m analizator.reddit_test --db historia_gkg.db --pierwotne pierwotne_historia.db --cache reddit.db
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

API = "https://arctic-shift.photon-reddit.com/api/posts/search/aggregate"
UA = {"User-Agent": "analizator-ruchow-firm/0.10 (https://github.com/mat3usz-mk/analizator-ruchow-firm)"}
ASSETS = {"ropa (XLE)": ("oil", "XLE"), "złoto (GLD)": ("gold", "GLD"), "zbrojeniówka (ITA)": ("Lockheed", "ITA"),
          "Chiny (FXI)": ("China", "FXI"), "Tajwan (EWT)": ("Taiwan", "EWT")}


def _con(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS counts (sub TEXT, q TEXT, rok INTEGER, dane TEXT, PRIMARY KEY (sub, q, rok))")
    return con


def _fetch(sub: str, q: str, after: date, before: date, tries: int = 2):
    params = urllib.parse.urlencode({"aggregate": "created_utc", "frequency": "day", "subreddit": sub, "title": q,
                                     "after": after.isoformat(), "before": before.isoformat()})
    for i in range(tries):
        try:
            data = json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}?{params}", headers=UA), timeout=90).read())["data"]
            time.sleep(1.0)
            return data
        except Exception as e:
            print(f"  [reddit] {sub} {q} {after}..{before}: {e}", flush=True)
            time.sleep(20 * (i + 1))
    return None


def daily_counts(con, sub: str, q: str, y0: int, y1: int) -> dict[date, int]:
    out: dict[date, int] = {}
    for y in range(y0, y1 + 1):
        row = con.execute("SELECT dane FROM counts WHERE sub=? AND q=? AND rok=?", (sub, q, y)).fetchone()
        if row:
            data = json.loads(row[0])
        else:
            end = min(date(y, 12, 31), date.today())
            data = _fetch(sub, q, date(y, 1, 1), end + timedelta(days=1))
            if data is None:  # serwer nie zdążył: kwartałami
                parts = [_fetch(sub, q, date(y, m, 1), min(date(y + (m == 10), (m + 3 - 1) % 12 + 1, 1), end + timedelta(days=1)))
                         for m in (1, 4, 7, 10) if date(y, m, 1) <= end]
                data = None if any(x is None for x in parts) else [p for x in parts for p in x]
            if data is None:
                continue
            con.execute("INSERT OR REPLACE INTO counts VALUES (?,?,?,?)", (sub, q, y, json.dumps(data)))
            con.commit()
        for p in data or []:
            # znacznik dnia bywa przesunięty o strefę (23:00 dnia poprzedniego), więc zaokrąglamy do najbliższej doby
            t = datetime.fromisoformat(p["created_utc"].replace("Z", "+00:00")) + timedelta(hours=12)
            out[t.date()] = out.get(t.date(), 0) + int(p["count"])
    return out


def spikes(s: dict[date, int], ratio: float = 3.0, min_n: int = 5) -> set[date]:
    days = sorted(s)
    out = set()
    for i in range(28, len(days)):
        hist = [s.get(days[i] - timedelta(days=k), 0) for k in range(1, 29)]
        med = statistics.median(hist)
        if s[days[i]] >= min_n and s[days[i]] >= ratio * max(med, 1):
            out.add(days[i])
    return out


def _eps(hits: dict[str, set[date]], gap: int = 7) -> list[tuple[str, date]]:
    eps = []
    for c, ds in hits.items():
        last = None
        for d in sorted(ds):
            if last is None or (d - last).days > gap:
                eps.append((c, d))
            last = d
    return eps


def _pct(x):
    return "brak" if x is None else f"{x:.0%}"


def _pp(x):
    return "brak" if x is None else f"{x * 100:+.1f}%".replace(".", ",")


def market_test(con, y0: int, y1: int, horizon: int = 30, n_perm: int = 1000) -> list[dict]:
    from .rynki import Series, prices
    rows = []
    puts, calls = daily_counts(con, "wallstreetbets", "puts", y0, y1), daily_counts(con, "wallstreetbets", "calls", y0, y1)
    items = [(k, *v) for k, v in ASSETS.items()] + [("strach na WSB: puts ≥ 2× calls (SPY)", None, "SPY")]
    rnd = random.Random(3)
    for label, q, etf in items:
        p = prices(etf, date(y0, 1, 1))
        if not p:
            continue
        s = Series(p)
        if q:
            sp = spikes(daily_counts(con, "wallstreetbets", q, y0, y1))
        else:
            sp = {d for d in puts if puts[d] >= 5 and puts[d] >= 2 * max(calls.get(d, 0), 1)}
        sp = sorted(d for d in sp if date(y0, 3, 1) <= d <= date.today() - timedelta(days=horizon + 2))
        ev = [r for d in sp if (r := s.ret(d + timedelta(days=1), horizon)) is not None]
        days = [date(y0, 3, 1) + timedelta(days=i) for i in range((date.today() - timedelta(days=horizon + 2) - date(y0, 3, 1)).days)]
        allr = [r for d in days if (r := s.ret(d + timedelta(days=1), horizon)) is not None]
        mean = lambda xs: sum(xs) / len(xs) if xs else None
        diff = (mean(ev) - mean(allr)) if ev and allr else None
        # permutacja: tyle samo losowych dni; p dla „wprost” (średnia wyższa) i „odwrotnie” (niższa)
        sims = []
        for _ in range(n_perm if ev else 0):
            smp = rnd.sample(allr, len(ev)) if len(allr) >= len(ev) else allr
            sims.append(mean(smp) - mean(allr))
        rows.append({"aktywo": label, "skokow": len(sp), "po_skoku": mean(ev), "zwykle": mean(allr), "roznica": diff,
                     "w_gore": sum(r > 0 for r in ev) / len(ev) if ev else None, "w_gore_zwykle": sum(r > 0 for r in allr) / len(allr) if allr else None,
                     "p_wprost": sum(x >= diff for x in sims) / len(sims) if sims else None,
                     "p_odwrotnie": sum(x <= diff for x in sims) / len(sims) if sims else None})
        print(f"  rynek {label}: {rows[-1]}", flush=True)
    return rows


def main(argv=None) -> int:
    from . import store
    from .backtest import evaluate as bt_eval, load_events, replay
    from .impuls import daily_impulse, episodes
    from .permutacja import run as perm
    from .score import extract_signals
    from .signals import COUNTRIES
    from .slady import evaluate as sl_eval, gate, traces
    from .ucz import _counts
    ap = argparse.ArgumentParser(prog="analizator.reddit_test")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", nargs="*", default=[])
    ap.add_argument("--cache", default="reddit.db")
    ap.add_argument("--od", type=int, default=2019)
    ap.add_argument("--out", default="raporty/reddit-wyniki.md")
    ap.add_argument("--suby", default="worldnews")
    a = ap.parse_args(argv)
    con = _con(a.cache)
    y1 = date.today().year
    # A. uwaga o kraju
    from .backtest import load_events as _le
    # kraje z wydarzeniami od 2019 r. (archiwum jest wolne, więc bez krajów, w których nie ma czego przewidywać)
    wanted = {e["kraj"] for f in ("wydarzenia_2015_2024.csv", "wydarzenia.csv") for e in _le(f) if e["data"].year >= a.od}
    att: dict[str, dict[str, set[date]]] = {sub: {} for sub in a.suby.split(",")}
    for c, names in COUNTRIES.items():
        if c not in wanted:
            continue
        name = re.sub(r"\\[bB]|[()?\\]", "", names[0])
        for sub in att:
            att[sub][c] = spikes(daily_counts(con, sub, name, a.od, y1))
        print(f"  {c}: " + ", ".join(f"{sub} {len(att[sub][c])}" for sub in att) + " skoków", flush=True)
    t0 = time.time()
    sig = extract_signals(store.load(store.connect(a.db)) + [x for p in a.pierwotne if os.path.exists(p) for x in store.load(store.connect(p))])
    tr = traces(sig)
    print(f"sygnały: {len(sig)} ({time.time() - t0:.0f} s)", flush=True)
    d = date.fromisoformat
    periods = [("2019–2024", load_events("wydarzenia_2015_2024.csv"), d("2019-03-01"), d("2024-12-31")),
               ("2025–2026 (test)", load_events("wydarzenia.csv"), d("2025-03-01"), date.today())]
    L = [f"# Reddit: nastroje wprost i odwrotnie ({date.today().isoformat()})", "",
         "Dane: archiwum Arctic Shift (kopia Reddita), dzienne liczby wpisów ze słowem w tytule. Skok: co najmniej 3× mediana z 28 dni. "
         "Trafny alarm: wydarzenie w tym kraju w ciągu 60 dni. p (przesunięcie): odsetek losowań z losowymi datami wydarzeń, w których wynik "
         "był co najmniej tak dobry; dla „odwrotnie” liczy się, czy wynik jest wyraźnie GORSZY od losowego (p odwrotnie małe).", "",
         "## A. Uwaga o kraju (r/worldnews; kraje z wydarzeniami od 2019 r.)", "", "Skok sam jako alarm:", "",
         "| subreddit | okres | epizodów | precyzja | przewaga nad losowym | p wprost | p odwrotnie |", "|---|---|---|---|---|---|---|"]
    gates = []
    for label, evs, s, e in periods:
        for sub, hits in att.items():
            h = {c: {x for x in ds if s <= x <= e} for c, ds in hits.items()}
            ev = sl_eval(h, tr, evs, s, e)
            eps = [(c, x) for c, x in _eps(h) if x <= e - timedelta(days=60)]
            r = perm(eps, [(x["kraj"], x["data"]) for x in evs if s <= x["data"] <= e], s, e, 1000)
            lift = "brak" if ev["lift"] is None else f"{ev['lift']:.1f}×"
            # p odwrotnie: odsetek losowań z wynikiem nie lepszym niż rzeczywisty (mały = Reddit wskazuje miejsca BEZ wydarzeń)
            L.append(f"| r/{sub} | {label} | {ev['ocenionych']} | {_pct(ev['precyzja'])} | {lift} | {r['przesuniecie']['p']:.3f} | "
                     f"{r['przesuniecie']['p_niski']:.3f} |")
            print(f"  {label} {sub}: {ev} perm {r}", flush=True)
        # bramki dla ręcznego indeksu i impulsy
        idx = replay([x for x in sig if s - timedelta(days=200) <= x["date"] <= e], s, e)
        both = {c: set().union(*(att[sub].get(c, set()) for sub in att)) for c in COUNTRIES}
        base = _counts(bt_eval(idx, evs))
        keep_if = _counts(bt_eval(gate(idx, both, days=14), evs))
        # odwrotnie: alarm zostaje tylko wtedy, gdy na Reddicie NIE było skoku w 14 dniach
        drop = {}
        for (c, t), v in idx.items():
            hot = any(t - timedelta(days=i) in both.get(c, ()) for i in range(14))
            drop[(c, t)] = min(v, 39.9) if hot else v
        keep_not = _counts(bt_eval(drop, evs))
        imp = daily_impulse([x for x in sig if s - timedelta(days=40) <= x["date"] <= e], s, e)
        ie = [(c, x) for c, x in episodes(imp, 10.0) if x <= e - timedelta(days=60)]
        hot_i = [(c, x) for c, x in ie if any(x - timedelta(days=i) in both.get(c, ()) for i in range(3))]
        cold_i = [(c, x) for c, x in ie if (c, x) not in set(hot_i)]
        ev_list = [(x["kraj"], x["data"]) for x in evs if s <= x["data"] <= e]
        gates.append((label, base, keep_if, keep_not, [(n, perm(eps_, ev_list, s, e, 1000)) for n, eps_ in
                                                       (("impuls ≥ 10 (wszystkie)", ie), ("impuls ≥ 10 i skok na Reddicie w 3 dniach", hot_i),
                                                        ("impuls ≥ 10 bez skoku na Reddicie", cold_i))]))
    L += ["", "Bramka dla alarmów ręcznego indeksu (próg 40, wydarzenie w 60 dni):", "",
          "| okres | wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |", "|---|---|---|---|---|---|---|"]
    for label, base, kif, knot, _ in gates:
        for n, ev in (("bez Reddita", base), ("wprost: alarm tylko przy skoku na Reddicie w 14 dniach", kif),
                      ("odwrotnie: alarm tylko BEZ skoku na Reddicie w 14 dniach", knot)):
            L.append(f"| {label} | {n} | {_pct(ev['hit_rate'])} | {_pct(ev['hit_rate_fresh'])} | {_pct(ev['precision'])} | {ev['prawdziwe']} | {ev['falszywe']} |")
    L += ["", "Silny impuls 48 h a Reddit:", "", "| okres | wariant | impulsów | trafnych | p (przesunięcie) |", "|---|---|---|---|---|"]
    for label, *_, ip in gates:
        for n, r in ip:
            L.append(f"| {label} | {n} | {r['alarmow']} | {r['trafnych']} ({r['trafnych'] / max(r['alarmow'], 1):.0%}) | {r['przesuniecie']['p']:.3f} |")
    # B. giełda
    mk = market_test(con, a.od, y1)
    L += ["", "## B. Giełda (r/wallstreetbets)", "", "Kurs ETF 30 dni od dnia po skoku wzmianek, wobec zwykłego dnia. p wprost: czy po skoku kurs "
          "rośnie bardziej niż zwykle; p odwrotnie: czy spada bardziej niż zwykle (1000 losowań tylu samo zwykłych dni).", "",
          "| wzmianki | skoków | kurs po skoku | zwykle | różnica | w górę po skoku | w górę zwykle | p wprost | p odwrotnie |", "|---|---|---|---|---|---|---|---|---|"]
    for r in mk:
        L.append(f"| {r['aktywo']} | {r['skokow']} | {_pp(r['po_skoku'])} | {_pp(r['zwykle'])} | {_pp(r['roznica'])} | {_pct(r['w_gore'])} | "
                 f"{_pct(r['w_gore_zwykle'])} | {'brak' if r['p_wprost'] is None else format(r['p_wprost'], '.3f')} | "
                 f"{'brak' if r['p_odwrotnie'] is None else format(r['p_odwrotnie'], '.3f')} |")
    L += ["", "Uwaga: kolejne dni na giełdzie nie są niezależne (okna 30 dni nachodzą na siebie), więc p dla giełdy jest raczej zbyt optymistyczne. "
          "X/Twitter pominięty: brak darmowego dostępu do archiwum (API płatne, Nitter wyłączony). Reddit bez archiwum Arctic Shift nie daje historii "
          "(Pushshift zamknięty, PullPush blokuje automaty). To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna."]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
