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


_BASE: dict = {}


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
    bkey = (id(tr), id(events), start, end, horizon)
    tot = pos = 0
    for c in (tr if bkey not in _BASE else ()):
        evs = ev_by_c.get(c, [])
        t = start
        while t + timedelta(days=horizon) <= end:
            tot += 1
            pos += any(t < ed <= t + timedelta(days=horizon) for ed in evs)
            t += timedelta(days=3)
    if bkey not in _BASE:
        _BASE[bkey] = pos / tot if tot else None
    base = _BASE[bkey]
    n_ev = sum(len(v) for v in ev_by_c.values())
    caught7 = caught30 = 0
    for c, evs in ev_by_c.items():
        for ed in evs:
            caught7 += any(ed - timedelta(days=7) <= d < ed for d in hits.get(c, ()))
            caught30 += any(ed - timedelta(days=30) <= d < ed for d in hits.get(c, ()))
    prec = true / len(judged) if judged else None
    return {"epizodow": len(eps), "ocenionych": len(judged), "prawdziwe": true, "precyzja": prec, "baza": base,
            "lift": prec / base if prec is not None and base else None, "wydarzen": n_ev, "w7": caught7, "w30": caught30}


CHANNELS = list(LABELS)
LAGS = [2, 7, 14]


def pair_hits(tr: dict, a: str, b: str | None, lag: int, start: date, end: date) -> dict[str, set[date]]:
    """Dni, w których pojawia się ślad b, a ślad a był w ciągu `lag` dni wcześniej (lub tego samego dnia), z innej sprawy.
    b=None: sam kanał a."""
    out = {}
    for c, dm in tr.items():
        days = set()
        for t, xs in dm.items():
            if not (start <= t <= end):
                continue
            if b is None:
                if any(ch == a for ch, _, _ in xs):
                    days.add(t)
                continue
            for ch, st, _ in xs:
                if ch != b:
                    continue
                if any(c2 == a and st2 != st for i in range(lag + 1) for c2, st2, _ in dm.get(t - timedelta(days=i), [])):
                    days.add(t)
                    break
        out[c] = days
    return out


def pair_scan(tr: dict, events: list[dict], start: date, end: date, min_eps: int = 10) -> list[dict]:
    """Wszystkie kanały i uporządkowane pary kanałów (a, potem b w ciągu L dni) z precyzją i przewagą nad losowym."""
    rows = []
    for a in CHANNELS:
        r = evaluate(pair_hits(tr, a, None, 0, start, end), tr, events, start, end)
        rows.append({"a": a, "b": None, "lag": 0, **r})
        for b in CHANNELS:
            if b == a:
                continue
            for L in LAGS:
                r = evaluate(pair_hits(tr, a, b, L, start, end), tr, events, start, end)
                if r["ocenionych"] >= min_eps:
                    rows.append({"a": a, "b": b, "lag": L, **r})
    return rows


def shrunk_lift(r: dict, prior: int = 20) -> float:
    """Przewaga ściągnięta do 1 przy małej liczbie epizodów (żeby 2 trafienia na 3 nie wygrywały)."""
    base = r["baza"] or 1e-9
    return ((r["prawdziwe"] + base * prior) / (r["ocenionych"] + prior)) / base


def weighted_hits(tr: dict, weights: dict[tuple, float], thr: float, start: date, end: date) -> dict[str, set[date]]:
    """Alarm, gdy w kraju zaszła para kanałów, której przewaga (wyuczona na latach wcześniejszych) jest co najmniej `thr`."""
    out: dict[str, set[date]] = defaultdict(set)
    for (a, b, L), w in weights.items():
        if w < thr:
            continue
        for c, days in pair_hits(tr, a, b, L, start, end).items():
            out[c] |= days
    return dict(out)


PARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slady_pary.json")


