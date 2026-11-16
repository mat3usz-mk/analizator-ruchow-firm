"""Własna historia do przyszłych testów: raz dziennie zapisuje pomiary, których nie da się później pobrać za darmo
(insiderzy Form 4, opcje put/call, krótka sprzedaż, statki AIS, loty, transakcje kongresmenów, stany ostrzeżeń)
oraz dzienne wyniki analizatora (indeks, poziom, impuls i szansa wg modelu dla każdego kraju).

Pliki CSV trafiają do katalogu (w GitHub Actions: osobna gałąź `archiwum`), jeden folder na dzień:
  archiwum/2026-11-16/pomiary.csv, stany.csv, kongres.csv, wyniki.csv

    python -m analizator.archiwum --db dane/analizator.db --stan dane/czuwanie_stan.json --out archiwum_git/archiwum
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from datetime import date


def _write(path: str, header: list[str], rows) -> int:
    rows = list(rows)
    if not rows:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def _table(con, name: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def export(db: str, out: str, state_path: str | None = None, since: str | None = None, today: str | None = None) -> dict:
    """Zapisuje dni po `since` (bez niego: wszystko, co jest w bazie). Zwraca liczbę wierszy na plik."""
    today = today or date.today().isoformat()
    con = sqlite3.connect(db)
    n = {"pomiary": 0, "stany": 0, "kongres": 0, "wyniki": 0}
    since = since or "0000"
    days = set()
    for t in ("metrics", "snapshots"):
        if _table(con, t):
            days |= {d for (d,) in con.execute(f"SELECT DISTINCT day FROM {t} WHERE day>?", (since,))}
    for d in sorted(days):
        if _table(con, "metrics"):
            n["pomiary"] += _write(os.path.join(out, d, "pomiary.csv"), ["zrodlo", "klucz", "dzien", "wartosc"],
                                   con.execute("SELECT source, key, day, value FROM metrics WHERE day=? ORDER BY source, key", (d,)))
        if _table(con, "snapshots"):
            n["stany"] += _write(os.path.join(out, d, "stany.csv"), ["zrodlo", "klucz", "dzien", "wartosc"],
                                 con.execute("SELECT source, key, day, value FROM snapshots WHERE day=? ORDER BY source, key", (d,)))
    if _table(con, "kongres"):
        rows = con.execute("SELECT doc, kto, ticker, typ, data, zgloszono FROM kongres WHERE COALESCE(zgloszono, data)>? "
                           "ORDER BY zgloszono, kto", (since,)).fetchall()
        n["kongres"] = _write(os.path.join(out, today, "kongres.csv"),
                              ["dokument", "kto", "spolka", "typ", "data_transakcji", "data_zgloszenia"], rows)
    con.close()
    if state_path and os.path.exists(state_path):
        st = json.load(open(state_path, encoding="utf-8")).get("kraje", {})
        n["wyniki"] = _write(os.path.join(out, today, "wyniki.csv"), ["kraj", "indeks", "poziom", "impuls", "szansa_model"],
                             [(c, v.get("indeks"), v.get("poziom"), v.get("impuls"), v.get("szansa")) for c, v in sorted(st.items())])
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.archiwum")
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stan", default=None)
    ap.add_argument("--od", default=None, help="tylko dni po tej dacie (domyślnie z pliku ostatnie_archiwum.txt obok bazy)")
    a = ap.parse_args(argv)
    mark = os.path.join(os.path.dirname(os.path.abspath(a.db)), "ostatnie_archiwum.txt")
    since = a.od or (open(mark).read().strip() if os.path.exists(mark) else None)
    today = date.today().isoformat()
    if since == today:
        print("archiwum: dzisiejszy zapis już jest")
        return 0
    # dzień `since` mógł być zapisany w połowie (pomiary dochodzą przez cały dzień), więc zapisujemy go jeszcze raz
    n = export(a.db, a.out, a.stan, since=(None if since is None else _day_before(since)), today=today)
    print(f"archiwum: {n}")
    with open(mark, "w") as f:
        f.write(today)
    return 0


def _day_before(d: str) -> str:
    from datetime import timedelta
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
