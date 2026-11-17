"""Źródła pierwotne: informacje u źródła, zanim (albo zamiast tego, że) trafią do artykułów.

Każde źródło zwraca rekordy w tym samym kształcie co wiadomości (url, title, date, source, domain),
więc dalej przechodzą przez te same reguły i ocenę. Tytuły źródeł "liczbowych" (ruch lotniczy,
przetargi, zmiany poziomu ostrzeżeń) są opisem pomiaru, np. "Air traffic over Iran down 72% vs
14-day norm", a nie zmyślonym nagłówkiem.

Źródła i domeny (muszą być dozwolone w środowisku):
- ESPI/EBI (raporty bieżące spółek z GPW i NewConnect) ......... www.stockwatch.pl
- Ostrzeżenia dla podróżnych USA (poziomy 1-4) .................. travel.state.gov
- Ostrzeżenia dla podróżnych Wielkiej Brytanii (FCDO) ........... www.gov.uk
- Biuletyny o strefach konfliktu EASA (CZIB) .................... www.easa.europa.eu
- Zakazy i ograniczenia lotów FAA ................................ www.faa.gov
- Sankcje OFAC (Recent Actions) .................................. ofac.treasury.gov
- Przetargi obronne w UE (TED, CPV 35*) .......................... api.ted.europa.eu
- Ruch lotniczy nad krajami (OpenSky, bez konta 400 kredytów/dzień) opensky-network.org
- Transakcje insiderów w USA (Form 4) ............................ www.sec.gov (już dozwolone)
- Ruch statków przez cieśniny (AIS, klucz AISSTREAM_API_KEY) ...... stream.aisstream.io

Większość z nich działa tylko "na żywo" (pokazuje stan obecny), więc historia buduje się
z każdym codziennym uruchomieniem i nie da się ich odtworzyć w teście na 2025 r.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import statistics
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .sources import _get, sec_user_agent
from .signals import COUNTRIES, detect_countries
from . import limit

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (source TEXT, key TEXT, value TEXT, day TEXT, PRIMARY KEY (source, key, day));
CREATE TABLE IF NOT EXISTS metrics (source TEXT, key TEXT, day TEXT, value REAL, PRIMARY KEY (source, key, day));
"""

# Kody ISO-3 używane w adresach travel.state.gov -> ISO-2 jak w COUNTRIES
ISO3 = {
    "ukr": "UA", "rus": "RU", "blr": "BY", "twn": "TW", "chn": "CN", "irn": "IR", "isr": "IL", "lbn": "LB", "syr": "SY",
    "irq": "IQ", "yem": "YE", "sau": "SA", "qat": "QA", "are": "AE", "kwt": "KW", "omn": "OM", "tur": "TR", "geo": "GE",
    "arm": "AM", "aze": "AZ", "kaz": "KZ", "mda": "MD", "srb": "RS", "xkx": "XK", "kos": "XK", "bih": "BA", "ven": "VE", "guy": "GY",
    "cub": "CU", "pan": "PA", "prk": "KP", "kor": "KR", "jpn": "JP", "phl": "PH", "pak": "PK", "ind": "IN", "afg": "AF",
    "egy": "EG", "lby": "LY", "sdn": "SD", "eth": "ET", "som": "SO", "nga": "NG", "mli": "ML", "ner": "NE", "bfa": "BF",
    "cod": "CD", "moz": "MZ", "mmr": "MM", "bur": "MM", "pol": "PL", "deu": "DE", "ltu": "LT", "lva": "LV", "est": "EE", "fin": "FI",
    "swe": "SE", "nor": "NO", "dnk": "DK", "rou": "RO", "hun": "HU", "svk": "SK", "cze": "CZ", "zaf": "ZA", "arg": "AR",
    "bra": "BR", "mex": "MX", "isl": None,
}
ISO2_TO_3 = {v: k for k, v in ISO3.items() if v}

