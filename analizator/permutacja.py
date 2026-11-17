"""Test permutacyjny: czy alarmy trafiają częściej, niż wynikałoby z przypadku.

Bierzemy prawdziwe początki epizodów alarmowych (reguła łączona, raporty/epizody.json) i prawdziwe wydarzenia, a potem
wielokrotnie psujemy związek między nimi na dwa sposoby:
  przesunięcie  każde wydarzenie dostaje losową datę w tym samym okresie (kraj zostaje, zostaje też liczba wydarzeń w kraju),
  zamiana       daty zostają, ale wydarzenia losowo zamieniają się krajami (zostaje rytm świata, znika powiązanie z krajem).
Wartość p = odsetek losowań, w których „trafnych alarmów” było co najmniej tyle, ile naprawdę.

    python -m analizator.permutacja --out raporty/permutacja-wyniki.md
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta


def precision(eps: list[tuple[str, date]], events: list[tuple[str, date]], horizon: int = 60) -> tuple[int, int]:
    by_c: dict[str, list[date]] = {}
    for c, d in events:
        by_c.setdefault(c, []).append(d)
    hit = sum(1 for c, d in eps if any(d < e <= d + timedelta(days=horizon) for e in by_c.get(c, ())))
    return hit, len(eps)


def run(eps, events, start: date, end: date, n: int = 2000, seed: int = 7, horizon: int = 60) -> dict:
    rnd = random.Random(seed)
    real, total = precision(eps, events, horizon)
    span = (end - start).days
    shift, swap = [], []
    countries = [c for c, _ in events]
    for _ in range(n):
        shift.append(precision(eps, [(c, start + timedelta(days=rnd.randrange(span))) for c, _ in events], horizon)[0])
        cs = countries[:]
        rnd.shuffle(cs)
        swap.append(precision(eps, [(c2, d) for c2, (_, d) in zip(cs, events)], horizon)[0])
    out = {"alarmow": total, "trafnych": real, "wydarzen": len(events)}
    for k, xs in (("przesuniecie", shift), ("zamiana", swap)):
        xs.sort()
        out[k] = {"srednio": sum(xs) / n, "p": sum(1 for x in xs if x >= real) / n, "p95": xs[int(0.95 * n)]}
    return out


def main(argv=None) -> int:
    from .backtest import load_events
    ap = argparse.ArgumentParser(prog="analizator.permutacja")
    ap.add_argument("--epizody", default="raporty/epizody.json")
    ap.add_argument("--out", default="raporty/permutacja-wyniki.md")
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args(argv)
    eps_all = [(e["kraj"], date.fromisoformat(e["data"])) for e in json.load(open(a.epizody, encoding="utf-8"))["epizody"]]
    d = date.fromisoformat
    periods = [("2019–2024", "wydarzenia_2015_2024.csv", d("2019-03-01"), d("2024-12-31")),
               ("2025–2026 (test)", "wydarzenia.csv", d("2025-03-01"), date.today() - timedelta(days=60))]
    L = [f"# Test permutacyjny alarmów ({date.today().isoformat()})", "",
         "Alarmy: początki epizodów reguły łączonej (model + ręczny indeks), raporty/epizody.json. Trafny alarm: wydarzenie w tym kraju "
         f"w ciągu 60 dni. Losowań: {a.n}. Przesunięcie: wydarzenia dostają losowe daty w tym samym okresie. Zamiana: wydarzenia "
         "losowo zamieniają się krajami. Wartość p: odsetek losowań co najmniej tak dobrych jak rzeczywistość (mniej niż 5% = wynik "
         "raczej nieprzypadkowy).", "",
         "| okres | alarmów | trafnych naprawdę | trafnych losowo (przesunięcie) | p | trafnych losowo (zamiana krajów) | p |",
         "|---|---|---|---|---|---|---|"]
    for label, csv, s, e in periods:
        eps = [(c, t) for c, t in eps_all if s <= t <= e]
        evs = [(x["kraj"], x["data"]) for x in load_events(csv) if s <= x["data"] <= e + timedelta(days=60)]
        r = run(eps, evs, s, e + timedelta(days=60), a.n)
        print(label, r)
        L.append(f"| {label} | {r['alarmow']} | {r['trafnych']} ({r['trafnych'] / max(r['alarmow'], 1):.0%}) | "
                 f"{r['przesuniecie']['srednio']:.1f} | {r['przesuniecie']['p']:.3f} | {r['zamiana']['srednio']:.1f} | {r['zamiana']['p']:.3f} |")
    L += ["", "Jak czytać: „przesunięcie” sprawdza, czy alarmy trafiają w czas, a nie tylko w kraje, w których często coś się dzieje. "
          "„Zamiana” sprawdza, czy trafiają we właściwy kraj, a nie tylko w okresy, gdy na świecie jest dużo wydarzeń. "
          "To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna."]
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
