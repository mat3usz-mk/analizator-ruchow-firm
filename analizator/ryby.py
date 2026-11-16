"""Ślady dobrze poinformowanych („grube ryby”): legalne, publiczne dane o tym, gdzie stawiają pieniądze ci, którzy wiedzą więcej.

- Krótka sprzedaż funduszy krajowych w USA (FINRA Reg SHO, dziennie, historia od lat): ktoś gra na spadek giełdy danego kraju.
- Nietypowe opcje put na fundusze krajowe (Nasdaq, dziennie; historię budujemy sami od dnia włączenia).
- Zgody USA na sprzedaż broni (DSCA, oficjalne komunikaty z nazwą kraju).
- Transakcje kongresmenów USA (zgłoszenia PTR w Izbie Reprezentantów): zakupy i sprzedaż spółek zbrojeniowych, energetycznych,
  lotniczych i żeglugowych. Kongresmeni mają dostęp do niejawnych odpraw, a zgłaszają transakcje z opóźnieniem do 45 dni.

Nie ma tu: 13F (portfele funduszy są jawne dopiero 45–135 dni po fakcie, za późno na wczesny sygnał), przepływów kryptowalut
„wielorybów” (darmowe źródła nie oznaczają adresów giełd, a płatne kosztują kilkaset dolarów miesięcznie) ani lobbingu
(zgłoszenia kwartalne, serwer Senatu niedostępny w czasie sprawdzania).

    python -m analizator.ryby --od 2022-01-01 --db ryby_historia.db     # historia do testu (krótka sprzedaż, DSCA)

NIE jest to rekomendacja inwestycyjna. Dane są publiczne; to, że ktoś coś kupił, nie znaczy, że wiedział więcej.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta

from .oficjalne import _item, _name, _once_a_day

UA = {"User-Agent": "Mozilla/5.0 (analizator ruchow firm; public data)", "Accept": "application/json, text/plain, */*"}

# Fundusze ETF notowane w USA, które odzwierciedlają giełdę jednego kraju
COUNTRY_ETF = {"TW": "EWT", "KR": "EWY", "CN": "FXI", "HK": "EWH", "JP": "EWJ", "IN": "INDA", "IL": "EIS", "TR": "TUR",
               "BR": "EWZ", "MX": "EWW", "ZA": "EZA", "SA": "KSA", "PL": "EPOL", "DE": "EWG", "FR": "EWQ", "GB": "EWU",
               "PH": "EPHE", "ID": "EIDO", "VN": "VNM", "TH": "THD", "MY": "EWM", "SG": "EWS", "AR": "ARGT", "CL": "ECH",
               "QA": "QAT", "AE": "UAE", "IT": "EWI", "ES": "EWP", "SE": "EWD", "NO": "NORW", "AU": "EWA", "CA": "EWC"}


def _get(url: str, timeout: int = 60, tries: int = 3, headers: dict | None = None) -> bytes:
    err = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers or UA), timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            err = e
        except Exception as e:
            err = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url[:90]}: {err}")


# --- Krótka sprzedaż (FINRA Reg SHO, wolumen dzienny) ----------------------------------------------------
def short_volume_day(d: date) -> dict[str, tuple[float, float]]:
    """{ETF: (wolumen krótkiej sprzedaży, wolumen całkowity)} dla funduszy krajowych w danym dniu (pusty w dni bez sesji)."""
    try:
        txt = _get(f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt", 60).decode("utf-8", "ignore")
    except Exception:
        return {}
    want = set(COUNTRY_ETF.values())
    out = {}
    for line in txt.splitlines()[1:]:
        p = line.split("|")
        if len(p) >= 5 and p[1] in want:
            try:
                out[p[1]] = (float(p[2]), float(p[4]))
            except ValueError:
                pass
    return out


def short_series(start: date, end: date, con=None) -> dict[str, dict[date, tuple[float, float]]]:
    """Szereg dzienny; z bazą `con` zapisuje dni w tabeli metrics (źródło finra_sv / finra_tv), żeby nie pobierać ich ponownie."""
    series: dict[str, dict[date, tuple[float, float]]] = defaultdict(dict)
    if con is not None:
        con.execute("CREATE TABLE IF NOT EXISTS metrics (source TEXT, key TEXT, day TEXT, value REAL, PRIMARY KEY (source, key, day))")
        for src, k, day, v in con.execute("SELECT source, key, day, value FROM metrics WHERE source IN ('finra_sv','finra_tv') AND day>=?",
                                          (start.isoformat(),)):
            sv, tv = series[k].get(date.fromisoformat(day), (0.0, 0.0))
            series[k][date.fromisoformat(day)] = (v, tv) if src == "finra_sv" else (sv, v)
        have = {d for s in series.values() for d in s}
    else:
        have = set()
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in have:
            day = short_volume_day(d)
            for etf, (sv, tv) in day.items():
                series[etf][d] = (sv, tv)
                if con is not None:
                    con.execute("INSERT OR REPLACE INTO metrics VALUES ('finra_sv',?,?,?)", (etf, d.isoformat(), sv))
                    con.execute("INSERT OR REPLACE INTO metrics VALUES ('finra_tv',?,?,?)", (etf, d.isoformat(), tv))
            if con is not None:
                con.commit()
        d += timedelta(days=1)
    return series


def short_signals(series: dict[str, dict[date, tuple[float, float]]], start: date, end: date) -> list[dict]:
    """Sygnał: w ostatnich 5 sesjach udział krótkiej sprzedaży o co najmniej 12 pkt proc. wyższy niż mediana z 60 sesji
    wcześniej I wolumen co najmniej 1,5 raza większy niż zwykle (sama zmiana udziału przy małym obrocie to szum)."""
    by_etf = {v: k for k, v in COUNTRY_ETF.items()}
    out = []
    for etf, s in series.items():
        days = sorted(s)
        last = None
        for i in range(65, len(days)):
            d = days[i]
            if not start <= d <= end:
                continue
            win, base = days[i - 4:i + 1], days[i - 65:i - 5]
            sv, tv = sum(s[x][0] for x in win), sum(s[x][1] for x in win)
            if tv <= 0:
                continue
            ratio = sv / tv
            b_ratio = statistics.median(s[x][0] / s[x][1] for x in base if s[x][1] > 0)
            b_vol = statistics.median(s[x][1] for x in base) * 5
            if ratio >= b_ratio + 0.12 and tv >= 1.5 * b_vol and (last is None or (d - last).days >= 14):
                last = d
                c = by_etf[etf]
                out.append(_item(f"https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data?etf={etf}",
                                 f"Short selling in {_name(c)} stock market fund ({etf}) jumps to {100 * ratio:.0f}% of volume from "
                                 f"usual {100 * b_ratio:.0f}%, trading {tv / b_vol:.1f}x normal; investors bet on a fall (FINRA)",
                                 d, "finra_short", "finra.org", c))
    return out


# --- Nietypowe opcje put na fundusze krajowe (Nasdaq) ----------------------------------------------------
def options_today(etf: str) -> tuple[float, float] | None:
    """(wolumen put, wolumen call) dziś, ze wszystkich terminów do 60 dni."""
    q = urllib.parse.urlencode({"assetclass": "etf", "limit": 2000, "fromdate": date.today().isoformat(),
                                "todate": (date.today() + timedelta(days=60)).isoformat(), "money": "all"})
    js = json.loads(_get(f"https://api.nasdaq.com/api/quote/{etf}/option-chain?{q}", 30))
    rows = (((js.get("data") or {}).get("table") or {}).get("rows")) or []
    num = lambda x: float(str(x).replace(",", "")) if x not in (None, "", "--") else 0.0
    puts = sum(num(r.get("p_Volume")) for r in rows)
    calls = sum(num(r.get("c_Volume")) for r in rows)
    return (puts, calls) if rows else None


def live_options(con, days: int = 7) -> list[dict]:
    """Raz dziennie zapisuje wolumen opcji; sygnał, gdy put ≥ 3x mediana z 20 poprzednich pomiarów i put/call ≥ 1,5."""
    if not _once_a_day(con, "opcje"):
        return []
    today = date.today().isoformat()
    out = []
    for c, etf in COUNTRY_ETF.items():
        try:
            v = options_today(etf)
        except Exception as e:
            print(f"  [opcje] {etf}: {e}")
            continue
        if not v:
            continue
        puts, calls = v
        con.execute("INSERT OR REPLACE INTO metrics VALUES ('opcje_put',?,?,?)", (etf, today, puts))
        con.execute("INSERT OR REPLACE INTO metrics VALUES ('opcje_call',?,?,?)", (etf, today, calls))
        hist = [x for (x,) in con.execute("SELECT value FROM metrics WHERE source='opcje_put' AND key=? AND day<? ORDER BY day DESC LIMIT 20",
                                          (etf, today))]
        if len(hist) >= 10:
            med = statistics.median(hist)
            if med > 0 and puts >= 3 * med and puts >= 1.5 * max(calls, 1) and puts >= 2000:
                out.append(_item(f"https://www.nasdaq.com/market-activity/etf/{etf.lower()}/option-chain",
                                 f"Unusual put options on {_name(c)} stock market fund ({etf}): {puts:,.0f} puts today, "
                                 f"{puts / med:.1f}x usual, put/call {puts / max(calls, 1):.1f}; bets on a fall (options market)",
                                 date.today(), "opcje", "nasdaq.com", c))
        time.sleep(1)
    con.commit()
    return out


# --- Zgody USA na sprzedaż broni (DSCA) ------------------------------------------------------------------
DSCA_RSS = "https://www.dsca.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=700&Site=1509&max={n}"


def dsca(start: date, end: date, n: int = 1000) -> list[dict]:
    from .signals import detect_countries
    root = ET.fromstring(_get(DSCA_RSS.format(n=n), 90))
    out = []
    for it in root.iter("item"):
        title, link, pub = (it.findtext(k) or "" for k in ("title", "link", "pubDate"))
        try:
            d = datetime.strptime(pub[:16].strip(), "%a, %d %b %Y").date()
        except ValueError:
            continue
        head = re.split(r"\s[–-]\s", title, maxsplit=1)[0]  # „Taiwan – MQ-9B…”: kraj przed myślnikiem
        found = detect_countries(head) or detect_countries(title)
        if not found or not start <= d <= end:
            continue
        out.append(_item(link or "https://www.dsca.mil/Press-Media/Major-Arms-Sales/",
                         f"US approves possible arms sale to {_name(found[0])}: {title.strip()[:150]} (DSCA)", d, "dsca", "dsca.mil", found[0]))
    return out


# --- Transakcje kongresmenów (Izba Reprezentantów, zgłoszenia PTR) ---------------------------------------
WATCH = {  # spółki, w których zakupy/sprzedaż przed kryzysem miałyby sens
    "zbrojeniówka": {"LMT", "RTX", "NOC", "GD", "LHX", "HII", "BA", "PLTR", "LDOS", "KTOS", "AVAV", "TXT", "BAH", "CACI", "SAIC"},
    "energia": {"XOM", "CVX", "COP", "OXY", "EOG", "HAL", "SLB", "LNG", "DVN", "MPC", "VLO", "PSX", "XLE", "USO"},
    "lotnictwo i turystyka": {"DAL", "UAL", "AAL", "LUV", "CCL", "RCL", "NCLH", "BKNG", "EXPE", "MAR", "HLT"},
    "żegluga": {"ZIM", "MATX", "FRO", "DHT", "STNG", "INSW"},
    "półprzewodniki (Tajwan)": {"TSM", "NVDA", "AMD", "AAPL", "QCOM", "AVGO", "INTC", "MU", "ASML"},
}
_TX = re.compile(r"\(([A-Z][A-Z.]{0,5})\)\s*(?:\[[A-Z]{2}\])?\s*(P|S|S \(partial\)|E)\s+(\d{2}/\d{2}/\d{4})", re.S)


def house_ptr_index(year: int) -> list[dict]:
    raw = _get(f"https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip", 120)
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.endswith(".txt"))
    rows = []
    for line in z.read(name).decode("utf-8", "ignore").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 9 and p[4].strip() == "P":
            try:
                rows.append({"kto": f"{p[2].strip()} {p[1].strip()} ({p[5].strip()})", "zgloszono": datetime.strptime(p[7].strip(), "%m/%d/%Y").date(),
                             "doc": p[8].strip(), "rok": year})
            except ValueError:
                continue
    return rows


def ptr_trades(doc: str, year: int) -> list[tuple[str, str, date]]:
    """[(ticker, typ P/S, data transakcji)] z PDF zgłoszenia (wymaga pakietu pypdf)."""
    from pypdf import PdfReader
    raw = _get(f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf", 60)
    text = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    text = re.sub(r"\s+", " ", text.replace("\x00", ""))
    out = []
    for m in _TX.finditer(text):
        try:
            out.append((m.group(1).replace(".", "-"), m.group(2)[0], datetime.strptime(m.group(3), "%m/%d/%Y").date()))
        except ValueError:
            continue
    return out


def live_congress(con, days: int = 45) -> list[dict]:
    """Raz dziennie: nowe zgłoszenia PTR z Izby Reprezentantów, transakcje w obserwowanych spółkach do tabeli kongres."""
    con.execute("CREATE TABLE IF NOT EXISTS kongres (doc TEXT, kto TEXT, ticker TEXT, typ TEXT, data TEXT, zgloszono TEXT, "
                "PRIMARY KEY (doc, ticker, typ, data))")
    con.execute("CREATE TABLE IF NOT EXISTS kongres_doc (doc TEXT PRIMARY KEY)")
    if not _once_a_day(con, "kongres"):
        return []
    try:
        import pypdf  # noqa: F401
    except ImportError:
        print("  [kongres] brak pakietu pypdf (pip install pypdf)")
        return []
    since = date.today() - timedelta(days=days)
    idx = [r for y in {since.year, date.today().year} for r in house_ptr_index(y) if r["zgloszono"] >= since]
    seen = {d for (d,) in con.execute("SELECT doc FROM kongres_doc")}
    new = [r for r in idx if r["doc"] not in seen]
    watched = set().union(*WATCH.values())
    for r in new[:150]:  # limit na jeden dzień; reszta jutro
        try:
            for t, typ, d in ptr_trades(r["doc"], r["rok"]):
                if t in watched:
                    con.execute("INSERT OR IGNORE INTO kongres VALUES (?,?,?,?,?,?)", (r["doc"], r["kto"], t, typ, d.isoformat(), r["zgloszono"].isoformat()))
            con.execute("INSERT OR IGNORE INTO kongres_doc VALUES (?)", (r["doc"],))
        except Exception as e:
            print(f"  [kongres] {r['doc']}: {e}")
        time.sleep(0.3)
    con.commit()
    print(f"  [kongres] przeczytano {min(len(new), 150)} nowych zgłoszeń z {len(new)}")
    return []  # tylko panel w raporcie (nie wpływa na indeks krajów, dopóki nie zostanie sprawdzone na historii)


def congress_panel(con, days: int = 60) -> list[dict]:
    """Podsumowanie do raportu: ilu kongresmenów kupowało / sprzedawało spółki z każdej grupy w ostatnich `days` dniach."""
    try:
        rows = con.execute("SELECT kto, ticker, typ, data FROM kongres WHERE data>=?", ((date.today() - timedelta(days=days)).isoformat(),)).fetchall()
    except Exception:
        return []
    out = []
    for grp, tick in WATCH.items():
        buy = sorted({(k, t) for k, t, typ, _ in rows if t in tick and typ == "P"})
        sell = sorted({(k, t) for k, t, typ, _ in rows if t in tick and typ == "S"})
        if buy or sell:
            out.append({"grupa": grp, "kupujacy": len({k for k, _ in buy}), "sprzedajacy": len({k for k, _ in sell}),
                        "spolki_kupno": sorted({t for _, t in buy}), "spolki_sprzedaz": sorted({t for _, t in sell})})
    return out


# --- Na żywo i historia ---------------------------------------------------------------------------------
def live_short(con, days: int = 10) -> list[dict]:
    if not _once_a_day(con, "finra_short"):
        return []
    end = date.today() - timedelta(days=1)
    series = short_series(end - timedelta(days=100), end, con)
    return short_signals(series, end - timedelta(days=days), end)


def live_dsca(con, days: int = 14) -> list[dict]:
    if not _once_a_day(con, "dsca"):
        return []
    return dsca(date.today() - timedelta(days=days), date.today(), n=50)


def history(start: date, end: date, which: set[str]) -> list[dict]:
    out = []
    if "dsca" in which:
        try:
            out += dsca(start, end)
        except Exception as e:
            print(f"  [dsca] {e}")
    if "finra_short" in which:
        series = short_series(start - timedelta(days=100), end)
        out += short_signals(series, start, end)
    return out


def main(argv=None) -> int:
    from . import store
    ap = argparse.ArgumentParser(prog="analizator.ryby")
    ap.add_argument("--od", default="2022-01-01")
    ap.add_argument("--do", default=date.today().isoformat())
    ap.add_argument("--db", default="ryby_historia.db")
    ap.add_argument("--zrodla", default="finra_short,dsca")
    a = ap.parse_args(argv)
    items = history(date.fromisoformat(a.od), date.fromisoformat(a.do), set(a.zrodla.split(",")))
    con = store.connect(a.db)
    print(f"zapisano {store.save(con, items)} z {len(items)}")
    for src, n in con.execute("SELECT source, COUNT(*) FROM articles GROUP BY 1"):
        print(f"  {src}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
