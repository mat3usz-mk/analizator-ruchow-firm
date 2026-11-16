"""Historia GDELT z surowych plików GKG 2.0 (data.gdeltproject.org), bez limitu zapytań API.

API DOC ma limit ok. 1 zapytania na 5 s i ucina wyniki na 250, więc backfill dwóch lat trwa ~20 godzin
i gubi artykuły. Pliki GKG (co 15 minut, wszystkie artykuły anglojęzyczne monitorowane przez GDELT)
zawierają tytuł strony (<PAGE_TITLE>), domenę, adres i datę. Pobieramy je wszystkie z zakresu dat
i zapisujemy tylko te tytuły, z których klasyfikator (signals.classify) wyciąga sygnał, bo tylko one
wpływają na ocenę. Źródło w bazie: "gdelt" (jak przy API), więc reszta analizatora działa bez zmian.

    python3 -m analizator.gdelt_pliki --from 2025-01-01 --to 2026-11-15 --db /tmp/h_gdelt_pliki.db

Wznawialne: zrobione pliki są w tabeli gdelt_files_done. Domena data.gdeltproject.org musi być dozwolona.
Uwaga przy porównaniach: API szuka fraz w całej treści, a tu filtrem jest tytuł, więc to inne (pełniejsze
w czasie, węższe w treści) dane niż backfill przez API.
"""
from __future__ import annotations

import argparse
import io
import re
import sqlite3
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date

from . import signals, store

MASTER = "https://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
_TITLE = re.compile(rb"<PAGE_TITLE>(.*?)</PAGE_TITLE>")
_COUNTRY = re.compile(r"\b(?:" + signals._ALL_COUNTRY_NAMES + r")", re.I)


def _get(url: str, tries: int = 5, timeout: int = 120) -> bytes:
    delay = 3.0
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "analizator/0.3"}), timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def file_list(start: date, end: date) -> list[str]:
    a, b = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    out = []
    for line in _get(MASTER).decode().splitlines():
        url = line.rsplit(" ", 1)[-1].replace("http://", "https://", 1)
        if url.endswith(".gkg.csv.zip"):
            stamp = url.rsplit("/", 1)[-1][:8]
            if a <= stamp <= b:
                out.append(url)
    return out


def process(url: str) -> tuple[str, list[tuple], int]:
    """Zwraca (url pliku, wiersze do zapisania, liczba artykułów w pliku)."""
    try:
        raw = _get(url)
    except Exception as e:
        if "404" in str(e):  # GDELT ma pojedyncze brakujące pliki
            return url, [], -404
        raise
    z = zipfile.ZipFile(io.BytesIO(raw))
    data = z.read(z.namelist()[0])
    rows, n = [], 0
    for line in data.split(b"\n"):
        m = _TITLE.search(line)
        if not m:
            continue
        n += 1
        title = m.group(1).decode("utf-8", "replace").strip()
        if not title or not _COUNTRY.search(title) or not signals.classify(title):
            continue
        f = line.split(b"\t", 5)
        if len(f) < 5:
            continue
        d = f[1].decode()
        rows.append((f[4].decode("utf-8", "replace"), title, f"{d[:4]}-{d[4:6]}-{d[6:8]}", "gdelt", f[3].decode("utf-8", "replace"), "en"))
    return url, rows, n


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="analizator.gdelt_pliki")
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", default=date.today().isoformat())
    p.add_argument("--db", default="historia_gdelt_pliki.db")
    p.add_argument("--workers", type=int, default=6)
    a = p.parse_args(argv)
    con = store.connect(a.db)
    con.execute("CREATE TABLE IF NOT EXISTS gdelt_files_done (file TEXT PRIMARY KEY, n_all INTEGER, n_saved INTEGER)")
    done = {r[0] for r in con.execute("SELECT file FROM gdelt_files_done")}
    todo = [u for u in file_list(date.fromisoformat(a.start), date.fromisoformat(a.end)) if u not in done]
    print(f"plików do pobrania: {len(todo)} (zrobione wcześniej: {len(done)})", flush=True)
    t0, k, failed = time.time(), 0, 0
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(process, u) for u in todo]
        for fut in as_completed(futs):
            try:
                url, rows, n = fut.result()
            except Exception as e:
                failed += 1
                print(f"  błąd: {e}", flush=True)
                continue
            con.executemany("INSERT OR IGNORE INTO articles(url, title, date, source, domain, lang) VALUES (?,?,?,?,?,?)", rows)
            con.execute("INSERT OR REPLACE INTO gdelt_files_done VALUES (?,?,?)", (url, n, len(rows)))
            k += 1
            if k % 200 == 0:
                con.commit()
                el = time.time() - t0
                print(f"{k}/{len(todo)} plików, {el / 60:.0f} min, zostało ok. {el / k * (len(todo) - k) / 60:.0f} min", flush=True)
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    print(f"koniec: {k} plików, błędów {failed} (uruchom ponownie, żeby je dobrać), artykułów w bazie {total}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
