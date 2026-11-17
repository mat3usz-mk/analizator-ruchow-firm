"""Łączenie śladów: czy alarm z kilku NIEZALEŻNYCH kanałów naraz (loty, ambasady, wycofanie firm, sankcje, waluta,
statki, energia, giełda) wyprzedza wydarzenia lepiej niż pojedyncze sygnały.

Każdy sygnał trafia do jednego kanału. Zbieżność = w oknie W dni w kraju są nowe sprawy (nie przedruki) z co najmniej K
różnych kanałów, pochodzące z co najmniej K różnych spraw (jeden artykuł opisujący dwie rzeczy nie wystarcza).

Warianty:
  wszystkie   kanały z artykułów i ze źródeł pierwotnych na równi,
  twarde+     co najmniej jeden kanał z twardych danych (pomiar, oficjalna lista), artykuły tylko jako potwierdzenie,
  twarde      tylko twarde dane (kursy, sankcje, przejścia statków, krótka sprzedaż, magazyny gazu).

Do tego bramka: alarm ręcznego indeksu (próg 40) zostaje tylko wtedy, gdy w 14 dniach przed nim była zbieżność K=2.

    python -m analizator.slady --db historia_gkg.db --pierwotne pierwotne_historia.db ryby_historia.db --out raporty/slady-wyniki.md
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import date, timedelta

HARD = {"kursy", "sankcje_ue", "sankcje_uk", "portwatch", "finra_short", "opcje", "agsi", "ofac", "insiders", "ais", "opensky",
        "faa", "easa", "ambasady", "travel", "notam"}
SKIP = {"ioda", "dsca", "acled"}  # wyłączone po testach albo opisujące samo wydarzenie (ACLED), nie ślad przed nim
LABELS = {"loty": "loty i przestrzeń powietrzna", "ambasady": "ambasady, ewakuacje, ostrzeżenia", "firmy": "wycofanie firm",
          "finanse": "finanse i ubezpieczenia", "waluta": "waluta", "sankcje": "sankcje", "statki": "statki i dostawy",
          "energia": "energia", "gielda": "giełda (krótka sprzedaż, opcje)"}
WINDOWS = [2, 7]
KS = [2, 3]
VARIANTS = [("wszystkie", "artykuły i twarde dane na równi"), ("twarde+", "twarde dane + artykuły jako potwierdzenie"),
            ("twarde", "tylko twarde dane")]


def channel(s: dict) -> str | None:
    src, cat = s.get("source"), s.get("category")
    if src in SKIP:
        return None
    if src == "kursy":
        return "waluta"
    if src in ("finra_short", "opcje", "insiders"):
        return "gielda"
    if src in ("sankcje_ue", "sankcje_uk", "ofac") or cat == "sankcje":
        return "sankcje"
    if src in ("portwatch", "ais") or cat == "lancuch_dostaw":
        return "statki"
    if src == "agsi" or cat == "energia_surowce":
        return "energia"
    if cat == "lotnictwo_przestrzen":
        return "loty"
    if cat in ("ewakuacja_personelu", "ostrzezenia_panstw"):
        return "ambasady"
    if cat in ("wyjscie_z_rynku", "wstrzymane_inwestycje", "sprzedaz_aktywow"):
        return "firmy"
    if cat in ("przeplywy_finansowe", "ubezpieczenia_finanse"):
        return "finanse"
    return None


def traces(signals: list[dict]) -> dict[str, dict[date, list[tuple[str, str, bool]]]]:
    """kraj -> dzień -> [(kanał, sprawa, twarde)], tylko pierwsze pojawienie się sprawy."""
    seen: set = set()
    out: dict = defaultdict(lambda: defaultdict(list))
    for s in sorted(signals, key=lambda x: x["date"]):
        if s.get("weight", 1) <= 0.05 or s.get("reactive") or s.get("negated") or s.get("reprint"):
            continue
        ch = channel(s)
        if not ch:
            continue
        story = s.get("story") or s.get("url") or s["title"]
        key = (s["country"], story, ch)
        if key in seen:
            continue
        seen.add(key)
        out[s["country"]][s["date"]].append((ch, str(story), s.get("source") in HARD))
    return out


def converged(day_map: dict, t: date, window: int, k: int, variant: str) -> bool:
    items = [x for i in range(window) for x in day_map.get(t - timedelta(days=i), [])]
    if variant == "twarde":
        items = [x for x in items if x[2]]
    chans = {c for c, _, _ in items}
    if len(chans) < k or len({st for _, st, _ in items}) < k:
        return False
    if variant == "twarde+":
        return any(h for _, _, h in items)
    return True


def daily(tr: dict, start: date, end: date, window: int, k: int, variant: str) -> dict[str, set[date]]:
    out = {}
    for c, dm in tr.items():
        days = set()
        t = start
        while t <= end:
            if dm and converged(dm, t, window, k, variant):
                days.add(t)
            t += timedelta(days=1)
        out[c] = days
    return out


def evaluate(hits: dict[str, set[date]], tr: dict, events: list[dict], start: date, end: date, horizon: int = 60, gap: int = 7) -> dict:
    ev_by_c = defaultdict(list)
    for e in events:
        if start + timedelta(days=30) <= e["data"] <= end:
            ev_by_c[e["kraj"]].append(e["data"])
    eps = []
    for c, days in hits.items():
        last = None
        for d in sorted(days):
            if last is None or (d - last).days > gap:
                eps.append((c, d))
            last = d
    judged = [(c, d) for c, d in eps if d + timedelta(days=horizon) <= end]
    true = sum(1 for c, d in judged if any(d < ed <= d + timedelta(days=horizon) for ed in ev_by_c.get(c, [])))
    # stopa bazowa: dni kraj-dzień (kraje z jakimkolwiek śladem), po których w horyzoncie było wydarzenie
    tot = pos = 0
    for c in tr:
        evs = ev_by_c.get(c, [])
        t = start
        while t + timedelta(days=horizon) <= end:
            tot += 1
            pos += any(t < ed <= t + timedelta(days=horizon) for ed in evs)
            t += timedelta(days=3)
    base = pos / tot if tot else None
    n_ev = sum(len(v) for v in ev_by_c.values())
    caught7 = caught30 = 0
    for c, evs in ev_by_c.items():
        for ed in evs:
            caught7 += any(ed - timedelta(days=7) <= d < ed for d in hits.get(c, ()))
            caught30 += any(ed - timedelta(days=30) <= d < ed for d in hits.get(c, ()))
    prec = true / len(judged) if judged else None
    return {"epizodow": len(eps), "ocenionych": len(judged), "prawdziwe": true, "precyzja": prec, "baza": base,
            "lift": prec / base if prec is not None and base else None, "wydarzen": n_ev, "w7": caught7, "w30": caught30}


def gate(index: dict, hits: dict[str, set[date]], days: int = 14, threshold: float = 40.0) -> dict:
    """Indeks z bramką: wartość ≥ progu zostaje tylko przy zbieżności śladów w `days` dni przed tygodniem."""
    out = {}
    for (c, t), v in index.items():
        ok = v < threshold or any(t - timedelta(days=i) in hits.get(c, ()) for i in range(days))
        out[(c, t)] = v if ok else min(v, threshold - 0.1)
    return out


def _pct(x):
    return "brak" if x is None else f"{x:.0%}"


def write(path: str, res: dict, meta: str) -> None:
    L = [f"# Łączenie śladów: test historyczny ({date.today().isoformat()})", "",
         "Zbieżność: w oknie W dni w kraju pojawiły się nowe sprawy (bez przedruków) z co najmniej K różnych kanałów "
         "(" + ", ".join(LABELS.values()) + "). Kolejne dni zbieżności w odstępie do 7 dni to jeden epizod. "
         "Precyzja: odsetek epizodów, po których w ciągu 60 dni nastąpiło wydarzenie w tym kraju. Przewaga = precyzja / odsetek "
         "zwykłych dni kraju, po których nastąpiło wydarzenie.", "", meta, ""]
    for period, r in res.items():
        L += [f"## {period}", "", "| wariant | okno | K | epizodów | precyzja | przewaga nad losowym | wydarzeń złapanych ≤7 dni przed | ≤30 dni przed |",
              "|---|---|---|---|---|---|---|---|"]
        for row in r["zbieznosc"]:
            n = row["wydarzen"] or 1
            lift = "brak" if row["lift"] is None else f"{row['lift']:.1f}×"
            L.append(f"| {row['wariant']} | {row['okno']} dni | {row['k']} | {row['epizodow']} | {_pct(row['precyzja'])} | {lift} | "
                     f"{row['w7']} z {row['wydarzen']} ({row['w7'] / n:.0%}) | {row['w30']} ({row['w30'] / n:.0%}) |")
        if r.get("bramka"):
            L += ["", "Bramka na alarmy ręcznego indeksu (próg 40, wydarzenie w 60 dni):", "",
                  "| | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |", "|---|---|---|---|---|---|"]
            for lab, ev in r["bramka"].items():
                L.append(f"| {lab} | {_pct(ev['hit_rate'])} | {_pct(ev['hit_rate_fresh'])} | {_pct(ev['precision'])} | {ev['prawdziwe']} | {ev['falszywe']} |")
        L.append("")
    L += ["Ślady z lotów i ambasad w latach historycznych pochodzą z nagłówków (bieżące strony FAA, EASA i ambasad nie mają "
          "archiwum), twarde dane to kursy walut, sankcje UE/UK, przejścia statków, krótka sprzedaż i magazyny gazu. "
          "Daty wydarzeń są przybliżone. To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None) -> int:
    from . import store
    from .backtest import evaluate as bt_eval, load_events, replay
    from .score import extract_signals
    from .ucz import _counts
    ap = argparse.ArgumentParser(prog="analizator.slady")
    ap.add_argument("--db", required=True)
    ap.add_argument("--pierwotne", nargs="*", default=[])
    ap.add_argument("--out", default="raporty/slady-wyniki.md")
    ap.add_argument("--bez-bramki", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    items = store.load(store.connect(a.db)) + [x for p in a.pierwotne if os.path.exists(p) for x in store.load(store.connect(p))]
    sig = extract_signals(items)
    tr_all = traces(sig)
    cnt = defaultdict(int)
    for dm in tr_all.values():
        for xs in dm.values():
            for ch, _, h in xs:
                cnt[("twarde " if h else "") + ch] += 1
    meta = "Ślady w danych: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda x: -x[1])) + "."
    print(f"sygnały {len(sig)}, {meta} ({time.time() - t0:.0f} s)", flush=True)
    d = date.fromisoformat
    res = {}
    for label, csv, s, e in [("Lata 2019–2024 (wydarzenia z listy 2015–2024)", "wydarzenia_2015_2024.csv", d("2019-03-01"), d("2024-12-31")),
                             (f"Test 2025-03 – {date.today():%Y-%m} (wydarzenia 2025–2026)", "wydarzenia.csv", d("2025-03-01"), date.today())]:
        evs = load_events(csv)
        rows = []
        hits_gate = None
        for var, _ in VARIANTS:
            for w in WINDOWS:
                for k in KS:
                    h = daily(tr_all, s, e, w, k, var)
                    r = evaluate(h, tr_all, evs, s, e)
                    rows.append({"wariant": var, "okno": w, "k": k, **r})
                    print(f"  {label[:10]} {var} W{w} K{k}: {r}", flush=True)
        res[label] = {"zbieznosc": rows}
        if not a.bez_bramki:
            idx = replay([x for x in sig if s - timedelta(days=200) <= x["date"] <= e], s, e)
            out = {"bez bramki": _counts(bt_eval(idx, evs))}
            for var in ("wszystkie", "twarde+"):
                hits_gate = daily(tr_all, s - timedelta(days=14), e, 7, 2, var)
                out[f"bramka: {var}, 2 kanały w 14 dniach"] = _counts(bt_eval(gate(idx, hits_gate), evs))
            res[label]["bramka"] = out
            print(f"  bramka {label[:10]}: {out}", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write(a.out, res, meta)
    print(open(a.out, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
