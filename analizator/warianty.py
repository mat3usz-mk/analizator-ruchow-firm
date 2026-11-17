"""Test historyczny wariantów parametrów (np. waga przedruków): ten sam ręczny indeks, próg 40, wydarzenie w ciągu 60 dni.

    python -m analizator.warianty --db historia_gkg.db --pierwotne pierwotne_historia.db \\
        --warianty "przedruk=1.0;przedruk=0.15;przedruk=0.0" --out raporty/przedruki-wyniki.md
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date


def main(argv=None) -> int:
    from . import score, store
    from .backtest import evaluate, load_events, replay
    from .ucz import _counts
    ap = argparse.ArgumentParser(prog="analizator.warianty")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", nargs="*", default=[])
    ap.add_argument("--warianty", required=True, help="np. przedruk=1.0;przedruk=0.15 (kilka parametrów: a=1,b=2)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    items = store.load(store.connect(a.db)) + [x for p in a.pierwotne if os.path.exists(p) for x in store.load(store.connect(p))]
    base = dict(score.PARAMS)
    d = date.fromisoformat
    periods = [("Lata 2019–2024 (wydarzenia z listy 2015–2024)", "wydarzenia_2015_2024.csv", d("2019-03-01"), d("2024-12-31")),
               (f"Test 2025-03 – {date.today():%Y-%m} (wydarzenia 2025–2026)", "wydarzenia.csv", d("2025-03-01"), date.today())]
    res: dict[str, dict[str, dict]] = {p[0]: {} for p in periods}
    for var in a.warianty.split(";"):
        over = {k.strip(): float(v) for k, v in (kv.split("=") for kv in var.split(","))}
        score.PARAMS.clear()
        score.PARAMS.update({**base, **over})
        t0 = time.time()
        sig = score.extract_signals(items)
        for label, csv_path, s, e in periods:
            ev = _counts(evaluate(replay(sig, s, e), load_events(csv_path)))
            res[label][var] = ev
            print(f"  {var} {label[:10]}: trafione {ev['hit_rate']}, precyzja {ev['precision']}, prawdziwe {ev['prawdziwe']}, "
                  f"fałszywe {ev['falszywe']} ({time.time() - t0:.0f} s)", flush=True)
    pct = lambda x: "brak" if x is None else f"{x:.0%}"
    L = [f"# Warianty parametrów: test historyczny ({date.today().isoformat()})", "",
         "Ręczny indeks, próg alarmu 40, wydarzenie w ciągu 60 dni. „przedruk” = waga wzmianki o zdarzeniu starszym niż 7 dni "
         "(przedruk albo ponowny opis starej decyzji); 1,0 = jak dotąd.", ""]
    for label, rows in res.items():
        L += [f"## {label}", "", "| wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy | mediana wyprzedzenia |",
              "|---|---|---|---|---|---|---|"]
        for var, ev in rows.items():
            L.append(f"| {var} | {pct(ev['hit_rate'])} | {pct(ev['hit_rate_fresh'])} | {pct(ev['precision'])} | {ev['prawdziwe']} | "
                     f"{ev['falszywe']} | {'brak' if ev['median_lead'] is None else str(ev['median_lead']) + ' dni'} |")
        L.append("")
    L.append("To test na danych historycznych, nie gwarancja i nie rekomendacja inwestycyjna.")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