# Prostokąty (lamin, lomin, lamax, lomax) dla OpenSky. Celowo nie za duże: koszt rośnie z powierzchnią.
BBOX = {
    "UA": (45.0, 30.0, 51.5, 40.0), "IR": (26.0, 46.0, 38.0, 60.0), "IL": (29.5, 34.2, 33.3, 35.9), "LB": (33.0, 35.0, 34.7, 36.7),
    "TW": (21.8, 119.3, 25.4, 122.1), "QA": (24.4, 50.7, 26.3, 51.7), "AE": (22.6, 51.5, 26.1, 56.4), "IQ": (29.0, 38.8, 37.4, 48.6),
    "SA": (20.0, 39.0, 28.0, 50.0), "PK": (24.0, 61.0, 36.0, 75.0), "IN": (20.0, 72.0, 30.0, 82.0), "YE": (12.5, 42.5, 18.0, 53.0),
    "PL": (49.0, 14.1, 54.9, 24.2), "LT": (53.9, 21.0, 56.5, 26.9), "EE": (57.5, 21.7, 59.7, 28.2), "FI": (59.8, 20.5, 66.0, 31.6),
    "RO": (43.6, 20.2, 48.3, 29.7), "MD": (45.4, 26.6, 48.5, 30.2), "VE": (0.6, -73.4, 12.2, -59.8), "KR": (33.1, 124.6, 38.6, 131.0),
    "AF": (29.3, 60.5, 38.5, 74.9), "SY": (32.3, 35.7, 37.3, 42.4), "EG": (22.0, 25.0, 31.7, 36.9), "TR": (36.0, 26.0, 42.1, 44.8),
}

# Amerykańskie spółki wrażliwe na konflikty (Form 4 składają tylko spółki z USA, nie zagraniczne)
INSIDER_TICKERS = ["LMT", "RTX", "NOC", "GD", "LHX", "BA", "XOM", "CVX", "COP", "LNG", "OXY", "HAL", "SLB", "KMI"]


def _con(con: sqlite3.Connection) -> sqlite3.Connection:
    con.executescript(SCHEMA)
    return con


def _today() -> str:
    return date.today().isoformat()


def _item(url: str, title: str, d: str, source: str, domain: str, lang: str = "en") -> dict:
    return {"url": url, "title": " ".join(title.split())[:300], "date": d, "source": source, "domain": domain, "lang": lang}


def _changed(con: sqlite3.Connection, source: str, key: str, value: str) -> str | None:
    """Zapisuje dzisiejszą wartość. Zwraca poprzednią, jeśli była inna (None przy braku zmiany albo pierwszym razie)."""
    prev = con.execute("SELECT value FROM snapshots WHERE source=? AND key=? AND day<? ORDER BY day DESC LIMIT 1",
                       (source, key, _today())).fetchone()
    con.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)", (source, key, value, _today()))
    con.commit()
    return prev[0] if prev and prev[0] != value else None


# --- ESPI / EBI ---------------------------------------------------------------
def espi(con: sqlite3.Connection, days: int = 7) -> list[dict]:
    """Komunikaty ESPI/EBI spółek z GPW z kanałów RSS przeznaczonych do czytników.
    Kolejność: Bankier (wymaga domeny www.bankier.pl w środowisku), potem stockwatch.pl (bywa 403 dla automatów)."""
    feeds = [("https://www.bankier.pl/rss/espi.xml", "bankier.pl"),
             ("https://www.stockwatch.pl/komunikaty-spolek/rss.aspx?type=&c=&t=", "stockwatch.pl")]
    out, root, domain, errors = [], None, "", []
    for url, domain in feeds:
        try:
            root = ET.fromstring(_get(url, tries=2))
            break
        except Exception as e:
            errors.append(f"{domain}: {e}")
    if root is None:
        raise RuntimeError("; ".join(errors))
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        try:
            d = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except Exception:
            d = _today()
        out.append(_item(it.findtext("link") or "", title + " " + (it.findtext("description") or "")[:200], d, "espi", domain, "pl"))
    return out


