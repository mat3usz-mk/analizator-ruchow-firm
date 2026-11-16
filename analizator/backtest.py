"""Test na danych historycznych.

1. backfill: pobiera wiadomości okno po oknie (domyślnie co 14 dni) do osobnej bazy.
   Da się przerwać i wznowić: zrobione okna są zapisywane w tabeli backfill_done.
2. evaluate: dla każdego tygodnia T liczy oceny WYŁĄCZNIE z danych sprzed T
   (tak, jakby analizator działał wtedy na żywo), a potem porównuje z listą
   rzeczywistych wydarzeń (wydarzenia.csv).

Miary:
- trafienie: wydarzenie, przed którym indeks kraju przekroczył próg w ciągu `horizon` dni;
- wyprzedzenie: ile dni przed wydarzeniem pierwszy raz przekroczono próg;
- fałszywy alarm: epizod alarmowy (kolejne tygodnie powyżej progu), po którym w ciągu
  `horizon` dni nic się w tym kraju nie wydarzyło;
- kalibracja: dla przedziałów indeksu, jak często w ciągu `horizon` dni nastąpiło wydarzenie.
  To jest droga do zamiany indeksu na prawdziwe prawdopodobieństwo.
"""
from __future__ import annotations

import csv
import html
import time
from collections import defaultdict
from datetime import date, timedelta

from . import sources, store
from .score import assess, country_name, extract_signals, week_start


def backfill(db: str, start: date, end: date, window_days: int = 14, source_names: tuple[str, ...] = ("gdelt", "gnews", "sec"),
             redo_empty: bool = False) -> None:
    con = store.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS backfill_done (source TEXT, start TEXT, n INTEGER, PRIMARY KEY (source, start))")
    fetchers = {"gdelt": sources.gdelt, "gnews": sources.google_news,
                # w historii mniej dokumentów SEC na okno, inaczej pobieranie trwałoby wiele godzin
                "sec": lambda start, end: sources.sec_edgar(start=start, end=end, max_docs=120)}
    windows = []
    d = start
    while d <= end:
        windows.append((d, min(d + timedelta(days=window_days - 1), end)))
        d += timedelta(days=window_days)
    for name in source_names:
        fn = fetchers[name]
        for a, b in windows:
            done = con.execute("SELECT n FROM backfill_done WHERE source=? AND start=?", (name, a.isoformat())).fetchone()
            if done and not (redo_empty and done[0] == 0):
                continue
            t0 = time.time()
            sources.LAST_ERRORS["n"] = 0
            try:
                arts = fn(start=a, end=b)
            except Exception as e:  # jedno złe okno nie przerywa całości
                print(f"[{name}] {a}..{b}: błąd {e}")
                continue
            if not arts and sources.LAST_ERRORS["n"]:
                print(f"[{name}] {a}..{b}: same błędy ({sources.LAST_ERRORS['n']}), okno zostaje do ponowienia")
                continue
            # Odrzuć artykuły spoza okna (wyszukiwarki czasem zwracają nowsze)
            arts = [x for x in arts if x.get("date") and a.isoformat() <= x["date"][:10] <= b.isoformat()]
            n = store.save(con, arts)
            con.execute("INSERT OR REPLACE INTO backfill_done VALUES (?,?,?)", (name, a.isoformat(), n))
            con.commit()
            print(f"[{name}] {a}..{b}: {len(arts)} artykułów, nowych {n} ({time.time() - t0:.0f}s)", flush=True)


