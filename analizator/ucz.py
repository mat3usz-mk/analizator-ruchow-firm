"""Uczenie maszynowe: wagi sygnałów i kalibracja indeksu na danych historycznych.

Zamiast ręcznie dobranych wag model (regresja logistyczna, bez bibliotek zewnętrznych) uczy się,
które składowe oceny kraju naprawdę poprzedzały wydarzenia. Daje to SKALIBROWANĄ szansę wydarzenia
w kraju w ciągu `horizon` dni (np. 60), a nie tylko indeks uwagi.

Uczciwy podział: model uczy się na latach 2015-2024 (wydarzenia_2015_2024.csv), a sprawdzany jest
na 2025-2026 (wydarzenia.csv), których w czasie uczenia nie widzi. Każdy tydzień liczony jest tylko
z danych dostępnych do tego tygodnia (bez zaglądania w przyszłość).

    python -m analizator.ucz --db historia_gkg.db --train-events wydarzenia_2015_2024.csv \\
        --test-events wydarzenia.csv --train-from 2015-05-01 --train-to 2024-12-31 --test-from 2025-03-01
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import time
from collections import defaultdict
from datetime import date, timedelta

from .signals import CATEGORIES

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.json")
CATS = sorted(CATEGORIES)
FEATURES = ["indeks_reczny", "odchylenie_z", "nowi_aktorzy_z", "nowe_kategorie", "ciche_nadwyzka", "priorytet_nadwyzka",
            "udzial_wyprzedzajacych", "dominacja_jednej_firmy", "log_wynik_tygodnia", "log_sygnaly_priorytetowe",
            "log_firmy", "log_panstwa", "dlugosc_historii"] + [f"kat_{c}" for c in CATS]
LABELS_PL = {
    "indeks_reczny": "obecny indeks (ręczne wagi)", "odchylenie_z": "odchylenie od normy kraju",
    "nowi_aktorzy_z": "więcej różnych firm i państw niż zwykle", "nowe_kategorie": "więcej typów ruchów niż zwykle",
    "ciche_nadwyzka": "ciche sygnały ponad normę", "priorytet_nadwyzka": "sygnały priorytetowe ponad normę",
    "udzial_wyprzedzajacych": "udział ruchów wyprzedzających", "dominacja_jednej_firmy": "jedna firma dominuje",
    "log_wynik_tygodnia": "siła sygnałów w tygodniu", "log_sygnaly_priorytetowe": "liczba sygnałów priorytetowych",
    "log_firmy": "liczba firm", "log_panstwa": "liczba państw", "dlugosc_historii": "długość historii kraju",
}


def features(r) -> list[float]:
    """Wektor cech z oceny kraju (CountryAssessment). Te same cechy na żywo i w uczeniu."""
    p = r.parts or {}
    clip = lambda x, lo, hi: max(lo, min(hi, x))
    cats = set(r.categories)
    return [
        r.own_index / 100 if r.own_index else r.index / 100,
        clip(p.get("z", 0.0), -2, 6),
        clip(p.get("z_act", 0.0), -2, 6),
        clip(p.get("cats", 0) - max(p.get("cats_base", 0.0), 1.0), -3, 6),
        clip(p.get("quiet_excess", 0.0), 0, 4),
        clip(p.get("prio_excess", 0.0), 0, 5),
        p.get("proactive", 0.0),
        p.get("dominance", 0.0),
        math.log1p(max(r.recent_score, 0.0)),
        math.log1p(p.get("prio_now", 0)),
        math.log1p(r.companies),
        math.log1p(r.states),
        min(len(r.weekly), 26) / 26,
    ] + [1.0 if c in cats else 0.0 for c in CATS]


# --- Regresja logistyczna (bez numpy) -------------------------------------------
def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def fit(X: list[list[float]], y: list[int], l2: float = 1e-2, iters: int = 400, lr: float = 0.5) -> dict:
    n, d = len(X), len(X[0])
    mean = [sum(row[j] for row in X) / n for j in range(d)]
    std = [math.sqrt(sum((row[j] - mean[j]) ** 2 for row in X) / n) or 1.0 for j in range(d)]
    Z = [[(row[j] - mean[j]) / std[j] for j in range(d)] for row in X]
    w, b = [0.0] * d, math.log((sum(y) + 0.5) / (n - sum(y) + 0.5))
    # Adam: stabilnie i szybko przy niezbalansowanych klasach
    mw, vw, mb, vb = [0.0] * d, [0.0] * d, 0.0, 0.0
    b1, b2, eps = 0.9, 0.999, 1e-8
    for t in range(1, iters + 1):
        gw, gb = [0.0] * d, 0.0
        for zi, yi in zip(Z, y):
            e = _sig(b + sum(a * c for a, c in zip(w, zi))) - yi
            gb += e
            for j in range(d):
                gw[j] += e * zi[j]
        gw = [g / n + l2 * wj for g, wj in zip(gw, w)]
        gb /= n
        mw = [b1 * m + (1 - b1) * g for m, g in zip(mw, gw)]
        vw = [b2 * v + (1 - b2) * g * g for v, g in zip(vw, gw)]
        mb, vb = b1 * mb + (1 - b1) * gb, b2 * vb + (1 - b2) * gb * gb
        a = lr * 0.1 * math.sqrt(1 - b2 ** t) / (1 - b1 ** t)
        w = [wj - a * m / (math.sqrt(v) + eps) for wj, m, v in zip(w, mw, vw)]
        b -= a * mb / (math.sqrt(vb) + eps)
    return {"features": FEATURES, "mean": mean, "std": std, "w": w, "b": b}


def predict(model: dict, x: list[float]) -> float:
    z = model["b"] + sum(wj * (xj - m) / s for wj, xj, m, s in zip(model["w"], x, model["mean"], model["std"]))
    return _sig(z)


_MODEL: dict | None = None


def load_model(path: str = MODEL_PATH) -> dict | None:
    global _MODEL
    if _MODEL is None and os.path.exists(path):
        try:
            _MODEL = json.load(open(path, encoding="utf-8"))
            if _MODEL.get("features") != FEATURES:
                _MODEL = None  # model z innej wersji cech: nie używamy
        except (OSError, ValueError):
            _MODEL = None
    return _MODEL


# --- Zbiór danych ------------------------------------------------------------------
def build_rows(signals: list[dict], events: list[dict], start: date, end: date, horizon: int = 60,
               step_days: int = 7, window_days: int = 210) -> list[dict]:
    """Dla każdego tygodnia i kraju: cechy z danych do tego dnia i etykieta (wydarzenie w kolejnych `horizon` dniach)."""
    from .score import assess
    signals = sorted(signals, key=lambda s: s["date"])
    dates = [s["date"] for s in signals]
    ev_by_c: dict[str, list[date]] = defaultdict(list)
    for e in events:
        ev_by_c[e["kraj"]].append(e["data"])
    rows, t, t0 = [], start, time.time()
    while t <= end:
        lo, hi = bisect.bisect_left(dates, t - timedelta(days=window_days)), bisect.bisect_right(dates, t)
        for r in assess(signals[lo:hi], today=t, use_model=False):
            y = int(any(t < d <= t + timedelta(days=horizon) for d in ev_by_c.get(r.country, ())))
            recent = any(t - timedelta(days=90) < d <= t for d in ev_by_c.get(r.country, ()))
            rows.append({"t": t, "kraj": r.country, "x": features(r), "y": y, "indeks": r.index, "po_wydarzeniu": recent})
        t += timedelta(days=step_days)
    print(f"  {len(rows)} wierszy {start}..{end} w {time.time() - t0:.0f} s", flush=True)
    return rows


# --- Ocena ------------------------------------------------------------------------
def auc(scores: list[float], y: list[int]) -> float | None:
    pos = sum(y)
    neg = len(y) - pos
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return (sum(r for r, yy in zip(ranks, y) if yy) - pos * (pos + 1) / 2) / (pos * neg)


def calibration(p: list[float], y: list[int], edges=(0, .05, .1, .2, .3, .5, 1.01)) -> list[tuple]:
    out = []
    for a, b in zip(edges, edges[1:]):
        idx = [i for i, v in enumerate(p) if a <= v < b]
        if idx:
            out.append((f"{a:.0%}–{min(b, 1):.0%}", len(idx), sum(p[i] for i in idx) / len(idx), sum(y[i] for i in idx) / len(idx)))
    return out


def compare(rows: list[dict], model: dict, events: list[dict], hand_thr: float, model_thr: float, horizon: int) -> dict:
    from .backtest import evaluate
    p = [predict(model, r["x"]) for r in rows]
    y = [r["y"] for r in rows]
    hand = [r["indeks"] for r in rows]
    fresh = [i for i, r in enumerate(rows) if not r["po_wydarzeniu"]]
    hand_idx = {(r["kraj"], r["t"]): r["indeks"] for r in rows}
    model_idx = {(r["kraj"], r["t"]): 100 * pi for r, pi in zip(rows, p)}
    ev_h = evaluate(hand_idx, events, threshold=hand_thr, horizon=horizon)
    ev_m = evaluate(model_idx, events, threshold=100 * model_thr, horizon=horizon)
    base = sum(y) / max(len(y), 1)
    brier = lambda q: sum((a - b) ** 2 for a, b in zip(q, y)) / max(len(y), 1)
    return {
        "wiersze": len(rows), "z_wydarzeniem": sum(y), "czestosc_bazowa": base,
        "auc_reczny": auc(hand, y), "auc_model": auc(p, y),
        "auc_reczny_zaskoczenie": auc([hand[i] for i in fresh], [y[i] for i in fresh]),
        "auc_model_zaskoczenie": auc([p[i] for i in fresh], [y[i] for i in fresh]),
        "brier_model": brier(p), "brier_staly": brier([base] * len(y)),
        "kalibracja": calibration(p, y),
        "reczny": {k: ev_h[k] for k in ("hit_rate", "hit_rate_fresh", "n_fresh", "n_events", "precision", "median_lead")},
        "model": {k: ev_m[k] for k in ("hit_rate", "hit_rate_fresh", "n_fresh", "n_events", "precision", "median_lead")},
    }


def _matching_threshold(rows: list[dict], model: dict, hand_thr: float) -> float:
    """Próg modelu dający na zbiorze UCZĄCYM tyle samo alarmów co ręczny indeks przy swoim progu (uczciwe porównanie)."""
    n_alarm = sum(r["indeks"] >= hand_thr for r in rows)
    p = sorted((predict(model, r["x"]) for r in rows), reverse=True)
    return p[min(max(n_alarm - 1, 0), len(p) - 1)] if p else 0.5


def _fmt(x, pct=True):
    return "brak" if x is None else (f"{x:.0%}" if pct else f"{x:.2f}")


def write_report(path: str, model: dict, tr: dict, te: dict, args) -> None:
    imp = sorted(zip(FEATURES, model["w"]), key=lambda t: -abs(t[1]))
    name = lambda f: LABELS_PL.get(f, f.replace("kat_", "kategoria: "))
    L = [f"# Model uczony na historii ({date.today().isoformat()})", "",
         f"Uczenie: {args.train_from}..{args.train_to}, test (model go nie widział): {args.test_from}..{args.test_to}. "
         f"Horyzont: wydarzenie w ciągu {args.horizon} dni. Dane: {os.path.basename(args.db)}.", "",
         "| | uczenie | **test** |", "|---|---|---|",
         f"| wiersze (kraj × tydzień) | {tr['wiersze']} | {te['wiersze']} |",
         f"| z wydarzeniem w horyzoncie | {tr['z_wydarzeniem']} ({_fmt(tr['czestosc_bazowa'])}) | {te['z_wydarzeniem']} ({_fmt(te['czestosc_bazowa'])}) |",
         f"| AUC ręczny indeks | {_fmt(tr['auc_reczny'], False)} | {_fmt(te['auc_reczny'], False)} |",
         f"| **AUC model** | {_fmt(tr['auc_model'], False)} | **{_fmt(te['auc_model'], False)}** |",
         f"| AUC ręczny, tylko kraje bez wydarzenia w ostatnich 90 dniach | {_fmt(tr['auc_reczny_zaskoczenie'], False)} | {_fmt(te['auc_reczny_zaskoczenie'], False)} |",
         f"| **AUC model, tylko kraje bez wydarzenia w ostatnich 90 dniach** | {_fmt(tr['auc_model_zaskoczenie'], False)} | **{_fmt(te['auc_model_zaskoczenie'], False)}** |",
         f"| Brier model / stała częstość (niżej = lepiej) | {tr['brier_model']:.4f} / {tr['brier_staly']:.4f} | {te['brier_model']:.4f} / {te['brier_staly']:.4f} |",
         "", "AUC: 0,5 = losowo, 1,0 = idealnie. Mówi, czy kraje przed wydarzeniem dostają wyższą ocenę niż pozostałe.", "",
         f"## Wydarzenia w teście (ręczny indeks przy progu {args.threshold:.0f} kontra model przy progu dającym tyle samo alarmów, {model['prog']:.0%})", "",
         "| | ręczny | model |", "|---|---|---|"]
    for k, lab in (("hit_rate", "trafione wydarzenia"), ("hit_rate_fresh", "trafione z zaskoczenia"),
                   ("precision", "trafne alarmy (precyzja)"), ("median_lead", "mediana wyprzedzenia (dni)")):
        a, b = te["reczny"][k], te["model"][k]
        L.append(f"| {lab} | {a if k == 'median_lead' else _fmt(a)} | {b if k == 'median_lead' else _fmt(b)} |")
    L += ["", "## Kalibracja na teście (czy „20%” znaczy 20%)", "", "| szansa wg modelu | tygodni | średnio przewidziane | naprawdę z wydarzeniem |", "|---|---|---|---|"]
    L += [f"| {b} | {n} | {pp:.1%} | {yy:.1%} |" for b, n, pp, yy in te["kalibracja"]]
    L += ["", "## Czego model się nauczył (wagi po standaryzacji, największe pierwsze)", "",
          "Dodatnia waga: cecha podnosi szansę wydarzenia. Ujemna: obniża ją (często szum).", ""]
    L += [f"- {name(f)}: {w:+.2f}" for f, w in imp[:15]]
    L += ["", "Model to wskazówka, nie wyrocznia: wydarzeń jest mało, a lista wydarzeń 2015–2024 była spisana z wiedzy ogólnej.",
          "Nie jest to rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv: list[str] | None = None) -> int:
    from . import store
    from .backtest import load_events
    from .score import extract_signals
    ap = argparse.ArgumentParser(prog="analizator.ucz")
    ap.add_argument("--db", required=True)
    ap.add_argument("--train-events", default="wydarzenia_2015_2024.csv")
    ap.add_argument("--test-events", default="wydarzenia.csv")
    ap.add_argument("--train-from", default="2015-05-01")
    ap.add_argument("--train-to", default="2024-12-31")
    ap.add_argument("--test-from", default="2025-03-01")
    ap.add_argument("--test-to", default=date.today().isoformat())
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--threshold", type=float, default=40.0)
    ap.add_argument("--out-model", default=MODEL_PATH)
    ap.add_argument("--out-report", default="raporty/model-wyniki.md")
    ap.add_argument("--watchlist", default="watchlist.txt")
    args = ap.parse_args(argv)
    wl = [l.strip() for l in open(args.watchlist, encoding="utf-8") if l.strip() and not l.startswith("#")] if os.path.exists(args.watchlist) else None
    t0 = time.time()
    arts = store.load(store.connect(args.db))
    print(f"{len(arts)} artykułów, wyciągam sygnały...", flush=True)
    sig = extract_signals(arts, wl)
    print(f"{len(sig)} sygnałów w {time.time() - t0:.0f} s", flush=True)
    ev_tr, ev_te = load_events(args.train_events), load_events(args.test_events)
    d = date.fromisoformat
    tr = build_rows(sig, ev_tr, d(args.train_from), d(args.train_to), args.horizon)
    te = build_rows(sig, ev_te, d(args.test_from), d(args.test_to), args.horizon)
    # Etykiety testowe tylko z wydarzeń testowych, a uczące tylko z uczących; tygodnie, których horyzont wychodzi poza listę, odpadają.
    tr = [r for r in tr if r["t"] + timedelta(days=args.horizon) <= d(args.train_to)]
    te = [r for r in te if r["t"] + timedelta(days=args.horizon) <= d(args.test_to)]
    model = fit([r["x"] for r in tr], [r["y"] for r in tr])
    model["prog"] = _matching_threshold(tr, model, args.threshold)
    model.update({"horyzont_dni": args.horizon, "uczenie": [args.train_from, args.train_to], "test": [args.test_from, args.test_to],
                  "utworzono": date.today().isoformat()})
    r_tr = compare(tr, model, ev_tr, args.threshold, model["prog"], args.horizon)
    r_te = compare(te, model, ev_te, args.threshold, model["prog"], args.horizon)
    model["wyniki_test"] = {k: r_te[k] for k in ("auc_reczny", "auc_model", "auc_model_zaskoczenie", "brier_model", "brier_staly")}
    model["kalibracja_test"] = r_te["kalibracja"]
    os.makedirs(os.path.dirname(os.path.abspath(args.out_report)), exist_ok=True)
    with open(args.out_model, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=1)
    write_report(args.out_report, model, r_tr, r_te, args)
    print(open(args.out_report, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
