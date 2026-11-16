"""Sprawdzenie na danych, czy wskazywane indeksy giełdowe naprawdę szły w podanym kierunku po dawnych alarmach.

Dla każdego epizodu alarmowego z historii (kraj, tydzień początku) bierzemy indeksy, które raport wskazałby
„w górę” i „w dół” (skutki.indices), i liczymy zmianę notowań w kolejnych `--dni` dniach (domyślnie 30).
Od zmiany odejmujemy zwykłą, przeciętną zmianę tego indeksu w dowolnych 30 dniach (żeby długi trend wzrostowy
nie udawał trafności). Kierunek „sprawdził się”, gdy nadwyżka ma właściwy znak.

Wynik trafia do analizator/rynki.json; raport pokazuje potem tylko kierunki, które sprawdzały się częściej niż
w połowie przypadków (z liczbą przypadków), a te, które się nie sprawdzały, ukrywa.

    python -m analizator.rynki --epizody raporty/epizody.json --out analizator/rynki.json --raport raporty/rynki-wyniki.md

Notowania: publiczne dane dzienne (Yahoo Finance, w razie braku stooq). To sprawdzenie typowych reakcji,
a nie prognoza cen. NIE jest to rekomendacja inwestycyjna.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import os
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rynki.json")

# Klucz etykiety (jak w skutki._uniq) -> notowania do sprawdzenia. Każda pozycja: lista kandydatów; kandydat to
# lista (symbol, znak) uśredniana jako koszyk. Znak -1: kierunek odwrotny (np. EUR/PLN w górę = PLN w dół).
TICKERS: dict[str, list[list[tuple[str, int]]]] = {
    "ropa brent": [[("BZ=F", 1)]],
    "gaz ttf": [[("TTF=F", 1)]],
    "złoto": [[("GC=F", 1)]],
    "indeks zmienności vix": [[("^VIX", 1)]],
    "frank szwajcarski": [[("EURCHF=X", -1)]],
    "obligacje usa i niemiec": [[("^TNX", -1)]],  # w górę ceny obligacji = rentowność w dół
    "kurs pln i walut regionu": [[("EURPLN=X", -1)]],
    "pszenica i kukurydza": [[("ZW=F", 1), ("ZC=F", 1)]],
    "miedź, aluminium, nikiel": [[("HG=F", 1)]],
    "s&p 500 energy": [[("XLE", 1)]],
    "s&p aerospace & defense select": [[("XAR", 1)]],
    "stoxx europe total market aerospace & defense": [[("RHM.DE", 1), ("BA.L", 1), ("SAAB-B.ST", 1), ("LDO.MI", 1)]],
    "rheinmetall, saab, kongsberg": [[("RHM.DE", 1), ("SAAB-B.ST", 1), ("KOG.OL", 1)]],
    "frachty kontenerowe": [[("MAERSK-B.CO", 1), ("HLAG.DE", 1), ("ZIM", 1)]],  # przez akcje armatorów
    "baltic dirty tanker index": [[("FRO", 1), ("DHT", 1)]],  # przez akcje armatorów tankowców
    "nawozy": [[("NTR", 1), ("CF", 1)]],
    "stoxx europe 600 oil & gas": [[("^SXEP", 1)], [("EXH1.DE", 1)]],
    "stoxx europe 600 travel & leisure": [[("^SXTP", 1)], [("EXV9.DE", 1)]],
    "stoxx europe 600 chemicals": [[("^SX4P", 1)], [("EXV7.DE", 1)]],
    "stoxx europe 600 utilities": [[("^SX6P", 1)], [("EXH9.DE", 1)]],
    "stoxx europe 600 retail": [[("^SXRP", 1)], [("EXH8.DE", 1)]],
    "stoxx europe 600 automobiles & parts": [[("^SXAP", 1)], [("EXV5.DE", 1)]],
    "stoxx europe 600 food & beverage": [[("^SX3P", 1)], [("EXH3.DE", 1)]],
    "stoxx europe 600 basic resources": [[("^SXPP", 1)], [("EXV6.DE", 1)]],
    "stoxx europe 600 banks": [[("^SX7P", 1)], [("EXV1.DE", 1)]],
    "phlx semiconductor": [[("^SOX", 1)]],
    "nasdaq 100": [[("^NDX", 1)]],
    "msci emerging markets": [[("EEM", 1)]],
    "dax": [[("^GDAXI", 1)]], "cac 40": [[("^FCHI", 1)]], "ftse 100": [[("^FTSE", 1)]],
    "wig20": [[("WIG20.WA", 1)], [("stooq:wig20", 1)]], "mwig40": [[("stooq:mwig40", 1)]],
    "omx helsinki 25": [[("^OMXH25", 1)]], "omx stockholm 30": [[("^OMX", 1)]], "obx": [[("OBX.OL", 1)]], "obx oslo": [[("OBX.OL", 1)]],
    "bux": [[("^BUX.BD", 1)]], "px": [[("stooq:^px", 1)]], "bet": [[("stooq:^bet", 1)]],
    "bist 100": [[("XU100.IS", 1)]], "ta-35": [[("TA35.TA", 1)], [("^TA125.TA", 1)]], "tadawul all share": [[("^TASI.SR", 1)]],
    "egx 30": [[("^CASE30", 1)]], "moex russia": [[("IMOEX.ME", 1)]],
    "taiex": [[("^TWII", 1)]], "kospi": [[("^KS11", 1)]], "nikkei 225": [[("^N225", 1)]], "hang seng": [[("^HSI", 1)]],
    "csi 300 i hang seng": [[("000300.SS", 1), ("^HSI", 1)]], "nifty 50 i sensex": [[("^NSEI", 1)]], "kse-100": [[("^KSE", 1)]],
    "straits times": [[("^STI", 1)]], "jakarta composite": [[("^JKSE", 1)]], "ftse bursa malaysia klci": [[("^KLSE", 1)]],
    "set index": [[("^SET.BK", 1)]], "psei": [[("PSEI.PS", 1)]], "ibovespa": [[("^BVSP", 1)]], "s&p merval": [[("^MERV", 1)]],
    "s&p/bmv ipc": [[("^MXX", 1)]], "ftse/jse top 40": [[("^J200.JO", 1)], [("STX40.JO", 1)]],
}

MIN_N = 5        # mniej przypadków: „za mało danych”, pokazujemy bez oceny
MIN_HIT = 0.55   # kierunek pokazujemy jako sprawdzony od tego odsetka trafień


def key(label: str) -> str:
    return label.split(" (")[0].split(":")[0].strip().lower()


# --- Notowania ------------------------------------------------------------------
def _yahoo(sym: str, start: date) -> dict[date, float]:
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?period1={p1}"
           f"&period2={int(time.time())}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (analizator ruchow firm)"})
    js = json.loads(urllib.request.urlopen(req, timeout=30).read())
    r = js["chart"]["result"][0]
    closes = r["indicators"]["quote"][0]["close"]
    return {datetime.fromtimestamp(t, timezone.utc).date(): c for t, c in zip(r["timestamp"], closes) if c}


def _stooq(sym: str, start: date) -> dict[date, float]:
    url = f"https://stooq.com/q/d/l/?s={urllib.request.quote(sym)}&d1={start:%Y%m%d}&i=d"
    txt = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode()
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        try:
            out[date.fromisoformat(row["Date"])] = float(row["Close"])
        except (KeyError, ValueError):
            continue
    return out


_CACHE: dict[str, dict[date, float] | None] = {}


def prices(sym: str, start: date) -> dict[date, float] | None:
    if sym not in _CACHE:
        data, err = None, None
        for attempt in range(3):
            try:
                data = _stooq(sym[6:], start) if sym.startswith("stooq:") else _yahoo(sym, start)
                break
            except Exception as e:  # brak symbolu, limit zapytań, sieć
                err = e
                time.sleep(2 + 3 * attempt)
        if not data or len(data) < 200:
            print(f"  [{sym}] brak notowań" + (f": {err}" if err else ""), flush=True)
            data = None
        _CACHE[sym] = data
        time.sleep(0.5)
    return _CACHE[sym]


class Series:
    def __init__(self, data: dict[date, float]):
        self.d = sorted(data)
        self.v = [data[x] for x in self.d]

    def ret(self, t: date, days: int) -> float | None:
        i = bisect.bisect_left(self.d, t)
        j = bisect.bisect_left(self.d, t + timedelta(days=days))
        if i >= len(self.d) or j >= len(self.d) or (self.d[i] - t).days > 5 or j <= i:
            return None
        return self.v[j] / self.v[i] - 1

    def drift(self, days: int) -> float:
        rs = [r for t in self.d[::5] if (r := self.ret(t, days)) is not None]
        return sum(rs) / len(rs) if rs else 0.0


def basket(label_key: str, start: date) -> tuple[list[tuple[Series, int, float]], str] | None:
    for cand in TICKERS.get(label_key, []):
        got = [(prices(s, start), sign) for s, sign in cand]
        got = [(Series(p), sign) for p, sign in got if p]
        if got:
            return [(s, sign, 0.0) for s, sign in got], "+".join(sym for sym, _ in cand)
    return None


# --- Ocena -----------------------------------------------------------------------
def evaluate(episodes: list[dict], days: int = 30) -> dict:
    from .skutki import FRONTS, FRONT_INDICES, indices
    if not episodes:
        return {}
    start = date.fromisoformat(min(e["data"] for e in episodes)) - timedelta(days=400)
    stats: dict[str, dict] = {}
    baskets: dict[str, tuple | None] = {}
    for e in episodes:
        c, t = e["kraj"], date.fromisoformat(e["data"])
        pairs = []
        for lvl in ("podwyższony", "wysoki"):
            ix = indices(c, lvl, verified=False)
            pairs += [(l, "up") for l in ix["up"]] + [(l, "down") for l in ix["down"]]
        for fk, (_, members) in FRONTS.items():
            if c in members:
                u, d = FRONT_INDICES.get(fk, ([], []))
                pairs += [(l, "up") for l in u] + [(l, "down") for l in d]
        for lab, direction in dict.fromkeys(pairs):
            k = key(lab)
            if k not in baskets:
                b = basket(k, start)
                if b:
                    for i, (s, sign, _) in enumerate(b[0]):
                        b[0][i] = (s, sign, s.drift(days))
                baskets[k] = b
            st = stats.setdefault(f"{k}|{direction}", {"key_dir": direction, "n": 0, "trafne": 0, "nadwyzka": 0.0, "kraje": defaultdict(int),
                                                      "symbol": baskets[k][1] if baskets[k] else None})
            if not baskets[k]:
                continue
            rs = [(r - dr) * sign for s, sign, dr in baskets[k][0] if (r := s.ret(t, days)) is not None]
            if not rs:
                continue
            ex = sum(rs) / len(rs)
            st["n"] += 1
            st["trafne"] += (ex > 0) if direction == "up" else (ex < 0)
            st["nadwyzka"] += ex
            st["kraje"][c] += 1
    for st in stats.values():
        st["nadwyzka"] = round(st["nadwyzka"] / st["n"], 4) if st["n"] else None
        st["kraje"] = dict(sorted(st["kraje"].items(), key=lambda t: -t[1])[:8])
    return stats


def verdict(st: dict | None) -> str:
    if not st or not st.get("symbol"):
        return "brak notowań"
    if st["n"] < MIN_N:
        return "za mało danych"
    # trafny kierunek w większości przypadków I średnio we właściwą stronę (inaczej to przypadek)
    sign_ok = st.get("nadwyzka") is not None and (st["nadwyzka"] > 0) == (st["key_dir"] == "up") if "key_dir" in st else True
    return "sprawdza się" if st["trafne"] / st["n"] >= MIN_HIT and sign_ok else "nie sprawdza się"


def write_report(path: str, stats: dict, meta: dict) -> None:
    rows = sorted(stats.items(), key=lambda kv: (-(kv[1]["n"] >= MIN_N), -(kv[1]["trafne"] / kv[1]["n"] if kv[1]["n"] else 0)))
    L = [f"# Indeksy giełdowe po dawnych alarmach ({date.today().isoformat()})", "",
         f"Epizody alarmowe: {meta['n_epizodow']} ({meta['okres']}, reguła alarmu: {meta['regula']}). Dla każdego epizodu liczona jest "
         f"zmiana notowań w {meta['dni']} dniach od początku alarmu, pomniejszona o przeciętną zmianę tego indeksu w dowolnych {meta['dni']} dniach.",
         f"Kierunek uznajemy za sprawdzony, gdy był trafny w co najmniej {MIN_HIT:.0%} z co najmniej {MIN_N} przypadków. "
         "Takie kierunki raport pokazuje z liczbą trafień, a niesprawdzające się ukrywa.", "",
         "| indeks | kierunek | przypadki | trafne | średnia nadwyżka | ocena | notowania |", "|---|---|---|---|---|---|---|"]
    for k, st in rows:
        lab, d = k.split("|")
        hit = f"{st['trafne']}/{st['n']} ({st['trafne'] / st['n']:.0%})" if st["n"] else "-"
        ex = f"{st['nadwyzka']:+.1%}" if st["nadwyzka"] is not None else "-"
        L.append(f"| {lab} | {'▲ w górę' if d == 'up' else '▼ w dół'} | {st['n']} | {hit} | {ex} | {verdict(st)} | {st['symbol'] or 'brak'} |")
    L += ["", "Uwagi: epizody w tym samym czasie (np. kilka krajów Bliskiego Wschodu naraz) nie są od siebie niezależne, więc liczba "
          "przypadków zawyża pewność. Koszyki akcji (armatorzy, zbrojeniówka, nawozy) zastępują indeksy, których notowań nie ma za darmo.",
          "To sprawdzenie typowych reakcji w przeszłości, nie prognoza cen. Nie jest to rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# --- Użycie w raporcie --------------------------------------------------------------
_RES: dict | None = None


def results(path: str = RESULTS_PATH) -> dict:
    global _RES
    if _RES is None:
        try:
            _RES = json.load(open(path, encoding="utf-8")).get("wyniki", {})
        except (OSError, ValueError):
            _RES = {}
    return _RES


def annotate(labels: list[str], direction: str) -> list[str]:
    """Zostawia kierunki sprawdzone na danych (z liczbą trafień) i te, których nie da się sprawdzić; ukrywa niesprawdzające się."""
    res = results()
    if not res:
        return labels
    out = []
    for lab in labels:
        st = res.get(f"{key(lab)}|{direction}")
        v = verdict(st)
        if v == "nie sprawdza się":
            continue
        if v == "sprawdza się":
            out.append(f"{lab} [sprawdziło się {st['trafne']} z {st['n']} razy]")
        elif v == "za mało danych":
            out.append(f"{lab} [za mało przypadków do sprawdzenia]")
        else:
            out.append(f"{lab} [niesprawdzone, brak notowań]")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.rynki")
    ap.add_argument("--epizody", required=True)
    ap.add_argument("--dni", type=int, default=30)
    ap.add_argument("--out", default=RESULTS_PATH)
    ap.add_argument("--raport", default="raporty/rynki-wyniki.md")
    a = ap.parse_args(argv)
    ep = json.load(open(a.epizody, encoding="utf-8"))
    eps = ep["epizody"]
    stats = evaluate(eps, a.dni)
    meta = {"n_epizodow": len(eps), "okres": f"{eps[0]['data']}..{eps[-1]['data']}" if eps else "-", "regula": ep.get("regula", "?"),
            "dni": a.dni, "utworzono": date.today().isoformat()}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({**meta, "wyniki": stats}, f, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(os.path.abspath(a.raport)), exist_ok=True)
    write_report(a.raport, stats, meta)
    print(open(a.raport, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