def load_events(path: str) -> list[dict]:
    """CSV: data,kraj,opis,typ,zrodlo (data RRRR-MM-DD, kraj = kod ISO-2 jak w signals.COUNTRIES)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("data") or row["data"].startswith("#"):
                continue
            out.append({**row, "data": date.fromisoformat(row["data"].strip()), "kraj": row["kraj"].strip().upper()})
    return out


def replay(signals: list[dict], start: date, end: date, params: dict | None = None, step_days: int = 7) -> dict[tuple[str, date], float]:
    """Indeks dla każdego (kraj, tydzień), licząc tylko z danych dostępnych do końca tego tygodnia."""
    signals = sorted(signals, key=lambda s: s["date"])
    out: dict[tuple[str, date], float] = {}
    t = week_start(start) + timedelta(days=6) if step_days == 7 else start
    while t <= end:
        known = [s for s in signals if s["date"] <= t]
        for r in assess(known, today=t, params=params):
            out[(r.country, t)] = r.index
        t += timedelta(days=step_days)
    return out


def evaluate(index: dict[tuple[str, date], float], events: list[dict], threshold: float = 40.0, horizon: int = 60) -> dict:
    weeks = sorted({t for _, t in index})
    countries = sorted({c for c, _ in index} | {e["kraj"] for e in events})
    ev_by_c: dict[str, list[date]] = defaultdict(list)
    for e in events:
        ev_by_c[e["kraj"]].append(e["data"])

    # Trafienia i wyprzedzenie
    results = []
    for e in events:
        if not weeks or e["data"] <= weeks[0] + timedelta(days=28) or e["data"] > weeks[-1] + timedelta(days=horizon):
            results.append({**e, "status": "poza zakresem testu", "lead": None, "max_index": None})
            continue
        pre = [(t, index.get((e["kraj"], t), 0.0)) for t in weeks if e["data"] - timedelta(days=horizon) <= t < e["data"]]
        alarms = [t for t, v in pre if v >= threshold]
        # "Zaskoczenie": kraj nie był w alarmie przez 90 dni przed oknem prognozy. Tylko tu trafienie znaczy naprawdę coś.
        earlier = [index.get((e["kraj"], t), 0.0) for t in weeks
                   if e["data"] - timedelta(days=horizon + 90) <= t < e["data"] - timedelta(days=horizon)]
        surprise = not any(v >= threshold for v in earlier)
        results.append({**e, "status": "trafione" if alarms else "przegapione", "zaskoczenie": surprise,
                        "lead": (e["data"] - alarms[0]).days if alarms else None,
                        "max_index": max((v for _, v in pre), default=0.0)})

    # Epizody alarmowe i fałszywe alarmy
    episodes = []
    for c in countries:
        cur = None
        for t in weeks:
            v = index.get((c, t), 0.0)
            if v >= threshold:
                if cur is None:
                    cur = {"kraj": c, "start": t, "end": t, "peak": v}
                cur["end"], cur["peak"] = t, max(cur["peak"], v)
            elif cur:
                episodes.append(cur)
                cur = None
        if cur:
            episodes.append(cur)
    last_week = weeks[-1] if weeks else date.today()
    for ep in episodes:
        ev = [d for d in ev_by_c.get(ep["kraj"], []) if ep["start"] - timedelta(days=7) <= d <= ep["end"] + timedelta(days=horizon)]
        if ev:
            ep["wynik"] = "prawdziwy alarm"
        elif (last_week - ep["end"]).days < horizon:
            ep["wynik"] = "za wcześnie, by ocenić"
        else:
            ep["wynik"] = "fałszywy alarm"

    # Kalibracja: przedział indeksu -> odsetek tygodni, po których w ciągu horyzontu było wydarzenie
    buckets = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
    calib = {b: [0, 0] for b in buckets}
    for (c, t), v in index.items():
        if (last_week - t).days < horizon:
            continue
        hit = any(t < d <= t + timedelta(days=horizon) for d in ev_by_c.get(c, []))
        for b in buckets:
            if b[0] <= v < b[1]:
                calib[b][0] += 1
                calib[b][1] += hit
    in_range = [r for r in results if r["status"] != "poza zakresem testu"]
    fresh = [r for r in in_range if r.get("zaskoczenie")]
    judged = [e for e in episodes if e["wynik"] != "za wcześnie, by ocenić"]
    return {
        "threshold": threshold, "horizon": horizon, "events": results, "episodes": episodes,
        "calibration": [(f"{a}–{min(b, 100)}", n, h, (h / n) if n else None) for (a, b), (n, h) in calib.items()],
        "hit_rate": (sum(r["status"] == "trafione" for r in in_range) / len(in_range)) if in_range else None,
        "hit_rate_fresh": (sum(r["status"] == "trafione" for r in fresh) / len(fresh)) if fresh else None,
        "n_fresh": len(fresh), "n_events": len(in_range),
        "precision": (sum(e["wynik"] == "prawdziwy alarm" for e in judged) / len(judged)) if judged else None,
        "median_lead": sorted(r["lead"] for r in in_range if r["lead"] is not None)[len([r for r in in_range if r["lead"] is not None]) // 2]
        if any(r["lead"] is not None for r in in_range) else None,
    }


def write_report(ev: dict, index: dict, path: str, n_articles: int, n_signals: int) -> None:
    e = html.escape
    pct = lambda x: "brak danych" if x is None else f"{x:.0%}"
    rows_ev = "".join(
        f"<tr><td>{r['data']}</td><td>{e(country_name(r['kraj']))}</td><td>{e(r.get('opis', ''))}</td>"
        f"<td class='{'ok' if r['status'] == 'trafione' else 'bad' if r['status'] == 'przegapione' else 'muted'}'>{r['status']}</td>"
        f"<td>{'tak' if r.get('zaskoczenie') else 'nie' if 'zaskoczenie' in r else ''}</td><td>{'' if r['lead'] is None else str(r['lead']) + ' dni'}</td><td>{'' if r['max_index'] is None else round(r['max_index'])}</td>"
        f"<td>{'<a href=' + chr(34) + e(r.get('zrodlo', '')) + chr(34) + '>źródło</a>' if r.get('zrodlo', '').startswith('http') else e(r.get('zrodlo', ''))}</td></tr>"
        for r in sorted(ev["events"], key=lambda r: r["data"]))
    rows_ep = "".join(
        f"<tr><td>{e(country_name(x['kraj']))}</td><td>{x['start']} – {x['end']}</td><td>{round(x['peak'])}</td>"
        f"<td class='{'ok' if x['wynik'] == 'prawdziwy alarm' else 'bad' if x['wynik'] == 'fałszywy alarm' else 'muted'}'>{x['wynik']}</td></tr>"
        for x in sorted(ev["episodes"], key=lambda x: x["start"]))
    rows_cal = "".join(f"<tr><td>{b}</td><td>{n}</td><td>{h}</td><td>{pct(r)}</td></tr>" for b, n, h, r in ev["calibration"])
    page = f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test historyczny analizatora</title><style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e4e3de;--ok:#3f7f4f;--bad:#b4442f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;--card:#20201e;--line:#34332f;--ok:#7fb07f;--bad:#e0705a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}main{{max-width:1000px;margin:0 auto;padding:24px 16px 64px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 24px}}td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
.ok{{color:var(--ok);font-weight:600}}.bad{{color:var(--bad);font-weight:600}}.muted{{color:var(--muted)}}
.kpi{{display:flex;flex-wrap:wrap;gap:12px}}.kpi div{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:180px}}
.kpi b{{display:block;font-size:26px}}.wrap{{overflow-x:auto}}a{{color:inherit}}</style></head><body><main>
<h1>Test historyczny analizatora</h1>
<p class="muted">{n_articles} artykułów · {n_signals} sygnałów · próg alarmu: indeks ≥ {ev['threshold']:.0f} · horyzont: {ev['horizon']} dni</p>
<div class="kpi"><div>Trafione wydarzenia<b>{pct(ev['hit_rate'])}</b></div><div>Trafione „z zaskoczenia”<b>{pct(ev['hit_rate_fresh'])}</b><span class="muted">{ev['n_fresh']} z {ev['n_events']} wydarzeń</span></div><div>Trafne alarmy<b>{pct(ev['precision'])}</b></div>
<div>Mediana wyprzedzenia<b>{'brak' if ev['median_lead'] is None else str(ev['median_lead']) + ' dni'}</b></div></div>
<h2>Wydarzenia</h2><div class="wrap"><table><tr><th>Data</th><th>Kraj</th><th>Wydarzenie</th><th>Wynik</th><th>Zaskoczenie</th><th>Wyprzedzenie</th><th>Maks. indeks przed</th><th>Źródło</th></tr>{rows_ev}</table></div>
<h2>Alarmy</h2><div class="wrap"><table><tr><th>Kraj</th><th>Okres</th><th>Szczyt</th><th>Ocena</th></tr>{rows_ep or '<tr><td colspan=4>brak</td></tr>'}</table></div>
<h2>Kalibracja</h2><p>Jak często w ciągu {ev['horizon']} dni nastąpiło wydarzenie, gdy indeks był w danym przedziale (liczone dla każdego dnia i kraju). Gdy będzie dużo danych,
te odsetki można traktować jako przybliżone prawdopodobieństwo.</p>
<div class="wrap"><table><tr><th>Indeks</th><th>Dni (kraj×dzień)</th><th>Z wydarzeniem</th><th>Odsetek</th></tr>{rows_cal}</table></div>
<h2>Uwaga</h2><p>Słowa kluczowe i profile krajów powstały z wiedzą o części tych wydarzeń, więc wynik może być zawyżony
(efekt wiedzy po fakcie). Wyszukiwarki pokazują dziś archiwum inaczej, niż wyglądały wiadomości wtedy. Lista wydarzeń
decyduje o wyniku: co liczymy jako „coś większego”, jest opisane w wydarzenia.csv.</p>
</main></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    with open(path.rsplit(".", 1)[0] + "_indeksy.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tydzien_do", "kraj", "indeks"])
        for (c, t), v in sorted(index.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            w.writerow([t.isoformat(), c, v])


def run(db: str, events_path: str, start: date, end: date, out: str, threshold: float, horizon: int, watchlist=None,
        params: dict | None = None, step_days: int = 1) -> dict:
    arts = store.load(store.connect(db))
    signals = extract_signals(arts, watchlist)
    index = replay(signals, start, end, params, step_days)
    ev = evaluate(index, load_events(events_path), threshold, horizon)
    write_report(ev, index, out, len(arts), len(signals))
    return ev
