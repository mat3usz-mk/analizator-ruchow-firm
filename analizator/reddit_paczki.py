"""Liczniki z paczek z pełną kopią Reddita (zbiory „top 40k subreddits” do końca 2024 r., Academic Torrents).

Czyta plik <subreddit>_submissions.zst (NDJSON skompresowany zstd) strumieniowo i zapisuje dzienne liczby wpisów ze słowem
w tytule do tej samej bazy, której używa analizator.reddit_test (tabela counts), więc test nie musi pytać archiwum online.

    python -m analizator.reddit_paczki --plik worldnews_submissions.zst --sub worldnews --cache reddit.db
"""
from __future__ import annotations

import argparse
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone


def queries(sub: str) -> list[str]:
    if sub == "wallstreetbets":
        from .reddit_test import ASSETS
        return [q for q, _ in ASSETS.values()] + ["puts", "calls"]
    from .signals import COUNTRIES
    return [re.sub(r"\\[bB]|[()?\\]", "", names[0]) for names in COUNTRIES.values()]


def count(path: str, sub: str, y0: int = 2018, y1: int = 2024) -> dict[tuple[str, int], dict[str, int]]:
    import zstandard
    qs = queries(sub)
    pats = [(q, re.compile(r"\b" + re.escape(q) + r"\b", re.I)) for q in qs]
    out: dict[tuple[str, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    n = 0
    with open(path, "rb") as fh:
        reader = zstandard.ZstdDecompressor(max_window_size=2 ** 31).stream_reader(fh)
        for line in io.TextIOWrapper(reader, encoding="utf-8", errors="replace"):
            n += 1
            try:
                obj = json.loads(line)
                t = datetime.fromtimestamp(int(float(obj["created_utc"])), tz=timezone.utc)
            except (ValueError, KeyError, TypeError):
                continue
            if not (y0 <= t.year <= y1):
                continue
            title = obj.get("title") or ""
            day = t.date().isoformat()
            for q, p in pats:
                if p.search(title):
                    out[(q, t.year)][day] += 1
            if n % 2_000_000 == 0:
                print(f"  {sub}: {n} wpisów, ostatni {day}", flush=True)
    print(f"  {sub}: razem {n} wpisów", flush=True)
    return out


def main(argv=None) -> int:
    from .reddit_test import _con
    ap = argparse.ArgumentParser(prog="analizator.reddit_paczki")
    ap.add_argument("--plik", required=True)
    ap.add_argument("--sub", required=True)
    ap.add_argument("--cache", default="reddit.db")
    a = ap.parse_args(argv)
    res = count(a.plik, a.sub)
    con = _con(a.cache)
    qs = queries(a.sub)
    for q in qs:
        for y in range(2018, 2025):
            days = res.get((q, y), {})
            data = [{"created_utc": f"{d}T00:00:00.000Z", "count": str(v)} for d, v in sorted(days.items())]
            con.execute("INSERT OR REPLACE INTO counts VALUES (?,?,?,?)", (a.sub, q, y, json.dumps(data)))
    con.commit()
    print(f"zapisano {len(qs)} zapytań × 7 lat dla r/{a.sub}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
