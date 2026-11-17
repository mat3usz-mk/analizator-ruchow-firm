"""Testy nowych źródeł, każde osobno, oraz test permutacyjny alarmów wysyłanych mailem.

1. Permutacja: czy impulsy 48 h (próg 10), wyuczone pary śladów i zbieżność twardych danych trafiają częściej niż przypadek.
2. Każde nowe źródło osobno (wiki, ton): samo jako alarm (precyzja, przewaga, permutacja) i dołożone do ręcznego indeksu
   (trafienia, precyzja, fałszywe alarmy wobec stanu bez niego).
3. EIA (sygnał globalny): czy nietypowy tydzień zapasów ropy poprzedza kryzys energetyczny albo blokadę gdziekolwiek w ciągu 30 dni.

    python -m analizator.nowe_testy --db historia_gkg.db --pierwotne pierwotne_historia.db ryby_historia.db --nowe nowe_historia.db
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import date, timedelta


def _eps_from_days(hits: dict[str, set[date]], gap: int = 7) -> list[tuple[str, date]]:
    eps = []
    for c, days in hits.items():
        last = None
        for d in sorted(days):
            if last is None or (d - last).days > gap:
                eps.append((c, d))
            last = d
    return eps


def _perm(eps, evs, s, e, n=1000):
    from .permutacja import run
    eps = [(c, d) for c, d in eps if s <= d <= e - timedelta(days=60)]
    ev = [(x["kraj"], x["data"]) for x in evs if s <= x["data"] <= e]
    return run(eps, ev, s, e, n)


def _pct(x):
    return "brak" if x is None else f"{x:.0%}"


def main(argv=None) -> int:
    from . import slady, store
    from .backtest import evaluate as bt_eval, load_events, replay
    from .impuls import daily_impulse, episodes
    from .score import extract_signals
    from .ucz import _counts
    ap = argparse.ArgumentParser(prog="analizator.nowe_testy")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", nargs="*", default=[])
    ap.add_argument("--nowe", nargs="*", default=["nowe_historia.db"])
    ap.add_argument("--out", default="raporty/nowe-zrodla-wyniki.md")
    ap.add_argument("--zrodla", default="wiki,ton")
    ap.add_argument("--tylko-eia", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    base_items = store.load(store.connect(a.db)) + [x for p in a.pierwotne if os.path.exists(p) for x in store.load(store.connect(p))]
    new_items = [x for p in a.nowe if os.path.exists(p) for x in store.load(store.connect(p))]
    sig = extract_signals(base_items)
    new_sig = {src: extract_signals([x for x in new_items if x["source"] == src]) for src in a.zrodla.split(",")}
    print(f"sygnały: {len(sig)}, nowe: { {k: len(v) for k, v in new_sig.items()} } ({time.time() - t0:.0f} s)", flush=True)
    d = date.fromisoformat
    periods = [("2019–2024", load_events("wydarzenia_2015_2024.csv"), d("2019-03-01"), d("2024-12-31")),
               ("2025–2026 (test)", load_events("wydarzenia.csv"), d("2025-03-01"), date.today())]
    L = [f"# Nowe źródła i test permutacyjny ({date.today().isoformat()})", "",
         "Każde źródło sprawdzone osobno. Trafny alarm: wydarzenie w tym kraju w ciągu 60 dni. Wartość p z testu permutacyjnego: "
         "odsetek losowań (daty wydarzeń losowo przesunięte albo kraje zamienione), w których wynik był co najmniej tak dobry jak "
         "naprawdę; mniej niż 0,05 = raczej nie przypadek.", ""]

    if a.tylko_eia:
        sig, new_sig = [], {}
    # 1) permutacja dla alarmów, które idą mailem albo mają potwierdzać alarm
    tr = slady.traces(sig)
    import json
    pairs = json.load(open(slady.PARY, encoding="utf-8"))
    weights = {(p["a"], p["b"], p["dni"]): p["przewaga"] for p in pairs["pary"]}
    L += ["## Test permutacyjny", "", "| alarm | okres | alarmów | trafnych | losowo (przesunięcie) | p | losowo (zamiana krajów) | p |",
          "|---|---|---|---|---|---|---|---|"]
    for label, evs, s, e in ([] if a.tylko_eia else periods):
        imp = daily_impulse([x for x in sig if s - timedelta(days=40) <= x["date"] <= e], s, e)
        sets = {"impuls 48 h ≥ 10": episodes(imp, 10.0), "impuls 48 h ≥ 6": episodes(imp, 6.0),
                "wyuczone pary śladów": _eps_from_days(slady.weighted_hits(tr, weights, pairs["prog"], s, e)),
                "twarde dane + potwierdzenie (48 h)": _eps_from_days(slady.daily(tr, s, e, 2, 2, "twarde+"))}
        for name, eps in sets.items():
            r = _perm(eps, evs, s, e)
            print(f"  perm {label} {name}: {r}", flush=True)
            L.append(f"| {name} | {label} | {r['alarmow']} | {r['trafnych']} ({r['trafnych'] / max(r['alarmow'], 1):.0%}) | "
                     f"{r['przesuniecie']['srednio']:.1f} | {r['przesuniecie']['p']:.3f} | {r['zamiana']['srednio']:.1f} | {r['zamiana']['p']:.3f} |")
    L.append("")

    # 2) nowe źródła, każde osobno
    L += ["## Nowe źródła osobno", "", "Samo źródło jako alarm:", "",
          "| źródło | okres | sygnałów | epizodów | precyzja | przewaga nad losowym | p (przesunięcie) | p (zamiana) |", "|---|---|---|---|---|---|---|---|"]
    added = []
    for src, ns in new_sig.items():
        for label, evs, s, e in periods:
            hits = defaultdict(set)
            for x in ns:
                if s <= x["date"] <= e:
                    hits[x["country"]].add(x["date"])
            ev = slady.evaluate(dict(hits), tr, evs, s, e)
            r = _perm(_eps_from_days(hits), evs, s, e)
            lift = "brak" if ev["lift"] is None else f"{ev['lift']:.1f}×"
            L.append(f"| {src} | {label} | {sum(len(v) for v in hits.values())} | {ev['ocenionych']} | {_pct(ev['precyzja'])} | "
                     f"{lift} | {r['przesuniecie']['p']:.3f} | {r['zamiana']['p']:.3f} |")
            print(f"  {src} {label}: {ev}", flush=True)
    L += ["", "Dołożone do ręcznego indeksu (próg 40, wydarzenie w 60 dni):", "",
          "| wariant | okres | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |", "|---|---|---|---|---|---|---|"]
    for label, evs, s, e in ([] if a.tylko_eia else periods):
        win = lambda xs: [x for x in xs if s - timedelta(days=200) <= x["date"] <= e]
        base = _counts(bt_eval(replay(win(sig), s, e), evs))
        rows = [("bez nowych źródeł", base)] + [(f"+ {src}", _counts(bt_eval(replay(win(sig + ns), s, e), evs))) for src, ns in new_sig.items()]
        for name, ev in rows:
            L.append(f"| {name} | {label} | {_pct(ev['hit_rate'])} | {_pct(ev['hit_rate_fresh'])} | {_pct(ev['precision'])} | {ev['prawdziwe']} | {ev['falszywe']} |")
            print(f"  indeks {label} {name}: {ev['prawdziwe']} / {ev['falszywe']} / {ev['hit_rate']}", flush=True)
            added.append((label, name, ev))
    L.append("")

    # 3) EIA: sygnał globalny, wydarzenia energetyczne gdziekolwiek
    eia = sorted({date.fromisoformat(x["date"][:10]) for x in new_items if x["source"] == "eia"})
    if eia:
        L += ["## Zapasy ropy EIA (sygnał globalny)", "", "Nietypowy tydzień (zmiana zapasów ≥ 2,5 odchylenia od 52 tygodni). Czy w ciągu 30 dni "
              "nastąpił kryzys energetyczny albo blokada gdziekolwiek, wobec zwykłego tygodnia.", "",
              "| okres | nietypowych tygodni | z wydarzeniem w 30 dni | zwykle (każdy tydzień) |", "|---|---|---|---|"]
        for label, evs, s, e in periods:
            ev = sorted(x["data"] for x in evs if (x.get("typ") or "").strip() in ("kryzys_energetyczny", "blokada"))
            follow = lambda w: any(w < x <= w + timedelta(days=30) for x in ev)
            wk = [w for w in eia if s <= w <= e - timedelta(days=30)]
            allw = []
            t = s
            while t <= e - timedelta(days=30):
                allw.append(t)
                t += timedelta(days=7)
            hit = sum(follow(w) for w in wk)
            L.append(f"| {label} | {len(wk)} | {hit} ({_pct(hit / len(wk) if wk else None)}) | {_pct(sum(map(follow, allw)) / len(allw) if allw else None)} |")
        L.append("")
    L += ["Reguła Sahm (bezrobocie w USA) pominięta: wskaźnik miesięczny, dotyczy tylko gospodarki USA i nie ma związku z krajami, "
          "dla których analizator szuka wydarzeń. Google Trends pominięte: brak oficjalnego dostępu do historii (tylko nieoficjalne "
          "pobieranie strony, blokowane przy większej liczbie zapytań); zamiast tego odsłony Wikipedii z oficjalnego API Wikimedia.",
          "", "To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna."]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
