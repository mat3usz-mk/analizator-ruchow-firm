"""Dopracowanie impulsu 48 h: siatka wariantów (okno, tło, minimum spraw, premia za nowe kategorie, waga artykułów,
potwierdzenie przez 2 dni, próg) i to, które kanały napędzają trafne impulsy.

Reguła wyboru ustalona z góry: na latach 2019–2024 bierzemy warianty z precyzją co najmniej taką jak obecny impuls ≥10
i co najmniej 30 epizodami, a z nich te, które łapią najwięcej wydarzeń do 7 dni przed. Potem sprawdzamy je na 2025–2026
(dane, których wybór nie widział) i testem permutacyjnym. Wdrażamy tylko, jeśli na 2025–2026 łapie więcej przy
precyzji nie gorszej niż obecny impuls.

    python -m analizator.impuls_warianty --db historia_gkg.db --pierwotne pierwotne_historia.db --out raporty/impuls-warianty.md
"""
from __future__ import annotations

import argparse
import itertools
import os
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

CAP = 3.0
OBECNY = {"okno": 2, "tlo": 28, "min_n": 2, "premia": 0.5, "artykuly": 1.0, "dni": 1, "prog": 10.0}
GRID = {"okno": [1, 2, 3], "tlo": [14, 28, 56], "min_n": [1, 2, 3], "premia": [0.0, 0.5, 1.0], "artykuly": [1.0, 0.5],
        "dni": [1, 2], "prog": [6.0, 8.0, 10.0, 12.0, 15.0]}


def stories(signals: list[dict]) -> dict[str, list[tuple[date, float, str, str | None, bool]]]:
    """kraj -> [(dzień pierwszego pojawienia się, waga, kategoria, kanał, twarde)], jak w score._impulse."""
    from .slady import HARD, channel
    first: dict[str, dict[str, tuple]] = defaultdict(dict)
    for s in signals:
        if s["weight"] <= 0.05 or s.get("reactive") or s.get("negated"):
            continue
        st = s.get("story") or s.get("url") or s["title"]
        old = first[s["country"]].get(st)
        if old is None or s["date"] < old[0]:
            first[s["country"]][st] = (s["date"], s["weight"], s["category"], channel(s), s.get("source") in HARD)
    return {c: list(v.values()) for c, v in first.items()}


def series(st: dict, start: date, end: date, okno: int, tlo: int, premia: float, artykuly: float
           ) -> dict[str, dict[date, tuple[float, int, str | None]]]:
    """kraj -> dzień -> (impuls, liczba nowych spraw w oknie, kanał dominujący w oknie). Sumy kroczące po dniach."""
    import bisect
    out = {}
    lo = start - timedelta(days=okno + tlo)
    n_days = (end - lo).days + 1
    for c, items in st.items():
        w = [0.0] * n_days
        cnt = [0] * n_days
        chs: dict[int, Counter] = defaultdict(Counter)
        cat_days: dict[str, list[int]] = defaultdict(list)
        for d0, wt, cat, ch, hard in items:
            if lo <= d0 <= end:
                i = (d0 - lo).days
                w[i] += min(wt, CAP) * (1.0 if hard else artykuly)
                cnt[i] += 1
                chs[i][ch or "artykuły"] += 1
                cat_days[cat].append(i)
        if not any(cnt):
            continue
        for v in cat_days.values():
            v.sort()
        pw, pc = [0.0], [0]
        for i in range(n_days):
            pw.append(pw[-1] + w[i])
            pc.append(pc[-1] + cnt[i])
        res = {}
        for i in range(okno + tlo, n_days):
            n_now = pc[i + 1] - pc[i + 1 - okno]
            if not n_now:
                continue
            w_now = pw[i + 1] - pw[i + 1 - okno]
            w_base = (pw[i + 1 - okno] - pw[i + 1 - okno - tlo]) * okno / tlo
            new = 0
            for days in cat_days.values():
                j = bisect.bisect_left(days, i + 1 - okno)
                if j < len(days) and days[j] <= i:  # kategoria jest w oknie
                    k = bisect.bisect_left(days, i + 1 - okno - tlo)
                    new += not (k < len(days) and days[k] < i + 1 - okno)
            z = (w_now - w_base) / (w_base + 1.0) ** 0.5 + premia * new
            cc = Counter()
            for x in range(i + 1 - okno, i + 1):
                cc.update(chs.get(x, {}))
            res[lo + timedelta(days=i)] = (z, n_now, cc.most_common(1)[0][0])
        out[c] = res
    return out


