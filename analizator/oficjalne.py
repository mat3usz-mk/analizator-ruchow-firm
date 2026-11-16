"""Źródła pierwotne i pomiary (bez artykułów): sankcje UE i Wielkiej Brytanii, oficjalne komunikaty Rady UE, ONZ i MAEA,
awarie internetu (IODA), przejścia statków przez cieśniny (IMF PortWatch) i gwałtowne spadki walut (notowania rynkowe).

Wszystkie są publiczne i bez klucza. Te z datami w danych (sankcje, IODA, PortWatch, kursy) mają też historię,
więc można je sprawdzić w teście historycznym:

    python -m analizator.oficjalne --od 2019-01-01 --do 2026-11-16 --db pierwotne_historia.db

Każdy wpis to „artykuł” (url, tytuł, data, źródło), ale kraj i kategoria są podane wprost (kotwica #kraj=XX w adresie,
kategoria ze źródła), więc nie zależą od zgadywania z tytułu. NIE jest to rekomendacja inwestycyjna.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import statistics
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (analizator ruchow firm; public data)"}

# źródło -> (kategoria, waga bazowa, aktor). Używane w score.extract_signals zamiast klasyfikacji tytułu.
STRUCTURED: dict[str, tuple[str, float, str]] = {
    "sankcje_ue": ("sankcje", 2.5, "panstwo"),
    "sankcje_uk": ("sankcje", 2.5, "panstwo"),
    "ioda": ("ostrzezenia_panstw", 2.5, "panstwo"),
    "kursy": ("przeplywy_finansowe", 2.5, "firma"),
    "portwatch": ("lancuch_dostaw", 3.0, "firma"),
    "acled": ("ostrzezenia_panstw", 2.5, "panstwo"),
    "agsi": ("energia_surowce", 2.5, "firma"),
}
OFFICIAL_RSS = {"rada_ue": ("https://www.consilium.europa.eu/en/rss/pressreleases.ashx", "consilium.europa.eu"),
                "onz": ("https://press.un.org/en/rss.xml", "press.un.org"),
                "maea": ("https://www.iaea.org/feeds/topnews", "iaea.org")}
ALL_SOURCES = set(STRUCTURED) | set(OFFICIAL_RSS)


def country_of(item: dict) -> str | None:
    m = re.search(r"#kraj=([A-Z]{2})", item.get("url") or "")
    return m.group(1) if m else None


def _get(url: str, timeout: int = 120, tries: int = 3, wait: int = 20) -> bytes:
    err = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            err = e
            time.sleep(wait * (i + 1) if "429" in str(e) else 3)
    raise RuntimeError(f"{url[:80]}: {err}")


def _item(url, title, d: date, source, domain, kraj):
    import hashlib
    k = hashlib.sha1(title.encode()).hexdigest()[:8]  # adres musi być unikalny (baza odrzuca powtórzony adres)
    return {"url": f"{url}#kraj={kraj}&d={d.isoformat()}&k={k}", "title": title, "date": d.isoformat(), "source": source, "domain": domain, "lang": "en"}


def _name(code: str) -> str:
    from .score import country_name
    return country_name(code)


# --- Sankcje: UE i Wielka Brytania (pełne listy z datą wpisania) ---------------------------------
ISO3 = {"RUS": "RU", "IRN": "IR", "SYR": "SY", "PRK": "KP", "BLR": "BY", "UKR": "UA", "LBY": "LY", "MMR": "MM", "VEN": "VE",
        "IRQ": "IQ", "AFG": "AF", "SDN": "SD", "SSD": "SS", "SOM": "SO", "YEM": "YE", "LBN": "LB", "MLI": "ML", "NIC": "NI",
        "COD": "CD", "CAF": "CF", "ZWE": "ZW", "GIN": "GN", "BDI": "BI", "TUN": "TN", "EGY": "EG", "MDA": "MD", "TUR": "TR",
        "HTI": "HT", "NER": "NE", "GTM": "GT", "BIH": "BA", "SRB": "RS", "CHN": "CN", "GNB": "GW", "TCD": "TD"}
UK_REGIME = {"south sudan": "SS", "russia": "RU", "iran": "IR", "syria": "SY", "democratic people": "KP", "belarus": "BY", "libya": "LY", "myanmar": "MM",
             "burma": "MM", "venezuela": "VE", "iraq": "IQ", "afghanistan": "AF", "sudan": "SD", "somalia": "SO",
             "yemen": "YE", "lebanon": "LB", "mali": "ML", "nicaragua": "NI", "congo": "CD", "central african": "CF", "zimbabwe": "ZW",
             "guinea": "GN", "bosnia": "BA", "haiti": "HT", "moldova": "MD", "ukraine": "RU"}  # reżim „Ukraine” dotyczy Rosji


def sanctions_eu(since: date | None = None) -> list[tuple[date, str]]:
    """(data publikacji pierwszego rozporządzenia, kraj programu) dla każdej pozycji listy UE."""
    raw = _get("https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw", 240)
    ns = "{http://eu.europa.ec/fpi/fsd/export}"
    out = []
    for _, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag != ns + "sanctionEntity":
            continue
        regs = [r for r in el.findall(ns + "regulation") if r.get("publicationDate")]
        if regs:
            first = min(regs, key=lambda r: r.get("publicationDate"))
            code = ISO3.get((first.get("programme") or "").upper())
            d = date.fromisoformat(first.get("publicationDate")[:10])
            if code and (since is None or d >= since):
                out.append((d, code))
        el.clear()
    return out


def sanctions_uk(since: date | None = None) -> list[tuple[date, str]]:
    raw = _get("https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv", 240).decode("utf-8-sig", "ignore")
    lines = raw.splitlines()
    if lines and lines[0].startswith("Report Date"):
        lines = lines[1:]
    seen, out = set(), []
    for row in csv.DictReader(lines):
        uid = row.get("Unique ID") or row.get("OFSI Group ID")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        reg = (row.get("Regime Name") or "").lower()
        code = next((c for k, c in UK_REGIME.items() if k in reg), None)
        try:
            d = datetime.strptime((row.get("Date Designated") or "").strip(), "%d/%m/%Y").date()
        except ValueError:
            continue
        if code and (since is None or d >= since):
            out.append((d, code))
    return out


def sanctions_items(rows: list[tuple[date, str]], source: str, who: str, domain: str, url: str) -> list[dict]:
    groups: dict[tuple[date, str], int] = defaultdict(int)
    for d, c in rows:
        groups[(d, c)] += 1
    return [_item(url, f"{who} sanctions designations: {n} new persons and entities linked to {_name(c)} (official sanctions list)",
                  d, source, domain, c) for (d, c), n in sorted(groups.items())]


# --- Oficjalne komunikaty (RSS): Rada UE, ONZ (Rada Bezpieczeństwa), MAEA ---------------------------
def official_rss(days: int = 7) -> list[dict]:
    out = []
    since = date.today() - timedelta(days=days)
    for src, (url, domain) in OFFICIAL_RSS.items():
        try:
            root = ET.fromstring(_get(url, 60, tries=2))
        except Exception as e:
            print(f"  [{src}] pominięto: {e}")
            continue
        for it in root.iter("item"):
            title, link, pub = (it.findtext(k) or "" for k in ("title", "link", "pubDate"))
            try:
                d = datetime.strptime(pub[:16].strip(), "%a, %d %b %Y").date()
            except ValueError:
                d = date.today()
            if d >= since and title:
                out.append({"url": link, "title": title.strip(), "date": d.isoformat(), "source": src, "domain": domain, "lang": "en"})
    return out


# --- Awarie internetu w całym kraju (IODA, Georgia Tech) ----------------------------------------------
def ioda(start: date, end: date) -> list[dict]:
    from .signals import COUNTRIES
    out, t = [], start
    while t < end:
        t2 = min(t + timedelta(days=30), end)
        a, b = (int(datetime(x.year, x.month, x.day, tzinfo=timezone.utc).timestamp()) for x in (t, t2))
        try:
            js = json.loads(_get(f"https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events?from={a}&until={b}&entityType=country&limit=2000", 90))
        except Exception as e:
            print(f"  [ioda] {t}: {e}")
            js = {"data": []}
        for ev in js.get("data") or []:
            code = (ev.get("location") or "").split("/")[-1].upper()
            dur = ev.get("duration") or 0
            # 2 h - 5 dni: krótsze to szum, dłuższe to zwykle artefakty pomiaru (np. Antarktyda)
            if code not in COUNTRIES or not 7200 <= dur <= 5 * 86400 or not ev.get("start"):
                continue
            d = datetime.fromtimestamp(ev["start"], timezone.utc).date()
            if not t <= d < t2:
                continue
            out.append(_item(f"https://ioda.inetintel.cc.gatech.edu/country/{code}?from={ev['start']}",
                             f"Nationwide internet connectivity disruption in {_name(code)} for {dur / 3600:.0f} hours "
                             f"(IODA measurement, {ev.get('datasource', '?')})", d, "ioda", "ioda.inetintel.cc.gatech.edu", code))
        t = t2
        time.sleep(1)
    # jedno zdarzenie na kraj i dzień
    uniq = {(x["date"], country_of(x)): x for x in out}
    return sorted(uniq.values(), key=lambda x: x["date"])


# --- Przejścia statków przez cieśniny (IMF PortWatch, dane dzienne od 2019) ---------------------------
CHOKE = {"Strait of Hormuz": "IR", "Bab el-Mandeb Strait": "YE", "Suez Canal": "EG", "Taiwan Strait": "TW",
         "Bosporus Strait": "TR", "Panama Canal": "PA", "Malacca Strait": "MY"}
PW = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"


def _pw_series(name: str, start: date) -> list[tuple[date, float, float]]:
    rows, off = [], 0
    where = f"portname='{name}' AND date >= DATE '{start.isoformat()}'"
    while True:
        q = urllib.parse.urlencode({"where": where, "outFields": "date,portname,n_total,n_tanker", "orderByFields": "date",
                                    "resultOffset": off, "resultRecordCount": 2000, "f": "json"})
        js = json.loads(_get(f"{PW}?{q}", 90, tries=4, wait=30))
        if "error" in js:
            raise RuntimeError(js["error"].get("message"))
        feats = js.get("features") or []
        for f in feats:
            at = f.get("attributes") or {}
            dv = at.get("date")
            d = datetime.fromtimestamp(dv / 1000, timezone.utc).date() if isinstance(dv, (int, float)) else date.fromisoformat(str(dv)[:10])
            rows.append((d, float(at.get("n_total") or 0), float(at.get("n_tanker") or 0)))
        if len(feats) < 2000 or not js.get("exceededTransferLimit", len(feats) >= 2000):
            break
        off += len(feats)
        time.sleep(2)
    return rows


def portwatch(start: date, end: date) -> list[dict]:
    out = []
    for name, code in CHOKE.items():
        try:
            s = _pw_series(name, start - timedelta(days=100))
        except Exception as e:
            print(f"  [portwatch] {name}: {e}")
            continue
        s.sort()
        last_sig = None
        for i in range(97, len(s)):
            d = s[i][0]
            if not start <= d <= end:
                continue
            for k, word in ((1, "Ship transits"), (2, "Tanker transits")):
                week = statistics.mean(x[k] for x in s[i - 6:i + 1])
                base = statistics.median(x[k] for x in s[i - 97:i - 7])
                if base >= 8 and week <= 0.6 * base and (last_sig is None or (d - last_sig).days >= 14):
                    last_sig = d
                    out.append(_item("https://portwatch.imf.org/pages/chokepoints",
                                     f"{word} through {name} down {100 * (1 - week / base):.0f}% vs 3-month norm "
                                     f"({week:.0f} vs {base:.0f} a day); ships avoid route (IMF PortWatch)", d, "portwatch", "portwatch.imf.org", code))
        time.sleep(3)
    return out


# --- Gwałtowne spadki walut (notowania dzienne) -----------------------------------------------------
FX = {"TR": "TRY", "IL": "ILS", "TW": "TWD", "KR": "KRW", "RU": "RUB", "UA": "UAH", "PK": "PKR", "IN": "INR", "EG": "EGP",
      "CN": "CNY", "PL": "PLN", "HU": "HUF", "NG": "NGN", "ZA": "ZAR", "BR": "BRL", "MX": "MXN", "PH": "PHP", "ID": "IDR",
      "KZ": "KZT", "GE": "GEL", "VN": "VND", "TH": "THB", "MY": "MYR", "CZ": "CZK", "RO": "RON", "NO": "NOK", "SE": "SEK",
      "CO": "COP", "CL": "CLP", "PE": "PEN", "MA": "MAD", "KE": "KES", "BD": "BDT", "LK": "LKR"}


def _yahoo(sym: str, start: date) -> list[tuple[date, float]]:
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    js = json.loads(_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={p1}"
                         f"&period2={int(time.time())}&interval=1d", 60, tries=3, wait=5))
    r = js["chart"]["result"][0]
    return [(datetime.fromtimestamp(t, timezone.utc).date(), c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]


def fx_shocks(start: date, end: date) -> list[dict]:
    from .signals import COUNTRIES
    out = []
    for code, cur in FX.items():
        if code not in COUNTRIES:
            continue
        try:
            s = _yahoo(f"{cur}=X", start - timedelta(days=420))
        except Exception as e:
            print(f"  [kursy] {cur}: {e}")
            continue
        last = None
        for i in range(255, len(s)):
            d = s[i][0]
            if not start <= d <= end:
                continue
            ch = s[i][1] / s[i - 5][1] - 1  # USD/XXX w górę = waluta słabnie
            hist = [s[j][1] / s[j - 5][1] - 1 for j in range(i - 250, i - 5)]
            sd = statistics.pstdev(hist) or 1e-9
            if ch >= 0.03 and ch >= 3 * sd and (last is None or (d - last).days >= 14):
                last = d
                out.append(_item(f"https://finance.yahoo.com/quote/{cur}%3DX",
                                 f"{_name(code)} currency ({cur}) weakens {100 * ch:.1f}% against USD in 5 trading days, "
                                 f"{ch / sd:.1f} times its usual move; capital outflow (market data)", d, "kursy", "finance.yahoo.com", code))
        time.sleep(0.5)
    return out


# --- ACLED: zdarzenia konfliktowe (konto: sekrety ACLED_EMAIL i ACLED_PASSWORD) -----------------------
# Dane ACLED nie mogą być publikowane: zapisujemy tylko wnioski (skok liczby zdarzeń w kraju), nie same zdarzenia.
_ACLED_TOKEN: str | None = None
ACLED_TYPES = "Battles:OR:event_type=Explosions/Remote violence:OR:event_type=Violence against civilians"


def _acled_token() -> str:
    global _ACLED_TOKEN
    if _ACLED_TOKEN:
        return _ACLED_TOKEN
    import os
    user, pw = os.environ.get("ACLED_EMAIL"), os.environ.get("ACLED_PASSWORD")
    if not user or not pw:
        raise RuntimeError("brak ACLED_EMAIL / ACLED_PASSWORD")
    body = urllib.parse.urlencode({"username": user, "password": pw, "grant_type": "password", "client_id": "acled",
                                   "scope": "authenticated"}).encode()
    req = urllib.request.Request("https://acleddata.com/oauth/token", data=body,
                                 headers={**UA, "Content-Type": "application/x-www-form-urlencoded"})
    _ACLED_TOKEN = json.loads(urllib.request.urlopen(req, timeout=60).read())["access_token"]
    return _ACLED_TOKEN


def acled_counts(start: date, end: date) -> dict[tuple[str, date], int]:
    """Liczba zdarzeń przemocy politycznej na kraj i dzień (bitwy, ostrzał/eksplozje, przemoc wobec cywilów)."""
    from .signals import detect_countries
    counts: dict[tuple[str, date], int] = defaultdict(int)
    names: dict[str, str | None] = {}
    t = start
    while t <= end:
        t2 = min(t + timedelta(days=30), end)
        page = 1
        while True:
            q = urllib.parse.urlencode({"event_date": f"{t.isoformat()}|{t2.isoformat()}", "event_date_where": "BETWEEN",
                                        "fields": "event_date|country", "limit": 5000, "page": page})
            q += "&event_type=" + urllib.parse.quote(ACLED_TYPES, safe=":=/")
            req = urllib.request.Request(f"https://acleddata.com/api/acled/read?{q}",
                                         headers={**UA, "Authorization": f"Bearer {_acled_token()}"})
            js = json.loads(urllib.request.urlopen(req, timeout=180).read())
            rows = js.get("data") or []
            for r in rows:
                c = r.get("country") or ""
                if c not in names:
                    found = detect_countries(c)
                    names[c] = found[0] if found else None
                if names[c]:
                    counts[(names[c], date.fromisoformat(r["event_date"][:10]))] += 1
            if len(rows) < 5000:
                break
            page += 1
        t = t2 + timedelta(days=1)
    return counts


def acled(start: date, end: date) -> list[dict]:
    """Sygnał: w ostatnich 7 dniach co najmniej 2 razy więcej zdarzeń niż mediana tygodniowa z 12 poprzednich tygodni (min. 10)."""
    counts = acled_counts(start - timedelta(days=100), end)
    if not counts:
        print("  [acled] brak danych (konto może mieć dostęp tylko do starszych danych)")
        return []
    print(f"  [acled] dane do {max(d for _, d in counts)}")
    by_c: dict[str, dict[date, int]] = defaultdict(dict)
    for (c, d), n in counts.items():
        by_c[c][d] = n
    out = []
    for c, days in by_c.items():
        last = None
        d = start
        while d <= end:
            week = sum(days.get(d - timedelta(days=i), 0) for i in range(7))
            prev = [sum(days.get(d - timedelta(days=7 * w + i), 0) for i in range(7)) for w in range(1, 13)]
            med = statistics.median(prev)
            if week >= 10 and week >= 2 * max(med, 1) and (last is None or (d - last).days >= 14):
                last = d
                out.append(_item("https://acleddata.com/", f"Political violence events in {_name(c)} up to {week} in 7 days "
                                 f"from a usual {med:.0f} a week: battles, explosions, attacks on civilians (ACLED)", d, "acled", "acleddata.com", c))
            d += timedelta(days=1)
    return out


# --- Magazyny gazu w UE (GIE AGSI+, sekret AGSI_KEY) -------------------------------------------------
def agsi(start: date, end: date) -> list[dict]:
    """Sygnał (dla Rosji jako dostawcy): zapełnienie magazynów UE co najmniej 10 pkt proc. poniżej średniej z 5 lat dla tego dnia."""
    import os
    key = os.environ.get("AGSI_KEY")
    if not key:
        raise RuntimeError("brak AGSI_KEY")
    rows, page = {}, 1
    while True:
        q = urllib.parse.urlencode({"type": "eu", "from": (start - timedelta(days=5 * 366 + 10)).isoformat(), "to": end.isoformat(),
                                    "size": 300, "page": page})
        req = urllib.request.Request(f"https://agsi.gie.eu/api?{q}", headers={**UA, "x-key": key})
        js = json.loads(urllib.request.urlopen(req, timeout=60).read())
        for r in js.get("data") or []:
            try:
                rows[date.fromisoformat(r["gasDayStart"])] = float(r["full"])
            except (KeyError, TypeError, ValueError):
                continue
        if page >= int(js.get("last_page") or 1):
            break
        page += 1
        time.sleep(0.3)
    out, last = [], None
    for d in sorted(x for x in rows if start <= x <= end):
        past = [rows.get(d.replace(year=d.year - k)) for k in range(1, 6) if not (d.month == 2 and d.day == 29)]
        past = [p for p in past if p is not None]
        if len(past) < 3:
            continue
        avg = statistics.mean(past)
        if rows[d] <= avg - 10 and (last is None or (d - last).days >= 30):
            last = d
            out.append(_item("https://agsi.gie.eu/", f"EU gas storage only {rows[d]:.0f}% full vs {avg:.0f}% 5-year average for this day; "
                             "supply risk from Russia (GIE AGSI)", d, "agsi", "agsi.gie.eu", "RU"))
    return out


# --- Na żywo (pierwotne.FETCHERS) i historia -----------------------------------------------------------
def live_sanctions(con, days: int = 7) -> list[dict]:
    """Raz dziennie (pliki mają kilkadziesiąt MB): wpisy z ostatnich `days` dni z list UE i Wielkiej Brytanii."""
    con.execute("CREATE TABLE IF NOT EXISTS metrics (source TEXT, key TEXT, day TEXT, value REAL, PRIMARY KEY (source, key, day))")
    today = date.today().isoformat()
    if con.execute("SELECT 1 FROM metrics WHERE source='sankcje' AND day=?", (today,)).fetchone():
        return []
    since = date.today() - timedelta(days=days)
    out = []
    for fn, src, who, dom, url in ((sanctions_eu, "sankcje_ue", "EU", "webgate.ec.europa.eu", "https://www.sanctionsmap.eu/"),
                                   (sanctions_uk, "sankcje_uk", "UK", "sanctionslist.fcdo.gov.uk", "https://www.gov.uk/government/publications/the-uk-sanctions-list")):
        try:
            out += sanctions_items(fn(since), src, who, dom, url)
        except Exception as e:
            print(f"  [{src}] pominięto: {e}")
    con.execute("INSERT OR REPLACE INTO metrics VALUES ('sankcje','dzien',?,?)", (today, float(len(out))))
    con.commit()
    return out


def _once_a_day(con, key: str) -> bool:
    """True, jeśli dziś jeszcze nie pobierano (dane dzienne nie zmieniają się co 30 minut)."""
    con.execute("CREATE TABLE IF NOT EXISTS metrics (source TEXT, key TEXT, day TEXT, value REAL, PRIMARY KEY (source, key, day))")
    today = date.today().isoformat()
    if con.execute("SELECT 1 FROM metrics WHERE source=? AND day=?", (key, today)).fetchone():
        return False
    con.execute("INSERT OR REPLACE INTO metrics VALUES (?, 'dzien', ?, 1)", (key, today))
    con.commit()
    return True


def live_ioda(con, days: int = 3) -> list[dict]:
    return ioda(date.today() - timedelta(days=days), date.today() + timedelta(days=1))


def live_portwatch(con, days: int = 7) -> list[dict]:
    if not _once_a_day(con, "portwatch"):
        return []
    return portwatch(date.today() - timedelta(days=days), date.today())


def live_fx(con, days: int = 5) -> list[dict]:
    if not _once_a_day(con, "kursy"):
        return []
    return fx_shocks(date.today() - timedelta(days=days), date.today())


def live_acled(con, days: int = 7) -> list[dict]:
    if not _once_a_day(con, "acled"):
        return []
    return acled(date.today() - timedelta(days=days), date.today())


def live_agsi(con, days: int = 7) -> list[dict]:
    if not _once_a_day(con, "agsi"):
        return []
    return agsi(date.today() - timedelta(days=days), date.today())


def live_rss(con, days: int = 7) -> list[dict]:
    return official_rss(days)


def history(start: date, end: date, which: set[str] | None = None) -> list[dict]:
    which = which or {"sankcje", "ioda", "portwatch", "kursy"}
    out = []
    if "sankcje" in which:
        for fn, src, who, dom, url in ((sanctions_eu, "sankcje_ue", "EU", "webgate.ec.europa.eu", "https://www.sanctionsmap.eu/"),
                                       (sanctions_uk, "sankcje_uk", "UK", "sanctionslist.fcdo.gov.uk", "https://www.gov.uk/government/publications/the-uk-sanctions-list")):
            try:
                out += [x for x in sanctions_items(fn(start), src, who, dom, url) if x["date"] <= end.isoformat()]
            except Exception as e:
                print(f"  [{src}] {e}")
    if "ioda" in which:
        out += ioda(start, end)
    if "portwatch" in which:
        out += portwatch(start, end)
    if "kursy" in which:
        out += fx_shocks(start, end)
    for name, fn in (("acled", acled), ("agsi", agsi)):
        if name in which:
            try:
                out += fn(start, end)
            except Exception as e:
                print(f"  [{name}] {e}")
    return out


def main(argv=None) -> int:
    from . import store
    ap = argparse.ArgumentParser(prog="analizator.oficjalne")
    ap.add_argument("--od", default="2019-01-01")
    ap.add_argument("--do", default=date.today().isoformat())
    ap.add_argument("--db", default="pierwotne_historia.db")
    ap.add_argument("--zrodla", default="sankcje,ioda,portwatch,kursy")
    a = ap.parse_args(argv)
    items = history(date.fromisoformat(a.od), date.fromisoformat(a.do), set(a.zrodla.split(",")))
    con = store.connect(a.db)
    print(f"zapisano {store.save(con, items)} z {len(items)}")
    for src, n in con.execute("SELECT source, COUNT(*) FROM articles GROUP BY 1"):
        print(f"  {src}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
