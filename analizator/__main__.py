"""Uruchamianie:

  python -m analizator demo                     # dane syntetyczne, bez internetu
  python -m analizator fetch --days 30          # pobierz wiadomości do bazy
  python -m analizator analyze                  # policz i zapisz raport.html
  python -m analizator run --days 30            # fetch + analyze
  python -m analizator backfill --from 2025-01-01 --to 2026-11-14 --db historia.db
  python -m analizator backtest --db historia.db --events wydarzenia.csv --from 2025-03-01 --to 2026-11-14
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

from . import demo, report, sources, store
from .score import assess, extract_signals


def _load_watchlist(path: str = "watchlist.txt") -> list[str] | None:
    if not os.path.exists(path):
        return None
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]


def _analyze(articles: list[dict], out: str, title: str, today: date | None = None, con=None) -> None:
    signals = extract_signals(articles, _load_watchlist())
    results = assess(signals, today=today)
    insiders = []
    if con is not None:
        from . import pierwotne
        insiders = pierwotne.insider_panel(con)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report.to_html(results, len(articles), len(signals), title, insiders=insiders))
    report.to_csv(results, os.path.splitext(out)[0] + ".csv")
    report.to_candidates_json(results, os.path.join(os.path.dirname(os.path.abspath(out)), "kandydaci.json"))
    print(f"\n{len(articles)} artykułów -> {len(signals)} sygnałów -> {len(results)} krajów")
    print(f"{'kraj':<6}{'indeks':>8}  {'poziom':<12}{'pewność':<10}{'firm':>5}  kategorie")
    for r in results[:12]:
        print(f"{r.country:<6}{r.index:>8.0f}  {r.level:<12}{r.confidence:<10}{r.companies:>5}  {', '.join(r.categories)}"
              + (f"  [ciche: {r.quiet}]" if r.quiet else ""))
    print(f"\nRaport: {os.path.abspath(out)}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="analizator", description="Szuka nietypowych ruchów dużych firm w wiadomościach.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--days", type=int, default=30)
        sp.add_argument("--sources", default="gdelt,gnews,sec,rss,pierwotne")
    for name in ("analyze", "run", "demo"):
        sp = sub.choices.get(name) or sub.add_parser(name)
        sp.add_argument("--out", default="raport_demo.html" if name == "demo" else "raport.html")
    sub.choices["analyze"].add_argument("--since-days", type=int, default=365)
    for name in ("fetch", "run", "analyze"):
        sub.choices[name].add_argument("--db", default="analizator.db")
    bf = sub.add_parser("backfill", help="pobierz historię okno po oknie")
    bf.add_argument("--from", dest="start", required=True)
    bf.add_argument("--to", dest="end", default=date.today().isoformat())
    bf.add_argument("--db", default="historia.db")
    bf.add_argument("--window", type=int, default=14)
    bf.add_argument("--sources", default="gdelt,gnews,sec")
    bf.add_argument("--redo-empty", action="store_true", help="ponów okna zapisane z zerem artykułów")
    bf.add_argument("--redo-all", action="store_true", help="pobierz wszystkie okna od nowa (np. po dodaniu zapytań)")
    w = sub.add_parser("watch", help="tryb ciągły: pobieraj co N minut i powiadamiaj tylko o istotnych zmianach")
    w.add_argument("--db", default="analizator.db")
    w.add_argument("--out", default="raport_biezacy.html")
    w.add_argument("--interval", type=int, default=20, help="minuty między cyklami")
    w.add_argument("--once", action="store_true", help="jeden cykl i koniec (dla crona / harmonogramu)")
    w.add_argument("--days", type=int, default=2)
    w.add_argument("--sources", default="gdelt,gnews,pierwotne")
    w.add_argument("--ntfy", default=os.environ.get("NTFY_TOPIC"), help="temat ntfy.sh do powiadomień na telefon")
    w.add_argument("--alerts-out", default=None, help="zapisz alarmy z tego cyklu do pliku")
    bt = sub.add_parser("backtest", help="odtwórz oceny tydzień po tygodniu i porównaj z wydarzeniami")
    bt.add_argument("--db", default="historia.db")
    bt.add_argument("--events", default="wydarzenia.csv")
    bt.add_argument("--from", dest="start", required=True)
    bt.add_argument("--to", dest="end", default=date.today().isoformat())
    bt.add_argument("--out", default="backtest.html")
    bt.add_argument("--threshold", type=float, default=40.0)
    bt.add_argument("--horizon", type=int, default=60)
    bt.add_argument("--step", type=int, default=1, help="co ile dni liczyć ocenę (1 = jak codzienne zadanie)")
    return p


def main(argv: list[str] | None = None) -> int:
    p = _parser()
    a = p.parse_args(argv)
    # ścieżki bezwzględne liczymy od razu: katalog roboczy na dysku sieciowym potrafi zniknąć w trakcie pracy
    for attr in ("out", "events", "alerts_out"):
        if getattr(a, attr, None):
            setattr(a, attr, os.path.abspath(getattr(a, attr)))
    if getattr(a, "db", None) and a.cmd in ("fetch", "run", "analyze", "backfill"):
        # zawsze pracuj na lokalnej kopii bazy (dysk sieciowy źle znosi zapisy SQLite)
        with store.local_copy(os.path.abspath(a.db)) as local:
            a.db = local
            return _dispatch(a)
    return _dispatch(a)


def _dispatch(a) -> int:

    if a.cmd == "backfill":
        from .backtest import backfill
        srcs = tuple(x.strip() for x in a.sources.split(","))
        if a.redo_all:
            con = store.connect(a.db)
            con.execute("CREATE TABLE IF NOT EXISTS backfill_done (source TEXT, start TEXT, n INTEGER, PRIMARY KEY (source, start))")
            con.executemany("DELETE FROM backfill_done WHERE source=?", [(x,) for x in srcs])
            con.commit()
        backfill(a.db, date.fromisoformat(a.start), date.fromisoformat(a.end), a.window, srcs, a.redo_empty)
        return 0
    if a.cmd == "backtest":
        from .backtest import run
        ev = run(a.db, a.events, date.fromisoformat(a.start), date.fromisoformat(a.end), a.out, a.threshold, a.horizon, _load_watchlist(), step_days=a.step)
        f = lambda x: "brak" if x is None else f"{x:.0%}"
        print(f"Trafione wydarzenia: {f(ev['hit_rate'])} · z zaskoczenia: {f(ev['hit_rate_fresh'])} ({ev['n_fresh']}/{ev['n_events']}) · trafne alarmy: {f(ev['precision'])} · mediana wyprzedzenia: {ev['median_lead']} dni")
        for b, n, h, r in ev["calibration"]:
            print(f"  indeks {b}: {n} tygodni, z wydarzeniem {h} ({f(r)})")
        print(f"Raport: {os.path.abspath(a.out)}")
        return 0

    if a.cmd == "watch":
        from .czuwanie import watch
        watch(a.db, a.out, a.interval, a.once, [x.strip() for x in a.sources.split(",")], a.days, a.ntfy, _load_watchlist(), a.alerts_out)
        return 0

    if a.cmd == "demo":
        _analyze(demo.generate(), a.out, "Analizator ruchów firm: DEMO (dane syntetyczne)")
        return 0

    if a.cmd in ("fetch", "run"):
        con = store.connect(a.db)
        for src in a.sources.split(","):
            if src.strip() == "pierwotne":
                from . import pierwotne
                print("Pobieram: źródła pierwotne...")
                arts = pierwotne.fetch_all(con, a.days)
                print(f"  razem {len(arts)} rekordów, nowych w bazie: {store.save(con, arts)}")
                continue
            fn = sources.FETCHERS.get(src.strip())
            if not fn:
                print(f"Nieznane źródło: {src}")
                continue
            print(f"Pobieram: {src} ({a.days} dni)...")
            arts = fn(days=a.days)
            print(f"  {len(arts)} artykułów, nowych w bazie: {store.save(con, arts)}")
        if a.cmd == "fetch":
            return 0

    con = store.connect(a.db)
    since = (date.today() - timedelta(days=getattr(a, "since_days", 365))).isoformat()
    arts = store.load(con, since)
    if not arts:
        print("Baza jest pusta. Najpierw: python -m analizator fetch")
        return 1
    _analyze(arts, a.out, "Analizator ruchów firm", today=date.today(), con=con)
    return 0


if __name__ == "__main__":
    sys.exit(main())