# --- Ostrzeżenia dla podróżnych -----------------------------------------------
_LEVEL = re.compile(r"Level (\d)")
_LEVEL_TEXT = {4: "Level 4: Do Not Travel", 3: "Level 3: Reconsider Travel", 2: "Level 2: Exercise Increased Caution", 1: "Level 1"}


def travel_us(con: sqlite3.Connection, days: int = 7) -> list[dict]:
    """Sygnał tylko przy ZMIANIE poziomu ostrzeżenia (podniesienie = sygnał, obniżenie = osłabienie)."""
    _con(con)
    root = ET.fromstring(_get("https://travel.state.gov/_res/rss/TAsTWs.xml"))
    out = []
    for it in root.iter("item"):
        link = it.findtext("link") or ""
        m3 = re.search(r"destination\.([a-z]{3})\.html", link)
        iso2 = ISO3.get(m3.group(1)) if m3 else None
        lm = _LEVEL.search(it.findtext("title") or "")
        if not iso2 or not lm:
            continue
        level = lm.group(1)
        prev = _changed(con, "travel_us", iso2, level)
        if prev:
            name = COUNTRIES[iso2][0]
            if int(level) > int(prev):
                title = f"US State Department raises travel advisory for {name} to {_LEVEL_TEXT.get(int(level), 'Level ' + level)} (from Level {prev}); travel warning"
            else:
                title = f"US State Department lowers travel advisory for {name} to Level {level} (from Level {prev}), resumes normal travel"
            out.append(_item(link, title, _today(), "travel_us", "travel.state.gov"))
    return out


def travel_uk(con: sqlite3.Connection, days: int = 7) -> list[dict]:
    """FCDO: ostatnio zmienione porady dla podróżnych, z opisem zmiany."""
    q = urllib.parse.urlencode({"filter_format": "travel_advice", "order": "-public_timestamp", "count": 60,
                                "fields": "title,public_timestamp,link,description"})
    data = json.loads(_get(f"https://www.gov.uk/api/search.json?{q}"))
    out = []
    since = (date.today() - timedelta(days=days)).isoformat()
    for r in data.get("results", []):
        d = (r.get("public_timestamp") or "")[:10]
        if d < since:
            continue
        text = f"UK FCDO travel advice update: {r.get('title', '')}. {r.get('description', '')}"
        if re.search(r"against all (?:but essential )?travel|leave (?:now|immediately)|evacuat|embassy", text, re.I):
            out.append(_item("https://www.gov.uk" + r.get("link", ""), text + " (travel warning)", d, "travel_uk", "gov.uk"))
    return out


# --- Lotnictwo: EASA CZIB, FAA ------------------------------------------------
def _country_sections(text: str) -> dict[str, str]:
    """Dla każdego kraju: fragmenty tekstu wokół jego nazwy (do wykrywania zmian na stronie)."""
    out: dict[str, list[str]] = {}
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        for c in detect_countries(sent):
            out.setdefault(c, []).append(sent.strip())
    return {c: " ".join(v) for c, v in out.items()}


def _page_text(url: str) -> str:
    import html as _html
    raw = _get(url).decode("utf-8", "ignore")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    return _html.unescape(re.sub(r"(?s)<[^>]+>", "\n", raw))


def easa_czib(con: sqlite3.Connection, days: int = 7) -> list[dict]:
    _con(con)
    url = "https://www.easa.europa.eu/en/domains/air-operations/czibs"
    text = _page_text(url)
    out = []
    for c, sec in _country_sections(text).items():
        ids = sorted(set(re.findall(r"CZIB[-\s]?\d{4}[-\s]?\d+R?\d*", sec)))
        prev = _changed(con, "easa", c, ",".join(ids))
        if prev is not None:
            new = sorted(set(ids) - set(prev.split(",")))
            if new:
                out.append(_item(url, f"EASA issues conflict zone bulletin {', '.join(new)} for airspace of {COUNTRIES[c][0]}; airlines told to avoid airspace",
                                 _today(), "easa", "easa.europa.eu"))
    return out