def live(signals: list[dict], today: date, days: int = 14, path: str = PARY) -> dict[str, list[dict]]:
    """Na żywo: które wyuczone pary śladów zaszły w kraju w ostatnich `days` dniach (najsilniejsza przewaga pierwsza)."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    tr = traces(signals)
    out: dict[str, dict] = defaultdict(dict)
    for p in cfg.get("pary", []):
        for c, ds in pair_hits(tr, p["a"], p["b"], p["dni"], today - timedelta(days=days - 1), today).items():
            if not ds:
                continue
            k = (p["a"], p["b"])
            old = out[c].get(k)
            if old is None or p["przewaga"] > old["przewaga"]:
                out[c][k] = {"a": LABELS[p["a"]], "b": LABELS[p["b"]], "dni": p["dni"], "przewaga": p["przewaga"], "data": max(ds).isoformat()}
    return {c: sorted(v.values(), key=lambda x: -x["przewaga"]) for c, v in out.items()}


def gate(index: dict, hits: dict[str, set[date]], days: int = 14, threshold: float = 40.0) -> dict:
    """Indeks z bramką: wartość ≥ progu zostaje tylko przy zbieżności śladów w `days` dni przed tygodniem."""
    out = {}
    for (c, t), v in index.items():
        ok = v < threshold or any(t - timedelta(days=i) in hits.get(c, ()) for i in range(days))
        out[(c, t)] = v if ok else min(v, threshold - 0.1)
    return out


def _pct(x):
    return "brak" if x is None else f"{x:.0%}"


def _lift(x):
    return "brak" if x is None else f"{x:.1f}×"


def _name(a, b, L):
    return LABELS[a] if b is None else f"{LABELS[a]} → {LABELS[b]} (do {L} dni)"


def write(path: str, res: dict, meta: str, scan: dict | None = None) -> None:
    L = [f"# Łączenie śladów: test historyczny ({date.today().isoformat()})", "",
         "Zbieżność: w oknie W dni w kraju pojawiły się nowe sprawy (bez przedruków) z co najmniej K różnych kanałów "
         "(" + ", ".join(LABELS.values()) + "). Kolejne dni zbieżności w odstępie do 7 dni to jeden epizod. "
         "Precyzja: odsetek epizodów, po których w ciągu 60 dni nastąpiło wydarzenie w tym kraju. Przewaga = precyzja / odsetek "
         "zwykłych dni kraju, po których nastąpiło wydarzenie.", "", meta, ""]
    if scan:
        tr_rows, te_idx, rule = scan["uczenie"], scan["test"], scan["regula"]
        key = lambda r: (r["a"], r["b"], r["lag"])
        L += ["## Które ślady i pary śladów poprzedzają wydarzenia", "",
              "Para „A → B (do L dni)”: ślad B pojawia się, gdy ślad A był w tym kraju w ciągu L dni wcześniej (z innej sprawy). "
              "Przewaga liczona na latach 2019–2024, potem sprawdzona na 2025–2026, których dobór nie widział. "
              "„Ściągnięta” przewaga uwzględnia małą liczbę epizodów.", "",
              "### Pojedyncze kanały", "", "| kanał | epizodów 2019–24 | precyzja | przewaga | epizodów 2025–26 | precyzja | przewaga |", "|---|---|---|---|---|---|---|"]
        for r in [r for r in tr_rows if r["b"] is None]:
            t = te_idx.get(key(r), {})
            L.append(f"| {LABELS[r['a']]} | {r['ocenionych']} | {_pct(r['precyzja'])} | {_lift(r['lift'])} | {t.get('ocenionych', 0)} | "
                     f"{_pct(t.get('precyzja'))} | {_lift(t.get('lift'))} |")
        pairs = sorted([r for r in tr_rows if r["b"] is not None], key=shrunk_lift, reverse=True)
        L += ["", "### Najlepsze pary na latach 2019–2024 i jak wypadły w 2025–2026", "",
              "| para | epizodów 2019–24 | precyzja | przewaga (ściągnięta) | epizodów 2025–26 | precyzja | przewaga |", "|---|---|---|---|---|---|---|"]
        for r in pairs[:15]:
            t = te_idx.get(key(r), {})
            L.append(f"| {_name(*key(r))} | {r['ocenionych']} | {_pct(r['precyzja'])} | {_lift(shrunk_lift(r))} | {t.get('ocenionych', 0)} | "
                     f"{_pct(t.get('precyzja'))} | {_lift(t.get('lift'))} |")
        top = [te_idx.get(key(r)) for r in pairs[:15]]
        ok = sum(1 for t in top if t and t.get("lift") and t["lift"] > 1)
        L += ["", f"Z 15 najlepszych par z lat 2019–2024 w 2025–2026 przewagę ponad 1× utrzymało {ok} (pozostałe: brak epizodów albo gorzej niż losowo).",
              "", "### Najsłabsze pary (2019–2024)", "", "| para | epizodów | precyzja | przewaga (ściągnięta) |", "|---|---|---|---|"]
        for r in pairs[-8:]:
            L.append(f"| {_name(*key(r))} | {r['ocenionych']} | {_pct(r['precyzja'])} | {_lift(shrunk_lift(r))} |")
        L += ["", "### Reguła z wyuczonymi wagami par", "",
              f"Alarm, gdy w kraju zaszła para, której ściągnięta przewaga na latach 2019–2024 wynosi co najmniej P. Próg wybrany na latach uczenia: P = {rule['prog']}.", "",
              "| P | epizodów 2019–24 | precyzja | przewaga | epizodów 2025–26 | precyzja | przewaga | wydarzeń złapanych ≤30 dni przed (2025–26) |",
              "|---|---|---|---|---|---|---|---|"]
        for thr, a, b in rule["wyniki"]:
            n = b["wydarzen"] or 1
            L.append(f"| {thr} | {a['ocenionych']} | {_pct(a['precyzja'])} | {_lift(a['lift'])} | {b['ocenionych']} | {_pct(b['precyzja'])} | "
                     f"{_lift(b['lift'])} | {b['w30']} z {b['wydarzen']} ({b['w30'] / n:.0%}) |")
        L.append("")
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
    periods = [("Lata 2019–2024 (wydarzenia z listy 2015–2024)", load_events("wydarzenia_2015_2024.csv"), d("2019-03-01"), d("2024-12-31")),
               (f"Test 2025-03 – {date.today():%Y-%m} (wydarzenia 2025–2026)", load_events("wydarzenia.csv"), d("2025-03-01"), date.today())]
    # 1) korelacje: pojedyncze kanały i pary z opóźnieniem, uczenie na 2019-2024, sprawdzenie na 2025-2026
    (_, ev_tr, s_tr, e_tr), (_, ev_te, s_te, e_te) = periods
    scan_tr = pair_scan(tr_all, ev_tr, s_tr, e_tr)
    scan_te = pair_scan(tr_all, ev_te, s_te, e_te, min_eps=0)
    te_idx = {(r["a"], r["b"], r["lag"]): r for r in scan_te}
    weights = {(r["a"], r["b"], r["lag"]): shrunk_lift(r) for r in scan_tr if r["b"] is not None}
    print(f"pary: {len(scan_tr)} ({time.time() - t0:.0f} s)", flush=True)
    rule_rows = []
    for thr in (1.5, 2.0, 2.5, 3.0):
        ra = evaluate(weighted_hits(tr_all, weights, thr, s_tr, e_tr), tr_all, ev_tr, s_tr, e_tr)
        rb = evaluate(weighted_hits(tr_all, weights, thr, s_te, e_te), tr_all, ev_te, s_te, e_te)
        rule_rows.append((thr, ra, rb))
        print(f"  reguła P{thr}: uczenie {ra}, test {rb}", flush=True)
    cand = [(thr, ra) for thr, ra, _ in rule_rows if ra["ocenionych"] >= 30 and ra["precyzja"] is not None]
    best = max(cand, key=lambda x: x[1]["precyzja"])[0] if cand else 2.0
    scan = {"uczenie": scan_tr, "test": te_idx, "regula": {"prog": best, "wyniki": rule_rows}}
    # 2) zbieżność K kanałów i bramka
    res = {}
    for label, evs, s, e in periods:
        rows = []
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
                out[f"bramka: {var}, 2 kanały w 14 dniach"] = _counts(bt_eval(gate(idx, daily(tr_all, s - timedelta(days=14), e, 7, 2, var)), evs))
            out[f"bramka: wyuczone pary (P {best}) w 14 dniach"] = _counts(bt_eval(gate(idx, weighted_hits(tr_all, weights, best, s - timedelta(days=14), e)), evs))
            res[label]["bramka"] = out
            print(f"  bramka {label[:10]}: { {k: (v['prawdziwe'], v['falszywe'], v['hit_rate']) for k, v in out.items()} }", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write(a.out, res, meta, scan)
    best_pairs = sorted(((k, v) for k, v in weights.items() if v >= best), key=lambda x: -x[1])
    with open(os.path.join(os.path.dirname(os.path.abspath(a.out)), "slady-pary.json"), "w", encoding="utf-8") as f:
        import json
        json.dump({"prog": best, "pary": [{"a": k[0], "b": k[1], "dni": k[2], "przewaga": round(v, 2)} for k, v in best_pairs]}, f, ensure_ascii=False, indent=1)
    print(open(a.out, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
