"""Nowe źródła do sprawdzenia na historii (każde osobno, patrz analizator/nowe_testy.py):

  eia   tygodniowe zapasy ropy w USA (EIA, seria WCESTUS1): nietypowo duży spadek albo wzrost zapasów, sygnał globalny,
  wiki  odsłony Wikipedii w języku kraju o tematach strachu (paszport, wiza, schron, emigracja, ewakuacja, kantor),
  ton   nagły spadek tonu wiadomości o kraju w GDELT (DOC API, timelinetone) wobec normy kraju.

Każde źródło zapisuje wiersze jak źródła pierwotne (kraj w adresie, data, opis), więc można je dołożyć do oceny krajów.

    python -m analizator.nowe_zrodla --zrodla eia,wiki,ton --od 2017-01-01 --db nowe_historia.db
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from .oficjalne import _item

UA = {"User-Agent": "analizator-ruchow-firm/0.10 (https://github.com/mat3usz-mk/analizator-ruchow-firm)"}


def _get(url: str, tries: int = 4, wait: float = 10.0, timeout: int = 120) -> bytes:
    err = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            err = e
            time.sleep(wait * (i + 1))
    raise RuntimeError(f"{url[:90]}: {err}")


def robust_z(x: float, hist: list[float]) -> float:
    med = statistics.median(hist)
    mad = statistics.median(abs(h - med) for h in hist) or 1e-9
    return (x - med) / (1.4826 * mad)


# --- EIA: zapasy ropy -----------------------------------------------------------
def eia_series() -> list[tuple[date, float]]:
    """Zapasy ropy w USA (tys. baryłek, tygodniowo). Najpierw kopia serii EIA w FRED (prosty CSV), potem strona EIA."""
    try:
        rows = _get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=WCESTUS1", tries=2, wait=5, timeout=60).decode().splitlines()[1:]
        out = [(date.fromisoformat(r.split(",")[0]), float(r.split(",")[1])) for r in rows if r.count(",") == 1 and r.split(",")[1] not in ("", ".")]
        if out:
            return sorted(out)
    except Exception as e:
        print(f"  [eia] FRED: {e}")
    html = _get("https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=WCESTUS1&f=W").decode("utf-8", "replace")
    out = []
    # wiersz: "2024-Jan" i do pięciu par (data tygodnia "01/05", wartość)
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        ym = re.search(r"(\d{4})-([A-Z][a-z]{2})", row)
        if not ym:
            continue
        y = int(ym.group(1))
        for md, val in re.findall(r"(\d{2}/\d{2})</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>", row):
            try:
                d = datetime.strptime(f"{y}/{md}", "%Y/%m/%d").date()
                out.append((d, float(val.replace(",", ""))))
            except ValueError:
                continue
    return sorted(out)


def eia_items(series: list[tuple[date, float]], start: date, z_thr: float = 2.5) -> list[dict]:
    """Tydzień ze zmianą zapasów nietypową względem 52 poprzednich tygodni (odchylenie odporne na skrajności)."""
    ch = [(series[i][0], series[i][1] - series[i - 1][1]) for i in range(1, len(series))]
    out = []
    for i in range(52, len(ch)):
        d, v = ch[i]
        if d < start:
            continue
        z = robust_z(v, [x for _, x in ch[i - 52:i]])
        if abs(z) >= z_thr:
            kind = "draw" if v < 0 else "build"
            out.append(_item("https://www.eia.gov/petroleum/supply/weekly/", f"US crude oil inventories unusual {kind}: "
                             f"{v / 1000:+.1f} mln bbl in a week ({z:+.1f} deviations, EIA)", d, "eia", "eia.gov", "US"))
    return out


# --- Wikipedia: tematy strachu w języku kraju ------------------------------------
TOPICS = ["Passport", "Travel visa", "Air raid shelter", "Emigration", "Emergency evacuation", "Bureau de change"]
# tylko kraje, których język wiki prawie nie jest dzielony z innymi (arabska, angielska, hiszpańska wiki nie wskazują kraju)
LANGS = {"UA": "uk", "RU": "ru", "PL": "pl", "IR": "fa", "IL": "he", "TW": "zh", "TR": "tr", "KR": "ko", "JP": "ja", "GE": "ka",
         "AM": "hy", "AZ": "az", "RS": "sr", "HU": "hu", "CZ": "cs", "RO": "ro", "FI": "fi", "SE": "sv", "NO": "no", "DK": "da",
         "EE": "et", "LV": "lv", "LT": "lt", "SK": "sk", "PK": "ur", "MM": "my", "ET": "am", "PH": "tl", "KZ": "kk"}


def wiki_titles() -> dict[str, list[str]]:
    """Tytuły tematów w językach z LANGS (przez Wikidata, z angielskich tytułów)."""
    q = urllib.parse.urlencode({"action": "wbgetentities", "sites": "enwiki", "titles": "|".join(TOPICS), "props": "sitelinks|labels",
                                "languages": "en", "format": "json"})
    ent = json.loads(_get(f"https://www.wikidata.org/w/api.php?{q}"))["entities"]
    out: dict[str, list[str]] = {}
    for e in ent.values():
        links = e.get("sitelinks", {})
        print(f"  wikidata {e.get('id')}: {e.get('labels', {}).get('en', {}).get('value')} ({len(links)} języków)")
        for lang in set(LANGS.values()):
            t = links.get(f"{lang}wiki", {}).get("title")
            if t:
                out.setdefault(lang, []).append(t)
    return out


def wiki_views(lang: str, title: str, start: date, end: date) -> dict[date, float]:
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{t}/daily/"
           f"{start:%Y%m%d}00/{end:%Y%m%d}00")
    try:
        items = json.loads(_get(url, tries=2, wait=3, timeout=60)).get("items", [])
    except Exception as e:
        print(f"  [wiki] {lang} {title}: {e}")
        return {}
    return {datetime.strptime(x["timestamp"][:8], "%Y%m%d").date(): float(x["views"]) for x in items}


def wiki_items(series: dict[str, dict[date, float]], start: date, ratio: float = 3.0, z_thr: float = 5.0) -> list[dict]:
    """Dzień, w którym suma odsłon tematów strachu jest ≥ 3× mediany z 28 dni i ≥ 5 odchyleń (oraz co najmniej 200 odsłon)."""
    out = []
    for c, s in series.items():
        days = sorted(s)
        for i in range(28, len(days)):
            d = days[i]
            if d < start:
                continue
            hist = [s[x] for x in days[i - 28:i]]
            med = statistics.median(hist)
            v = s[d]
            if v >= 200 and v >= ratio * max(med, 1) and robust_z(v, hist) >= z_thr:
                out.append(_item(f"https://pageviews.wmcloud.org/?project={LANGS[c]}.wikipedia.org", f"Wikipedia views on passport, visa, "
                                 f"shelter and emigration topics in {LANGS[c]} spiked to {v:.0f} vs {med:.0f} typical (Wikimedia)",
                                 d, "wiki", "wikimedia.org", c))
    return out


# --- GDELT: ton wiadomości o kraju -------------------------------------------------
def ton_series(country: str, name: str, start: date, end: date) -> dict[date, float]:
    q = urllib.parse.urlencode({"query": f'"{name}" sourcelang:english', "mode": "timelinetone", "format": "json",
                                "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959"})
    try:
        data = json.loads(_get(f"https://api.gdeltproject.org/api/v2/doc/doc?{q}", tries=2, wait=30, timeout=60))
    except Exception as e:
        print(f"  [ton] {country}: {e}")
        return {}
    out = {}
    for tl in data.get("timeline", []):
        for p in tl.get("data", []):
            try:
                out[datetime.strptime(p["date"][:8], "%Y%m%d").date()] = float(p["value"])
            except (KeyError, ValueError):
                continue
    return out


def ton_items(series: dict[str, dict[date, float]], start: date, z_thr: float = -3.5) -> list[dict]:
    """Dzień, w którym ton wiadomości o kraju spada o ≥ 3,5 odchylenia poniżej normy z 28 dni."""
    out = []
    for c, s in series.items():
        days = sorted(s)
        for i in range(28, len(days)):
            d = days[i]
            if d < start:
                continue
            hist = [s[x] for x in days[i - 28:i]]
            z = robust_z(s[d], hist)
            if z <= z_thr:
                out.append(_item(f"https://api.gdeltproject.org/#ton-{c}", f"News tone about the country fell to {s[d]:.2f} vs "
                                 f"{statistics.median(hist):.2f} typical ({z:.1f} deviations, GDELT)", d, "ton", "gdeltproject.org", c))
    return out


def history(sources: set[str], start: date, end: date, sink=None) -> list[dict]:
    """sink(items): zapis na bieżąco (długie pobieranie może zostać przerwane limitem czasu)."""
    from .signals import COUNTRIES
    items: list[dict] = []
    if "eia" in sources:
        s = eia_series()
        print(f"eia: {len(s)} tygodni ({s[0][0] if s else '-'} .. {s[-1][0] if s else '-'})", flush=True)
        items += eia_items(s, start)
    if "wiki" in sources:
        titles = wiki_titles()
        series = {}
        for c, lang in LANGS.items():
            tot: dict[date, float] = {}
            for t in titles.get(lang, []):
                for d, v in wiki_views(lang, t, max(start - timedelta(days=40), date(2015, 7, 1)), end).items():
                    tot[d] = tot.get(d, 0.0) + v
                time.sleep(0.2)
            if tot:
                series[c] = tot
            print(f"  wiki {c} ({lang}): {len(titles.get(lang, []))} tematów, {len(tot)} dni", flush=True)
        items += wiki_items(series, start)
    if "ton" in sources:
        series = {}
        for c, names in COUNTRIES.items():
            name = re.sub(r"\\[bB]|[()?\\]", "", names[0])
            s = ton_series(c, name, max(start - timedelta(days=40), date(2017, 1, 1)), end)
            part = ton_items({c: s}, start) if s else []
            if sink and part:
                sink(part)
            else:
                items += part
            print(f"  ton {c}: {len(s)} dni, {len(part)} sygnałów", flush=True)
            time.sleep(6)
    return items


def main(argv=None) -> int:
    from . import store
    ap = argparse.ArgumentParser(prog="analizator.nowe_zrodla")
    ap.add_argument("--zrodla", default="eia,wiki,ton")
    ap.add_argument("--od", default="2017-03-01")
    ap.add_argument("--do", default=date.today().isoformat())
    ap.add_argument("--db", default="nowe_historia.db")
    a = ap.parse_args(argv)
    con = store.connect(a.db)
    items = history(set(a.zrodla.split(",")), date.fromisoformat(a.od), date.fromisoformat(a.do), sink=lambda xs: store.save(con, xs))
    print(f"zapisano {store.save(con, items)} z {len(items)}")
    for src, n in con.execute("SELECT source, COUNT(*) FROM articles GROUP BY 1"):
        print(f"  {src}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