def faa_restrictions(con: sqlite3.Connection, days: int = 7) -> list[dict]:
    _con(con)
    url = "https://www.faa.gov/air_traffic/publications/us_restrictions"
    text = _page_text(url)
    out = []
    for c, sec in _country_sections(text).items():
        h = hashlib.sha1(sec.encode()).hexdigest()[:16]
        if _changed(con, "faa", c, h):
            out.append(_item(url, f"FAA updates flight prohibitions and NOTAM for airspace of {COUNTRIES[c][0]} (FAA warning)",
                             _today(), "faa", "faa.gov"))
    return out


# --- Sankcje: OFAC ------------------------------------------------------------
def ofac(con: sqlite3.Connection, days: int = 30) -> list[dict]:
    url = "https://ofac.treasury.gov/recent-actions"
    raw = _get(url).decode("utf-8", "ignore")
    out = []
    since = date.today() - timedelta(days=days)
    for m in re.finditer(r'href="(/recent-actions/(\d{8})[^"]*)"[^>]*>(.*?)</a>', raw, re.S):
        d = datetime.strptime(m.group(2), "%Y%m%d").date()
        title = re.sub(r"<[^>]+>", " ", m.group(3))
        if d < since:
            continue
        out.append(_item("https://ofac.treasury.gov" + m.group(1), f"OFAC sanctions action: {title}", d.isoformat(), "ofac", "ofac.treasury.gov"))
    return out


# --- Przetargi obronne: TED ---------------------------------------------------
TED_COUNTRIES = ["POL", "LTU", "LVA", "EST", "FIN", "SWE", "DNK", "DEU", "ROU", "NOR"]


