"""Pobieranie wiadomości z darmowych źródeł (bez kluczy API).

- GDELT DOC 2.0: globalny indeks wiadomości w ~65 językach, ostatnie ~3 miesiące.
- Google News RSS: szybki podgląd po zapytaniu, EN i PL.
- SEC EDGAR (pełnotekstowe): raporty bieżące 8-K/6-K spółek z USA i zagranicznych
  notowanych w USA, np. "suspend operations in Ukraine". Wymaga nagłówka
  User-Agent z kontaktem (zmienna SEC_USER_AGENT), inaczej jest pomijane.
- Własne kanały RSS z pliku feeds.txt (np. komunikaty giełdowe, branżowe portale).

Wszystko zwraca słowniki: url, title, date (YYYY-MM-DD), source, domain, lang.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

UA = "analizator-ruchow-firm/0.1 (+research prototype)"

# Zapytania pogrupowane tematycznie. Krótkie, bo GDELT ma limit długości zapytania.
QUERIES_EN = [
    '"ordered departure" OR "embassy evacuates" OR "non-essential staff" OR "non-emergency staff" OR "leave immediately"',
    '"suspend flights" OR "suspends flights" OR "avoid airspace" OR "airspace closed" OR "FAA warning" OR "conflict zone"',
    '"carrier strike group" OR "closes border" OR "border crossing closed" OR "war risk premium"',
    '"suspend operations" OR "suspends operations" OR "halts operations"',
    '"evacuates staff" OR "relocates staff" OR "non-essential staff" OR "evacuate employees"',
    '"exit the market" OR "pulls out of" OR "withdraws from"',
    '"sells stake" OR "divests" OR "asset sale" OR "writedown"',
    '"war risk" OR "insurers cancel" OR "reduce exposure" OR "cut credit lines"',
    '"force majeure" OR "reroutes" OR "halts shipments" OR "suspends deliveries"',
    '"gas transit" OR "storage levels" OR "book capacity"',
]
QUERIES_PL = [
    '"wycofuje się z" OR "zawiesza działalność" OR "ewakuuje pracowników"',
    '"sprzedaje udziały" OR "ogranicza ekspozycję" OR "wstrzymuje dostawy"',
]


# Liczba błędów w ostatnim wywołaniu źródła (backfill nie oznacza okna jako zrobionego, gdy wszystko padło)
LAST_ERRORS = {"n": 0}


BLOCKED_HOSTS: set[str] = set()


def _get(url: str, headers: dict | None = None, timeout: int = 30, tries: int = 4) -> bytes:
    """GET z ponawianiem przy 429/5xx/zerwanym połączeniu (przerwa rośnie: 5, 15, 45 s)."""
    import urllib.error
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in BLOCKED_HOSTS:
        raise urllib.error.URLError(f"host zablokowany przez sieć środowiska: {host}")
    delay = 5.0
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                LAST_ERRORS["n"] += 1
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if "Tunnel connection failed: 403" in str(e) or "Forbidden" in str(getattr(e, "reason", "")):
                # proxy odmawia hosta (brak go na liście dozwolonych) - ponawianie nic nie da
                BLOCKED_HOSTS.add(host)
                LAST_ERRORS["n"] += 1
                raise
            if attempt == tries - 1:
                LAST_ERRORS["n"] += 1
                raise
        time.sleep(delay)
        delay *= 3
    raise RuntimeError("unreachable")


def gdelt(days: int = 30, extra_terms: str = "", max_records: int = 250, pause: float = 6.0,
          start: date | None = None, end: date | None = None) -> list[dict]:
    """GDELT DOC API. Limit: ok. 1 zapytanie na 5 s, okno do ~90 dni."""
    out: list[dict] = []
    span = f"{min(days, 90)}d"
    for i, q in enumerate(QUERIES_EN):
        query = f"({q}) {extra_terms}".strip()
        window = ({"startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d235959")}
                  if start and end else {"timespan": span})
        # W oknach historycznych pytamy od najnowszych i od najstarszych, żeby limit 250 nie zjadał początku okna.
        articles = []
        for sort in (("datedesc", "dateasc") if start and end else ("datedesc",)):
            params = urllib.parse.urlencode({
                "query": query, "mode": "artlist", "format": "json",
                "maxrecords": max_records, "sort": sort, **window,
            })
            try:
                raw = _get(f"https://api.gdeltproject.org/api/v2/doc/doc?{params}") or b"{}"
                articles += json.loads(raw).get("articles", [])
            except json.JSONDecodeError:
                print(f"  [gdelt] zapytanie {i + 1}: odpowiedź nie jest JSON (zbyt długie zapytanie?)")
            except Exception as e:
                print(f"  [gdelt] pominięto zapytanie {i + 1} ({sort}): {e}")
            if sort == "datedesc" and start and end:
                time.sleep(pause)
        for a in articles:
            sd = a.get("seendate", "")
            out.append({
                "url": a.get("url"), "title": a.get("title", ""),
                "date": f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) >= 8 else None,
                "source": "gdelt", "domain": a.get("domain"), "lang": a.get("language"),
            })
        if i < len(QUERIES_EN) - 1:
            time.sleep(pause)
    return out


def google_news(days: int = 30, pause: float = 1.0, start: date | None = None, end: date | None = None) -> list[dict]:
    out: list[dict] = []
    for lang, queries, loc in (("en", QUERIES_EN, "hl=en-US&gl=US&ceid=US:en"), ("pl", QUERIES_PL, "hl=pl&gl=PL&ceid=PL:pl")):
        for q in queries:
            when = f" after:{start.isoformat()} before:{(end + timedelta(days=1)).isoformat()}" if start and end else f" when:{days}d"
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q + when)}&{loc}"
            try:
                root = ET.fromstring(_get(url))
            except Exception as e:
                print(f"  [google news] pominięto: {e}")
                continue
            for item in root.iter("item"):
                title = item.findtext("title") or ""
                src = item.find("source")
                try:
                    d = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
                except Exception:
                    d = None
                out.append({
                    "url": item.findtext("link"), "title": title.rsplit(" - ", 1)[0],
                    "date": d, "source": "gnews", "domain": src.get("url") if src is not None else None, "lang": lang,
                })
            time.sleep(pause)
    return out


# Frazy szukane w raportach 8-K/6-K. "impairment" i "wind down" dawały głównie szum księgowy, więc ich nie ma.
SEC_PHRASES = ['"suspend operations"', '"suspended operations"', '"cease operations"', '"evacuat"', '"force majeure"',
               '"exit the market"', '"withdraw from"']
# Kraje sprawdzane w raportach SEC. Bez "Georgia" (myli się ze stanem USA).
SEC_COUNTRIES = {
    "Ukraine": "UA", "Russia": "RU", "Belarus": "BY", "Taiwan": "TW", "China": "CN", "Iran": "IR", "Israel": "IL", "Lebanon": "LB",
    "Iraq": "IQ", "Yemen": "YE", "Red Sea": "YE", "Saudi Arabia": "SA", "Qatar": "QA", "United Arab Emirates": "AE",
    "Strait of Hormuz": "IR", "Venezuela": "VE", "Moldova": "MD", "Serbia": "RS", "Poland": "PL",
    "Turkey": "TR", "Egypt": "EG", "Pakistan": "PK", "South Korea": "KR", "North Korea": "KP", "Philippines": "PH",
}
_PHRASE_RE = {
    '"suspend operations"': r"suspend\w* (?:\w+ ){0,3}operations", '"suspended operations"': r"suspend\w* (?:\w+ ){0,3}operations",
    '"cease operations"': r"ceas\w* (?:\w+ ){0,3}operations", '"evacuat"': r"evacuat\w*", '"force majeure"': r"force majeure",
    '"exit the market"': r"exit\w* (?:the |from )?(?:\w+ )?market", '"withdraw from"': r"withdr[ae]w\w* from",
}


def _ascii(text: str) -> str:
    """Nagłówki HTTP przyjmują tylko ASCII: "Łódź" -> "Lodz"."""
    import unicodedata
    text = text.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def sec_user_agent() -> str | None:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua and os.path.exists("config.json"):
        try:
            ua = json.load(open("config.json", encoding="utf-8")).get("sec_user_agent")
        except Exception:
            ua = None
    return _ascii(ua).strip() if ua else None


def _strip_html(raw: bytes) -> str:
    import html as _html
    import re as _re
    text = raw.decode("utf-8", "ignore")
    text = _re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = _re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(_html.unescape(text).split())


def sec_sentence(text: str, phrase: str, country: str) -> str | None:
    """Zdanie z raportu, w którym fraza i kraj występują razem. Inaczej None (to był szum)."""
    import re as _re
    pr = _re.compile(_PHRASE_RE[phrase], _re.I)
    cr = _re.compile(r"\b" + _re.escape(country) + r"\b")
    for sent in _re.split(r"(?<=[.;])\s+", text):
        if len(sent) < 600 and pr.search(sent) and cr.search(sent):
            return sent.strip()
    return None


def sec_edgar(days: int = 30, pause: float = 0.12, start: date | None = None, end: date | None = None,
              max_docs: int = 400) -> list[dict]:
    """Raporty 8-K/6-K, w których fraza i kraj są w TYM SAMYM zdaniu. Tytuł = to zdanie (nie zmyślony skrót).

    Limit SEC: 10 zapytań/s. Każdy kandydat wymaga pobrania dokumentu, więc max_docs ogranicza czas.
    """
    ua = sec_user_agent()
    if not ua:
        print("  [sec] pominięto: brak SEC_USER_AGENT (SEC wymaga imienia i e-maila)")
        return []
    end = end or date.today()
    start = start or end - timedelta(days=days)
    out: list[dict] = []
    seen: set[str] = set()
    errors = checked = rejected = 0
    for phrase in SEC_PHRASES:
        for country in SEC_COUNTRIES:
            params = urllib.parse.urlencode({
                "q": f'{phrase} "{country}"', "forms": "8-K,6-K", "dateRange": "custom",
                "startdt": start.isoformat(), "enddt": end.isoformat(),
            })
            try:
                data = json.loads(_get(f"https://efts.sec.gov/LATEST/search-index?{params}", {"User-Agent": ua}))
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  [sec] błąd {phrase} {country}: {e}")
                if errors >= 10:
                    print("  [sec] za dużo błędów, przerywam")
                    return out
                continue
            time.sleep(pause)
            for hit in data.get("hits", {}).get("hits", []):
                if checked >= max_docs:
                    break
                src = hit.get("_source", {})
                adsh, _, fname = hit.get("_id", "").partition(":")
                cik = (src.get("ciks") or [""])[0].lstrip("0")
                if not (cik and fname):
                    continue
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fname}"
                if (url, country) in seen:
                    continue
                seen.add((url, country))
                checked += 1
                try:
                    text = _strip_html(_get(url, {"User-Agent": ua}))
                except Exception:
                    continue
                finally:
                    time.sleep(pause)
                sent = sec_sentence(text, phrase, country)
                if not sent:
                    rejected += 1
                    continue
                company = (src.get("display_names") or ["?"])[0].split(" (CIK")[0].split("  (")[0]
                out.append({
                    "url": url, "title": f"{company}: {sent}"[:300], "date": src.get("file_date"),
                    "source": "sec", "domain": "sec.gov", "lang": "en",
                })
    print(f"  [sec] sprawdzono {checked} dokumentów, odrzucono {rejected} (kraj i fraza nie w jednym zdaniu), zostało {len(out)}")
    return out


def rss_feeds(path: str = "feeds.txt") -> list[dict]:
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    for line in open(path, encoding="utf-8"):
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        try:
            root = ET.fromstring(_get(url))
        except Exception as e:
            print(f"  [rss] pominięto {url}: {e}")
            continue
        for item in root.iter("item"):
            try:
                d = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
            except Exception:
                d = datetime.now().date().isoformat()
            out.append({
                "url": item.findtext("link"), "title": item.findtext("title") or "", "date": d,
                "source": "rss", "domain": urllib.parse.urlparse(url).netloc, "lang": None,
            })
    return out


FETCHERS = {"pierwotne": None, "gdelt": gdelt, "gnews": google_news, "sec": sec_edgar, "rss": lambda days: rss_feeds()}
