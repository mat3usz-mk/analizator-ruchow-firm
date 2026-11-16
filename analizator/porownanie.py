"""Test historyczny: czy źródła pierwotne i mniejsza waga artykułów poprawiają wynik.

Warianty (ręczny indeks, próg 40, te same wydarzenia):
  A  tylko artykuły (jak dotąd)
  B  artykuły + źródła pierwotne (sankcje UE/UK, awarie internetu IODA, przejścia przez cieśniny, spadki walut)
  C  jak B, artykuły z wagą 0,5
  D  jak B, artykuły z wagą 0,25
  E  tylko źródła pierwotne

    python -m analizator.porownanie --db historia_gkg.db --pierwotne pierwotne_historia.db --out raporty/pierwotne-porownanie.md

Uwaga: listy sankcji zawierają tylko obowiązujące wpisy (zdjęte z listy znikają), a IODA ma pełne dane dopiero od ok. 2022 r.
"""
from __future__ import annotations

import argparse
import os
import time
from collections import Counter
from datetime import date

VARIANTS = [("A", "tylko artykuły", 1.0, True, False), ("B", "artykuły + źródła pierwotne", 1.0, True, True),
            ("C", "jak B, artykuły z wagą 0,5", 0.5, True, True), ("D", "jak B, artykuły z wagą 0,25", 0.25, True, True),
            ("E", "tylko źródła pierwotne", 1.0, False, True)]


def _scaled(rows: list[dict], f: float) -> list[dict]:
    return [{**r, "weight": round(r["weight"] * f, 3)} for r in rows] if f != 1.0 else rows


def run(art_sig, prim_sig, events, start: date, end: date, threshold: float = 40.0, horizon: int = 60) -> dict:
    from .backtest import evaluate, replay
    from .ucz import _counts
    out = {}
    for key, label, f, use_art, use_prim in VARIANTS:
        t0 = time.time()
        sig = (_scaled(art_sig, f) if use_art else []) + (prim_sig if use_prim else [])
        idx = replay(sig, start, end)
        ev = _counts(evaluate(idx, events, threshold=threshold, horizon=horizon))
        out[key] = ev
        print(f"  {key} {start}..{end}: trafione {ev['hit_rate']}, precyzja {ev['precision']}, prawdziwe {ev['prawdziwe']}, "
              f"fałszywe {ev['falszywe']} ({time.time() - t0:.0f} s)", flush=True)
    return out


def _f(x, pct=True):
    return "brak" if x is None else (f"{x:.0%}" if pct else str(x))


def write(path: str, res: dict[str, dict], meta: dict) -> None:
    L = [f"# Źródła pierwotne kontra artykuły: test historyczny ({date.today().isoformat()})", "",
         "Ręczny indeks, próg alarmu 40, wydarzenie w ciągu 60 dni. Źródła pierwotne w teście: " + meta["zrodla"] + ".", "",
         "Uwagi: listy sankcji zawierają tylko obowiązujące dziś wpisy (zdjęte z listy znikają z historii), IODA ma pełne dane "
         "dopiero od ok. 2022 r., a PortWatch od 2019 r. Artykuły to tytuły z GDELT od 2019 r.", ""]
    for period, r in res.items():
        L += [f"## {period}", "", "| wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy | mediana wyprzedzenia |",
              "|---|---|---|---|---|---|---|"]
        for key, label, *_ in VARIANTS:
            ev = r[key]
            L.append(f"| {key}: {label} | {_f(ev['hit_rate'])} | {_f(ev['hit_rate_fresh'])} | {_f(ev['precision'])} | {ev['prawdziwe']} | "
                     f"{ev['falszywe']} | {'brak' if ev['median_lead'] is None else str(ev['median_lead']) + ' dni'} |")
        L.append("")
    L += ["Precyzja = odsetek alarmów, po których w ciągu 60 dni nastąpiło wydarzenie. To test na danych historycznych, nie gwarancja.",
          "Nie jest to rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None) -> int:
    from . import store
    from .backtest import load_events
    from .score import extract_signals
    ap = argparse.ArgumentParser(prog="analizator.porownanie")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", required=True)
    ap.add_argument("--out", default="raporty/pierwotne-porownanie.md")
    ap.add_argument("--test-from", default="2025-03-01")
    ap.add_argument("--train-from", default="2022-03-01")
    ap.add_argument("--train-to", default="2024-12-31")
    ap.add_argument("--zrodla", default="", help="tylko te źródła pierwotne, np. sankcje_ue,sankcje_uk,kursy")
    a = ap.parse_args(argv)
    t0 = time.time()
    art = extract_signals(store.load(store.connect(a.db)))
    prim_items = store.load(store.connect(a.pierwotne))
    if a.zrodla:
        prim_items = [x for x in prim_items if x["source"] in set(a.zrodla.split(","))]
    prim = extract_signals(prim_items)
    src = Counter(x["source"] for x in prim)
    print(f"sygnały: artykuły {len(art)}, pierwotne {len(prim)} {dict(src)} ({time.time() - t0:.0f} s)", flush=True)
    d = date.fromisoformat
    res = {}
    res[f"Lata {a.train_from[:4]}–{a.train_to[:4]} (wydarzenia z listy 2015–2024)"] = run(
        art, prim, load_events("wydarzenia_2015_2024.csv"), d(a.train_from), d(a.train_to))
    res[f"Test {a.test_from[:7]} – {date.today():%Y-%m} (wydarzenia 2025–2026)"] = run(
        art, prim, load_events("wydarzenia.csv"), d(a.test_from), date.today())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write(a.out, res, {"zrodla": ", ".join(f"{k} ({v} sygnałów)" for k, v in src.most_common())})
    print(open(a.out, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