def ted_defence(con: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Liczba ogłoszeń przetargów na sprzęt obronny i bezpieczeństwa (CPV 35*) w ostatnich 30 dniach,
    porównana z tą samą liczbą z poprzednich pomiarów. Skok = sygnał zbrojenia (zwykle długofalowy)."""
    _con(con)
    out = []
    since = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
    for c3 in TED_COUNTRIES:
        body = json.dumps({"query": f"classification-cpv IN (35000000) AND buyer-country IN ({c3}) AND publication-date >= {since}",
                           "fields": ["publication-number"], "limit": 1, "page": 1}).encode()
        req = urllib.request.Request("https://api.ted.europa.eu/v3/notices/search", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "analizator-ruchow-firm/0.3"})
        try:
            limit.check()
            with urllib.request.urlopen(req, timeout=limit.left(30)) as r:
                n = float(json.loads(r.read()).get("totalNoticeCount", 0))
        except Exception as e:
            print(f"  [ted] {c3}: {e}")
            if "403" in str(e):
                break  # host zablokowany: nie męcz pozostałych krajów
            continue
        iso2 = ISO3.get(c3.lower())
        con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)", ("ted", iso2, _today(), n))
        con.commit()
        hist = [v for (v,) in con.execute("SELECT value FROM metrics WHERE source='ted' AND key=? AND day<? ORDER BY day DESC LIMIT 60",
                                           (iso2, _today()))]
        if len(hist) >= 14:
            med = statistics.median(hist)
            if med > 0 and n >= 1.6 * med and n - med >= 5:
                out.append(_item("https://ted.europa.eu", f"Defence procurement surge in {COUNTRIES[iso2][0]}: {int(n)} military tenders in 30 days "
                                 f"vs norm {med:.0f} (EU TED); stockpiling", _today(), "ted", "ted.europa.eu"))
        time.sleep(0.5)
    return out


# --- Ruch lotniczy: OpenSky ---------------------------------------------------
def opensky(con: sqlite3.Connection, days: int = 7) -> list[dict]:
    """Liczba samolotów w powietrzu nad krajem, porównana z medianą z 14 ostatnich pomiarów (o tej samej porze)."""
    _con(con)
    out = []
    for c, (la0, lo0, la1, lo1) in BBOX.items():
        url = f"https://opensky-network.org/api/states/all?lamin={la0}&lomin={lo0}&lamax={la1}&lomax={lo1}"
        try:
            states = json.loads(_get(url, tries=2)).get("states") or []
        except Exception as e:
            print(f"  [opensky] {c}: {e}")
            continue
        n = float(sum(1 for s in states if not s[8]))  # tylko w powietrzu
        con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)", ("opensky", c, _today(), n))
        con.commit()
        hist = [v for (v,) in con.execute("SELECT value FROM metrics WHERE source='opensky' AND key=? AND day<? ORDER BY day DESC LIMIT 14",
                                           (c, _today()))]
        if len(hist) >= 7:
            med = statistics.median(hist)
            if med >= 10 and n <= 0.5 * med:
                drop = round(100 * (1 - n / med))
                out.append(_item(f"https://opensky-network.org/#{c}", f"Air traffic over {COUNTRIES[c][0]} down {drop}% vs 14-day norm "
                                 f"({int(n)} aircraft vs {med:.0f}); airlines avoid airspace (OpenSky)", _today(), "opensky", "opensky-network.org"))
        time.sleep(1.0)
    return out


# --- Insiderzy: Form 4 --------------------------------------------------------
def insiders(con: sqlite3.Connection, days: int = 14) -> list[dict]:
    """Suma sprzedaży (kod S) i zakupów (kod P) akcji przez insiderów spółek zbrojeniowych i energetycznych z USA.

    Nie jest przypisana do kraju, więc nie wpływa na indeks krajów: trafia do osobnego panelu w raporcie
    (tabela metrics, źródło insider_sell / insider_buy).
    """
    _con(con)
    ua = sec_user_agent()
    if not ua:
        return []
    tickers = json.loads(_get("https://www.sec.gov/files/company_tickers.json", {"User-Agent": ua}))
    cik = {v["ticker"]: str(v["cik_str"]) for v in tickers.values()}
    since = date.today() - timedelta(days=days)
    for t in INSIDER_TICKERS:
        if t not in cik:
            continue
        atom = _get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik[t]}&type=4&dateb=&owner=include&count=40&output=atom",
                    {"User-Agent": ua})
        ns = {"a": "http://www.w3.org/2005/Atom"}
        sell = buy = 0.0
        for e in ET.fromstring(atom).findall("a:entry", ns):
            upd = (e.findtext("a:updated", default="", namespaces=ns) or "")[:10]
            if not upd or upd < since.isoformat():
                continue
            href = e.find("a:link", ns).get("href", "")
            idx_url = href if href.startswith("http") else "https://www.sec.gov" + href
            try:
                idx = _get(idx_url, {"User-Agent": ua}).decode("utf-8", "ignore")
                xml_path = re.search(r'href="(/Archives/[^"]+\.xml)"', idx)
                if not xml_path:
                    continue
                doc = ET.fromstring(_get("https://www.sec.gov" + xml_path.group(1), {"User-Agent": ua}))
            except Exception:
                continue
            for tr in doc.iter("nonDerivativeTransaction"):
                code = tr.findtext("transactionCoding/transactionCode") or ""
                try:
                    sh = float(tr.findtext("transactionAmounts/transactionShares/value") or 0)
                    px = float(tr.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
                except ValueError:
                    continue
                if code == "S":
                    sell += sh * px
                elif code == "P":
                    buy += sh * px
            time.sleep(0.15)
        con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)", ("insider_sell", t, _today(), sell))
        con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)", ("insider_buy", t, _today(), buy))
        con.commit()
    return []


def insider_panel(con: sqlite3.Connection) -> list[dict]:
    """Ostatni pomiar insiderów vs mediana poprzednich (do raportu)."""
    _con(con)
    rows = []
    for t in INSIDER_TICKERS:
        cur = con.execute("SELECT day, value FROM metrics WHERE source='insider_sell' AND key=? ORDER BY day DESC LIMIT 1", (t,)).fetchone()
        if not cur:
            continue
        hist = [v for (v,) in con.execute("SELECT value FROM metrics WHERE source='insider_sell' AND key=? AND day<? ORDER BY day DESC LIMIT 30",
                                           (t, cur[0]))]
        buy = con.execute("SELECT value FROM metrics WHERE source='insider_buy' AND key=? AND day=?", (t, cur[0])).fetchone()
        med = statistics.median(hist) if hist else None
        rows.append({"ticker": t, "day": cur[0], "sell": cur[1], "buy": buy[0] if buy else 0.0, "sell_norm": med,
                     "unusual": bool(med is not None and len(hist) >= 7 and cur[1] > 3 * max(med, 1e5))})
    return rows


FETCHERS = {
    "espi": espi, "travel_us": travel_us, "travel_uk": travel_uk, "easa": easa_czib, "faa": faa_restrictions,
    "ofac": ofac, "ted": ted_defence, "opensky": opensky, "insiders": insiders,
    "sankcje_ue_uk": lambda con, days=7: __import__("analizator.oficjalne", fromlist=["x"]).live_sanctions(con, days),
    "oficjalne_rss": lambda con, days=7: __import__("analizator.oficjalne", fromlist=["x"]).live_rss(con, days),
    # IODA (awarie internetu) wyłączone: w teście historycznym dawało ok. 60 fałszywych alarmów więcej bez żadnego trafienia
    "portwatch": lambda con, days=7: __import__("analizator.oficjalne", fromlist=["x"]).live_portwatch(con, days),
    "finra_short": lambda con, days=7: __import__("analizator.ryby", fromlist=["x"]).live_short(con, days),
    "opcje": lambda con, days=7: __import__("analizator.ryby", fromlist=["x"]).live_options(con, days),
    "dsca": lambda con, days=7: __import__("analizator.ryby", fromlist=["x"]).live_dsca(con, max(days, 14)),
    "kongres": lambda con, days=7: __import__("analizator.ryby", fromlist=["x"]).live_congress(con),
    "agsi": lambda con, days=7: __import__("analizator.oficjalne", fromlist=["x"]).live_agsi(con, days),
    # ACLED pominięte na żywo: darmowe konto daje dane opóźnione o 12 miesięcy (funkcja oficjalne.live_acled jest gotowa)
    "kursy": lambda con, days=7: __import__("analizator.oficjalne", fromlist=["x"]).live_fx(con, min(days, 5)),
    "ais": lambda con, days=7: __import__("analizator.ais", fromlist=["fetch"]).fetch(con, days),
}


# Limit czasu na źródło w sekundach (AIS słucha strumienia ok. 3 min, FINRA przy pierwszym uruchomieniu pobiera 100 dni)
STATUS: dict[str, str] = {}  # wynik ostatniego pobrania każdego źródła (do paczki dla nocnego przeglądu)
LIMITS = {"ais": 300, "finra_short": 240, "kongres": 240}


def fetch_all(con: sqlite3.Connection, days: int = 7, names: list[str] | None = None) -> list[dict]:
    _con(con)
    out = []
    for name in names or list(FETCHERS):
        limit.start(LIMITS.get(name, 120))
        try:
            items = FETCHERS[name](con, days=days)
            print(f"  [{name}] {len(items)} rekordów")
            STATUS[name] = f"{len(items)} rekordów"
            out += items
        except Exception as e:
            print(f"  [{name}] pominięto: {e}")
            STATUS[name] = f"błąd: {str(e)[:160]}"
        finally:
            limit.stop()
    return out
