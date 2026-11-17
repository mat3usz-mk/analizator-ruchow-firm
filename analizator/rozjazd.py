"""Rozjazd: twarde dane spółki kontra ton artykułów.

Najpierw twarde dane (transakcje insiderów z Form 4), dopiero potem artykuły jako kontrola. Gdy insiderzy wyraźnie sprzedają
(co najmniej 3× norma), a nagłówki o tej spółce z ostatnich 7 dni są w większości optymistyczne, oznaczamy rozjazd:
media grają w górę, a ludzie ze środka wychodzą. Odwrotnie: insiderzy kupują, a nagłówki straszą.

Uwaga: tego połączenia nie da się sprawdzić na historii (darmowe archiwa nagłówków o spółkach z tonem nie istnieją), więc to
oznaczenie do wglądu, nie alarm. Sam sygnał sprzedaży w spółkach energetycznych przeszedł test (raporty/insiderzy-wyniki.md).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date

NAMES = {"LMT": "Lockheed Martin", "RTX": "RTX Raytheon", "NOC": "Northrop Grumman", "GD": "General Dynamics", "LHX": "L3Harris",
         "BA": "Boeing", "XOM": "Exxon Mobil", "CVX": "Chevron", "COP": "ConocoPhillips", "LNG": "Cheniere Energy",
         "OXY": "Occidental Petroleum", "HAL": "Halliburton", "SLB": "SLB Schlumberger", "KMI": "Kinder Morgan",
         "EOG": "EOG Resources", "PSX": "Phillips 66"}
OPT = re.compile(r"\b(?:upgrad\w*|outperform\w*|buy rating|strong buy|bullish|rall(?:y|ies|ied)|soar\w*|surg\w*|jump\w*|"
                 r"record (?:high|profit|earnings|output)|beats?|boom\w*|windfall|top pick|target (?:raised|hike)|raises? (?:guidance|dividend|outlook)|"
                 r"all-time high|skyrocket\w*|breakout|buy now|undervalued|gains?)\b", re.I)
PES = re.compile(r"\b(?:downgrad\w*|underperform\w*|sell rating|bearish|plung\w*|slump\w*|tumbl\w*|sink\w*|slid\w*|falls?|drops?|"
                 r"miss(?:es|ed)?|cuts? (?:guidance|dividend|outlook|jobs)|target (?:cut|lowered)|lawsuit|probe|losses|layoffs?|crash\w*|"
                 r"overvalued|sell-off|selloff)\b", re.I)


def tone(title: str) -> int:
    o, p = bool(OPT.search(title)), bool(PES.search(title))
    return 1 if o and not p else (-1 if p and not o else 0)


def headlines(ticker: str, days: int = 7, get=None) -> list[str]:
    from .sources import _get
    get = get or _get
    q = f'"{NAMES.get(ticker, ticker)}" stock when:{days}d'
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"
    root = ET.fromstring(get(url))
    return [(i.findtext("title") or "").rsplit(" - ", 1)[0] for i in root.iter("item")]


def assess(rows: list[dict], titles_of=headlines) -> list[dict]:
    """rows: panel insiderów (pierwotne.insider_panel). Zwraca rozjazdy z liczbami."""
    from .rzetelnosc import emotion_score
    out = []
    for r in rows:
        selling = r.get("unusual") and (r.get("sell") or 0) >= 1e6
        buying = (r.get("buy") or 0) >= 2e5
        if not (selling or buying):
            continue
        try:
            ts = titles_of(r["ticker"])
        except Exception as e:
            print(f"  [rozjazd] {r['ticker']}: {e}")
            continue
        tones = [tone(t) for t in ts]
        opt, pes = tones.count(1), tones.count(-1)
        emo = sum(emotion_score(t)[0] >= 0.3 for t in ts)
        toned = opt + pes
        base = {"ticker": r["ticker"], "naglowkow": len(ts), "optymistyczne": opt, "pesymistyczne": pes, "emocjonalne": emo,
                "sprzedaz": r.get("sell"), "norma": r.get("sell_norm"), "zakup": r.get("buy")}
        if selling and toned >= 5 and opt / toned >= 0.6:
            out.append({**base, "rodzaj": "media w górę, insiderzy sprzedają"})
        elif buying and toned >= 5 and pes / toned >= 0.6:
            out.append({**base, "rodzaj": "media w dół, insiderzy kupują"})
    return out


def cached(path: str, rows: list[dict], today: str | None = None) -> list[dict]:
    """Raz dziennie (nagłówki zmieniają się wolno, a czuwanie działa co 30 minut)."""
    today = today or date.today().isoformat()
    try:
        old = json.load(open(path, encoding="utf-8"))
        if old.get("dzien") == today:
            return old.get("rozjazdy", [])
    except (OSError, ValueError):
        pass
    res = assess(rows)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"dzien": today, "rozjazdy": res}, f, ensure_ascii=False)
    return res
