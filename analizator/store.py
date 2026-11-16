"""Lokalna baza SQLite: artykuły zbierane codziennie budują historię (tło) dla porównań."""
from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import tempfile

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT, source TEXT, domain TEXT, lang TEXT,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date);
"""


def connect(path: str = "analizator.db") -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def save(con: sqlite3.Connection, articles: list[dict]) -> int:
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO articles(url, title, date, source, domain, lang) VALUES (?,?,?,?,?,?)",
        [(a["url"] or f"no-url:{a['title']}", a["title"], a.get("date"), a.get("source"), a.get("domain"), a.get("lang"))
         for a in articles if a.get("title")],
    )
    con.commit()
    return con.total_changes - before


def load(con: sqlite3.Connection, since: str | None = None) -> list[dict]:
    q = "SELECT url, title, date, source, domain, lang FROM articles"
    rows = con.execute(q + (" WHERE date >= ?" if since else ""), (since,) if since else ()).fetchall()
    return [dict(zip(("url", "title", "date", "source", "domain", "lang"), r)) for r in rows]


@contextlib.contextmanager
def local_copy(path: str):
    """SQLite na dysku sieciowym (np. /mnt/project-files) bywa "readonly" albo blokuje zapis.
    Pracujemy na kopii w katalogu tymczasowym i na końcu podmieniamy plik atomowo."""
    tmpdir = tempfile.mkdtemp(prefix="analizator-")
    local = os.path.join(tmpdir, os.path.basename(path))
    if os.path.exists(path):
        shutil.copy2(path, local)
    try:
        yield local
    finally:
        if os.path.exists(local):
            staged = path + ".nowy"
            shutil.copy2(local, staged)
            os.replace(staged, path)
        shutil.rmtree(tmpdir, ignore_errors=True)
