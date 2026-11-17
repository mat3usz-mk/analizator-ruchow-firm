"""Test historyczny insiderów: czy nietypowe transakcje zarządów spółek zbrojeniowych i energetycznych z USA (Form 4)
wyprzedzają konflikty i ruchy kursów ich branży.

Dane: kwartalne zbiory SEC „Insider Transactions Data Sets” (Form 3/4/5, od 2006 r.), wymagają SEC_USER_AGENT.
Liczymy tygodniowe sumy zakupów (kod P) i sprzedaży (kod S) na otwartym rynku w grupie spółek. Anomalia: tydzień z sumą
co najmniej 3× powyżej mediany z 26 poprzednich tygodni (i powyżej progu kwotowego).

    python -m analizator.insiderzy_test --od 2019 --out raporty/insiderzy-wyniki.md
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import statistics
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, timedelta

URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
GROUPS = {
    "zbrojeniowe": (["LMT", "RTX", "NOC", "GD", "LHX", "BA", "HII", "LDOS", "KTOS", "AVAV"], "ITA"),
    "energetyczne": (["XOM", "CVX", "COP", "LNG", "OXY", "HAL", "SLB", "KMI", "EOG", "PSX"], "XLE"),
}
MIN_USD = {"P": 200_000, "S": 5_000_000}


def _week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_quarter(y: int, q: int, ua: str, cache: str) -> list[tuple]:
    """(symbol, data transakcji, kod, wartość USD) dla spółek z GROUPS."""
    path = os.path.join(cache, f"{y}q{q}.zip")
    if not os.path.exists(path):
        req = urllib.request.Request(URL.format(y=y, q=q), headers={"User-Agent": ua})
        try:
            data = urllib.request.urlopen(req, timeout=180).read()
        except Exception as e:
            print(f"  {y}q{q}: {e}", flush=True)
            return []
        open(path, "wb").write(data)
        time.sleep(1)
    want = {t for ts, _ in GROUPS.values() for t in ts}
    z = zipfile.ZipFile(path)
    names = {n.split("/")[-1].upper(): n for n in z.namelist()}
    sub = {}
    with z.open(names["SUBMISSION.TSV"]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, "utf-8", errors="replace"), delimiter="\t"):
            sym = (r.get("ISSUERTRADINGSYMBOL") or "").upper().strip()
            if sym in want:
                sub[r["ACCESSION_NUMBER"]] = sym
    out = []
    with z.open(names["NONDERIV_TRANS.TSV"]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, "utf-8", errors="replace"), delimiter="\t"):
            sym = sub.get(r["ACCESSION_NUMBER"])
            code = r.get("TRANS_CODE")
            if not sym or code not in ("P", "S"):
                continue
            try:
                usd = float(r.get("TRANS_SHARES") or 0) * float(r.get("TRANS_PRICEPERSHARE") or 0)
                d = _parse(r.get("TRANS_DATE", ""))
            except ValueError:
                continue
            if d and usd > 0:
                out.append((sym, d, code, usd))
    return out


def _parse(s: str) -> date | None:
    from datetime import datetime
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip()[:11], fmt).date()
        except ValueError:
            continue
    return None


def anomalies(tx: list[tuple], start: date, end: date) -> dict:
    """{(grupa, kod): [tygodnie z anomalią]} oraz tygodniowe serie."""
    sym2g = {t: g for g, (ts, _) in GROUPS.items() for t in ts}
    weekly = defaultdict(lambda: defaultdict(float))
    for sym, d, code, usd in tx:
        weekly[(sym2g[sym], code)][_week(d)] += usd
    out = {}
    for k, ser in weekly.items():
        wk = _week(start - timedelta(weeks=30))
        weeks = []
        while wk <= end:
            weeks.append(wk)
            wk += timedelta(weeks=1)
        vals = [ser.get(w, 0.0) for w in weeks]
        hits = []
        for i in range(26, len(weeks)):
            if weeks[i] < start:
                continue
            med = statistics.median(vals[i - 26:i])
            if vals[i] >= max(3 * med, MIN_USD[k[1]]):
                hits.append(weeks[i])
        out[k] = {"anomalie": hits, "tygodnie": [w for w in weeks if w >= start]}
    return out


def evaluate(an: dict, events: list[dict], horizon: int = 30) -> list[dict]:
    from .rynki import Series, prices
    types = {"zbrojeniowe": {"konflikt"}, "energetyczne": {"kryzys_energetyczny", "blokada"}}
    rows = []
    for (g, code), v in sorted(an.items()):
        conflicts = sorted(e["data"] for e in events if (e.get("typ") or "").strip() in types[g])
        etf = GROUPS[g][1]
        p = prices(etf, min(v["tygodnie"]) - timedelta(days=30)) if v["tygodnie"] else None
        s = Series(p) if p else None
        follow = lambda w: any(w < d <= w + timedelta(days=horizon) for d in conflicts)
        base = sum(follow(w) for w in v["tygodnie"]) / len(v["tygodnie"]) if v["tygodnie"] else None
        hit = sum(follow(w) for w in v["anomalie"])
        rets = [r for w in v["anomalie"] if s and (r := s.ret(w + timedelta(days=7), horizon)) is not None]
        allr = [r for w in v["tygodnie"] if s and (r := s.ret(w + timedelta(days=7), horizon)) is not None]
        avg = lambda xs: sum(xs) / len(xs) if xs else None
        rows.append({"grupa": g, "kod": "zakupy" if code == "P" else "sprzedaż", "etf": etf, "tygodni": len(v["tygodnie"]),
                     "anomalii": len(v["anomalie"]), "konflikt_po": hit, "precyzja": hit / len(v["anomalie"]) if v["anomalie"] else None,
                     "baza": base, "etf_po": avg(rets), "etf_zwykle": avg(allr),
                     "etf_wzrost": sum(1 for r in rets if r > 0) / len(rets) if rets else None})
    return rows


def write(path: str, rows_by_period: dict, n_tx: int) -> None:
    pct = lambda x: "brak" if x is None else f"{x:.0%}"
    pp = lambda x: "brak" if x is None else f"{x * 100:+.1f}%".replace(".", ",")
    L = [f"# Insiderzy spółek zbrojeniowych i energetycznych z USA: test historyczny ({date.today().isoformat()})", "",
         f"Dane: zbiory SEC Form 3/4/5, {n_tx} transakcji na otwartym rynku (zakupy P, sprzedaż S) w 20 spółkach. "
         "Anomalia: tydzień z sumą co najmniej 3× powyżej mediany z 26 tygodni (zakupy od 0,2 mln USD, sprzedaż od 5 mln USD). "
         "Wydarzenie w ciągu 30 dni (dowolny kraj): dla zbrojeniowych konflikt, dla energetycznych kryzys energetyczny albo blokada. Kurs ETF branży (ITA, XLE) liczony od tygodnia po anomalii, 30 dni.", ""]
    for period, rows in rows_by_period.items():
        L += [f"## {period}", "", "| grupa | transakcje | tygodni z anomalią | wydarzenie w 30 dni po anomalii | zwykle (każdy tydzień) | ETF 30 dni po anomalii | ETF zwykle | ETF w górę po anomalii |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['grupa']} | {r['kod']} | {r['anomalii']} z {r['tygodni']} | {r['konflikt_po']} ({pct(r['precyzja'])}) | {pct(r['baza'])} | "
                     f"{pp(r['etf_po'])} | {pp(r['etf_zwykle'])} | {pct(r['etf_wzrost'])} |")
        L.append("")
    L += ["Jak czytać: jeśli „wydarzenie w 30 dni po anomalii” jest wyraźnie wyższy od „zwykle”, nietypowe transakcje insiderów coś zapowiadały. "
          "To samo dla kursu ETF. Mała liczba anomalii oznacza duży błąd przypadku. To test historyczny, nie rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None) -> int:
    from .backtest import load_events
    ap = argparse.ArgumentParser(prog="analizator.insiderzy_test")
    ap.add_argument("--od", type=int, default=2019)
    ap.add_argument("--cache", default="sec_insider_zip")
    ap.add_argument("--out", default="raporty/insiderzy-wyniki.md")
    a = ap.parse_args(argv)
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        print("brak SEC_USER_AGENT")
        return 2
    import unicodedata
    ua = unicodedata.normalize("NFKD", ua.replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode()
    os.makedirs(a.cache, exist_ok=True)
    tx = []
    today = date.today()
    for y in range(a.od - 1, today.year + 1):
        for q in range(1, 5):
            if date(y, 3 * q - 2, 1) > today - timedelta(days=100):
                continue  # zbiór za kwartał pojawia się po jego zakończeniu
            part = load_quarter(y, q, ua, a.cache)
            print(f"  {y}q{q}: {len(part)} transakcji", flush=True)
            tx += part
    d = date.fromisoformat
    periods = {"Lata 2019–2024 (wydarzenia z listy 2015–2024)": ("wydarzenia_2015_2024.csv", d(f"{a.od}-03-01"), d("2024-12-31")),
               "Test 2025–2026 (wydarzenia 2025–2026)": ("wydarzenia.csv", d("2025-03-01"), today - timedelta(days=35))}
    res = {}
    for label, (csv_path, s, e) in periods.items():
        res[label] = evaluate(anomalies(tx, s, e), load_events(csv_path))
        for r in res[label]:
            print(" ", label[:10], r, flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write(a.out, res, len(tx))
    print(open(a.out, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
