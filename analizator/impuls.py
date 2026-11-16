"""Test historyczny impulsu: czy nagły przyrost nowych sygnałów w 48 h (względem tła kraju z 4 tygodni) wyprzedza wydarzenia.

Dla każdego dnia i kraju liczy impuls tak samo jak raport (score._impulse), z danych dostępnych do tego dnia.
Alarm impulsu = impuls >= próg i co najmniej 2 nowe sprawy. Kolejne alarmy w odstępie do 7 dni to jeden epizod.

    python -m analizator.impuls --db historia_gkg.db --pierwotne pierwotne_historia.db --out raporty/impuls-wyniki.md
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import date, timedelta

from .score import IMPULSE_BASE_DAYS, IMPULSE_DAYS, _impulse

THRESHOLDS = [2.5, 4.0, 6.0, 10.0]
LEADS = [3, 7, 14, 30]


def daily_impulse(signals: list[dict], start: date, end: date) -> dict[str, dict[date, tuple[float, int]]]:
    """(kraj -> dzień -> (impuls, liczba nowych spraw)). Sprawa liczy się od dnia, w którym pojawiła się pierwszy raz."""
    first: dict[str, dict[str, tuple]] = defaultdict(dict)
    for s in signals:
        if s["weight"] <= 0.05 or s.get("reactive") or s.get("negated"):
            continue
        st = s.get("story") or s.get("url") or s["title"]
        old = first[s["country"]].get(st)
        if old is None or s["date"] < old[0]:
            first[s["country"]][st] = (s["date"], s["weight"], s["category"], None)
    out: dict[str, dict[date, tuple[float, int]]] = {}
    span = IMPULSE_BASE_DAYS + IMPULSE_DAYS
    for c, stories in first.items():
        by_day: dict[date, list] = defaultdict(list)
        for k, v in stories.items():
            by_day[v[0]].append((k, v))
        days = sorted(d for d in by_day if start - timedelta(days=span) <= d <= end)
        if not days:
            continue
        res = {}
        t = start
        while t <= end:
            win = {k: v for d in (t - timedelta(days=i) for i in range(span)) for k, v in by_day.get(d, [])}
            if win:
                z, info = _impulse(win, t)
                if info["historii"]:
                    res[t] = (z, info["historii"])
            t += timedelta(days=1)
        out[c] = res
    return out


def episodes(imp: dict, thr: float, gap: int = 7) -> list[tuple[str, date]]:
    eps = []
    for c, days in imp.items():
        last = None
        for d in sorted(days):
            z, n = days[d]
            if z >= thr and n >= 2:
                if last is None or (d - last).days > gap:
                    eps.append((c, d))
                last = d
    return eps


def evaluate(imp: dict, events: list[dict], start: date, end: date, thr: float, horizon: int = 30) -> dict:
    eps = episodes(imp, thr)
    ev_by_c = defaultdict(list)
    for e in events:
        if start + timedelta(days=30) <= e["data"] <= end:
            ev_by_c[e["kraj"]].append(e["data"])
    n_ev = sum(len(v) for v in ev_by_c.values())
    hits = {L: 0 for L in LEADS}
    leads = []
    for c, evs in ev_by_c.items():
        alarms = [d for cc, d in eps if cc == c]
        for ed in evs:
            before = [d for d in alarms if ed - timedelta(days=max(LEADS)) <= d < ed]
            for L in LEADS:
                hits[L] += any(ed - timedelta(days=L) <= d for d in before)
            if before:
                leads.append((ed - max(before)).days)
    true = sum(1 for c, d in eps if any(d < ed <= d + timedelta(days=horizon) for ed in ev_by_c.get(c, [])))
    # stopa bazowa: odsetek dni kraj-dzień (spośród krajów z danymi), po których w ciągu `horizon` dni było wydarzenie
    days_total = days_pos = 0
    for c, days in imp.items():
        for d in days:
            days_total += 1
            days_pos += any(d < ed <= d + timedelta(days=horizon) for ed in ev_by_c.get(c, []))
    base = days_pos / days_total if days_total else None
    prec = true / len(eps) if eps else None
    leads.sort()
    return {"prog": thr, "wydarzen": n_ev, "trafienia": {L: hits[L] for L in LEADS}, "epizodow": len(eps), "prawdziwe": true,
            "precyzja": prec, "baza": base, "lift": (prec / base) if prec is not None and base else None,
            "mediana_wyprzedzenia": leads[len(leads) // 2] if leads else None}


def _pct(x):
    return "brak" if x is None else f"{x:.0%}"


def write(path: str, res: dict, horizon: int) -> None:
    L = [f"# Impuls 48 h: test historyczny ({date.today().isoformat()})", "",
         "Impuls = ile nowych spraw (ważonych, źródła pierwotne ważą więcej) pojawiło się w kraju w 48 h w porównaniu z jego zwykłym "
         "tłem z poprzednich 4 tygodni. Alarm impulsu: impuls od progu i co najmniej 2 nowe sprawy; alarmy w odstępie do 7 dni to jeden epizod.",
         f"Trafienie: epizod impulsu w ciągu N dni przed wydarzeniem. Precyzja: odsetek epizodów, po których w ciągu {horizon} dni "
         "nastąpiło wydarzenie w tym kraju. Przewaga nad losowym = precyzja / odsetek wszystkich dni kraj-dzień, po których nastąpiło wydarzenie.", ""]
    for period, rows in res.items():
        L += [f"## {period}", "", "| próg | wydarzeń | impuls ≤3 dni przed | ≤7 dni | ≤14 dni | ≤30 dni | epizodów | precyzja | przewaga nad losowym | mediana wyprzedzenia |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            n = r["wydarzen"] or 1
            h = r["trafienia"]
            lift = "brak" if r["lift"] is None else f"{r['lift']:.1f}×"
            L.append(f"| {r['prog']} | {r['wydarzen']} | {h[3]} ({h[3] / n:.0%}) | {h[7]} ({h[7] / n:.0%}) | {h[14]} ({h[14] / n:.0%}) | "
                     f"{h[30]} ({h[30] / n:.0%}) | {r['epizodow']} | {_pct(r['precyzja'])} | "
                     f"{lift} | "
                     f"{'brak' if r['mediana_wyprzedzenia'] is None else str(r['mediana_wyprzedzenia']) + ' dni'} |")
        L.append("")
    L += ["Daty wydarzeń w listach są przybliżone (z wiedzy ogólnej), więc wyprzedzenie 1–3 dni bywa niepewne. To test na danych "
          "historycznych, nie gwarancja i nie rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None) -> int:
    from . import store
    from .backtest import load_events
    from .score import extract_signals
    ap = argparse.ArgumentParser(prog="analizator.impuls")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", nargs="*", default=[])
    ap.add_argument("--out", default="raporty/impuls-wyniki.md")
    ap.add_argument("--horyzont", type=int, default=30)
    a = ap.parse_args(argv)
    t0 = time.time()
    items = store.load(store.connect(a.db)) + [x for p in a.pierwotne if os.path.exists(p) for x in store.load(store.connect(p))]
    sig = extract_signals(items)
    print(f"sygnały: {len(sig)} ({time.time() - t0:.0f} s)", flush=True)
    d = date.fromisoformat
    res = {}
    for label, csv, s, e in [("Lata 2019–2024 (wydarzenia z listy 2015–2024)", "wydarzenia_2015_2024.csv", d("2019-03-01"), d("2024-12-31")),
                             (f"Test 2025-03 – {date.today():%Y-%m} (wydarzenia 2025–2026)", "wydarzenia.csv", d("2025-03-01"), date.today())]:
        imp = daily_impulse([x for x in sig if s - timedelta(days=40) <= x["date"] <= e], s, e)
        evs = load_events(csv)
        res[label] = [evaluate(imp, evs, s, e, thr, a.horyzont) for thr in THRESHOLDS]
        for r in res[label]:
            print(f"  {label[:12]} próg {r['prog']}: {r}", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write(a.out, res, a.horyzont)
    print(open(a.out, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