def episodes(ser: dict, prog: float, min_n: int, dni: int, gap: int = 7) -> list[tuple[str, date, str]]:
    eps = []
    for c, days in ser.items():
        last = None
        for d in sorted(days):
            z, n, ch = days[d]
            ok = z >= prog and n >= min_n
            if ok and dni > 1:
                prev = days.get(d - timedelta(days=1))
                ok = prev is not None and prev[0] >= prog
            if ok:
                if last is None or (d - last).days > gap:
                    eps.append((c, d, ch))
                last = d
    return eps


def score(eps, ev_by_c: dict[str, list[date]], horizon: int = 30) -> dict:
    alarms = defaultdict(list)
    for c, d, _ in eps:
        alarms[c].append(d)
    caught = {3: 0, 7: 0, 30: 0}
    for c, evs in ev_by_c.items():
        for ed in evs:
            for L in caught:
                caught[L] += any(ed - timedelta(days=L) <= d < ed for d in alarms.get(c, ()))
    true = sum(1 for c, d, _ in eps if any(d < ed <= d + timedelta(days=horizon) for ed in ev_by_c.get(c, ())))
    return {"epizodow": len(eps), "trafnych": true, "precyzja": true / len(eps) if eps else 0.0, "zlapane": caught}


def main(argv=None) -> int:
    from . import store
    from .backtest import load_events
    from .permutacja import run as perm
    from .score import extract_signals
    ap = argparse.ArgumentParser(prog="analizator.impuls_warianty")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", nargs="*", default=[])
    ap.add_argument("--out", default="raporty/impuls-warianty.md")
    a = ap.parse_args(argv)
    t0 = time.time()
    items = store.load(store.connect(a.db)) + [x for p in a.pierwotne if os.path.exists(p) for x in store.load(store.connect(p))]
    sig = extract_signals(items)
    st = stories(sig)
    print(f"sygnały: {len(sig)}, kraje: {len(st)} ({time.time() - t0:.0f} s)", flush=True)
    d = date.fromisoformat
    periods = {"2019–2024": ("wydarzenia_2015_2024.csv", d("2019-03-01"), d("2024-12-31")),
               "2025–2026": ("wydarzenia.csv", d("2025-03-01"), date.today() - timedelta(days=30))}
    evs, sers = {}, {}
    for p, (csv, s, e) in periods.items():
        byc = defaultdict(list)
        for x in load_events(csv):
            if s + timedelta(days=30) <= x["data"] <= e:
                byc[x["kraj"]].append(x["data"])
        evs[p] = byc
    keys = list(GRID)
    results = {p: {} for p in periods}
    for okno, tlo, premia, art in itertools.product(GRID["okno"], GRID["tlo"], GRID["premia"], GRID["artykuly"]):
        for p, (csv, s, e) in periods.items():
            ser = series(st, s, e, okno, tlo, premia, art)
            sers[(p, okno, tlo, premia, art)] = ser if (okno, tlo, premia, art) == (2, 28, 0.5, 1.0) else None
            for min_n, dni, prog in itertools.product(GRID["min_n"], GRID["dni"], GRID["prog"]):
                v = (okno, tlo, min_n, premia, art, dni, prog)
                eps = episodes(ser, prog, min_n, dni)
                results[p][v] = (score(eps, evs[p]), eps)
        print(f"  okno {okno} tło {tlo} premia {premia} artykuły {art} ({time.time() - t0:.0f} s)", flush=True)
    cur = tuple(OBECNY[k] for k in keys)
    base_tr = results["2019–2024"][cur][0]
    # wybór na 2019–2024
    cand = [(v, r) for v, (r, _) in results["2019–2024"].items() if r["epizodow"] >= 30 and r["precyzja"] >= base_tr["precyzja"]]
    cand.sort(key=lambda x: (-x[1]["zlapane"][7], -x[1]["precyzja"]))
    top = [v for v, _ in cand[:8]]
    if cur not in top:
        top.append(cur)

    def desc(v):
        okno, tlo, min_n, premia, art, dni, prog = v
        return (f"okno {okno * 24} h, tło {tlo} dni, min. {min_n} spraw, premia {premia}, artykuły ×{art}, "
                f"{'2 dni z rzędu' if dni == 2 else '1 dzień'}, próg {prog:g}")

    L = [f"# Impuls 48 h: dopracowanie ({date.today().isoformat()})", "",
         "Siatka wariantów impulsu: okno (24/48/72 h), długość tła (14/28/56 dni), minimum nowych spraw, premia za nowe kategorie, "
         "waga artykułów względem twardych danych, wymóg 2 dni z rzędu, próg. Epizod: alarm impulsu, kolejne w odstępie do 7 dni "
         "łączone. Trafny epizod: wydarzenie w tym kraju w ciągu 30 dni. Złapane: wydarzenie, przed którym był epizod do 3/7/30 dni.",
         "", f"Reguła wyboru (z góry): na 2019–2024 precyzja co najmniej jak obecny impuls ({base_tr['precyzja']:.0%}) i co najmniej 30 "
         "epizodów, a z tych najwięcej złapanych do 7 dni. Potem sprawdzenie na 2025–2026 i test permutacyjny (losowe daty wydarzeń, "
         "1000 losowań; p = odsetek losowań co najmniej tak dobrych).", "",
         "| wariant | okres | epizodów | trafnych | precyzja | złapane ≤3 dni | ≤7 dni | ≤30 dni | p |", "|---|---|---|---|---|---|---|---|---|"]
    for v in top:
        for p, (csv, s, e) in periods.items():
            r, eps = results[p][v]
            n_ev = sum(len(x) for x in evs[p].values())
            pr = perm([(c, dd) for c, dd, _ in eps], [(c, x) for c, xs in evs[p].items() for x in xs], s, e + timedelta(days=30),
                      n=1000, horizon=30)["przesuniecie"]["p"] if eps else 1.0
            z = r["zlapane"]
            L.append(f"| {'**obecny** ' if v == cur else ''}{desc(v)} | {p} | {r['epizodow']} | {r['trafnych']} | {r['precyzja']:.0%} | "
                     f"{z[3]} z {n_ev} | {z[7]} | {z[30]} | {pr:.3f} |")
    # krzywa progu dla obecnego wariantu
    L += ["", "## Obecny wariant przy różnych progach", "", "| próg | okres | epizodów | precyzja | złapane ≤7 dni |", "|---|---|---|---|---|"]
    for prog in GRID["prog"]:
        v = cur[:-1] + (prog,)
        for p in periods:
            r = results[p][v][0]
            L.append(f"| {prog:g} | {p} | {r['epizodow']} | {r['precyzja']:.0%} | {r['zlapane'][7]} |")
    # które kanały napędzają impulsy
    L += ["", "## Co napędza impulsy (obecny wariant, próg 6, kanał dominujący w oknie)", "",
          "| kanał | okres | epizodów | trafnych | precyzja |", "|---|---|---|---|---|"]
    for p in periods:
        ser = sers[(p, 2, 28, 0.5, 1.0)]
        eps = episodes(ser, 6.0, 2, 1)
        by = defaultdict(list)
        for c, dd, ch in eps:
            by[ch].append((c, dd, ch))
        for ch, es in sorted(by.items(), key=lambda x: -len(x[1])):
            r = score(es, evs[p])
            L.append(f"| {ch} | {p} | {r['epizodow']} | {r['trafnych']} | {r['precyzja']:.0%} |")
    L += ["", "Daty wydarzeń są przybliżone, więc wyprzedzenie 1–3 dni bywa niepewne. To test historyczny, nie gwarancja i nie "
          "rekomendacja inwestycyjna."]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
