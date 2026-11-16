"""Tryb ciągły: co kilkanaście minut pobiera najszybsze źródła, liczy indeksy i wysyła powiadomienie
tylko wtedy, gdy dzieje się coś nowego i istotnego. Nie używa AI, więc nie zużywa limitu Claude.

  python -m analizator watch --db analizator.db --interval 20            # pętla bez końca (serwer, komputer)
  python -m analizator watch --db analizator.db --once                   # jeden cykl (cron, harmonogram)

Powiadomienia: na telefon przez ntfy.sh (darmowa aplikacja ntfy, temat podany w zmiennej NTFY_TOPIC
albo w --ntfy), a zawsze także do pliku alerty.log obok bazy i na ekran.
"""
from __future__ import annotations

import json
import os
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta

from . import report, sources, store
from .score import PRIORITY_CATS, PRIORITY_SOURCES, assess, country_name, extract_signals
from .skutki import indices

FAST_PRIMARY = ["travel_us", "travel_uk", "easa", "faa", "ofac", "opensky"]  # szybkie, bez AIS (3 min) i danych dziennych
LEVELS = {"niski": 0, "podwyższony": 1, "wysoki": 2}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s.replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode()


def notify(title: str, body: str, topic: str | None, log_path: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # W publicznym repozytorium logi są jawne: z CICHO=1 treść alarmu nie trafia do logu (tylko do e-maila i strony z hasłem)
    print(f"\n[ALARM {stamp}]" + ("" if os.environ.get("CICHO") else f" {title}\n{body}"))
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {title}\n{body}\n\n")
    if topic:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                                     headers={"Title": _ascii(title)[:200], "Priority": "high", "Tags": "warning"})
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:
            print(f"  [ntfy] nie wysłano: {e}")


def _fetch(con, days: int, srcs: list[str]) -> None:
    sources.RETRIES = 2
    for src in srcs:
        try:
            if src == "pierwotne":
                from . import pierwotne
                arts = pierwotne.fetch_all(con, days, names=FAST_PRIMARY)
            else:
                arts = sources.FETCHERS[src](days=days)
            print(f"  [{src}] nowych: {store.save(con, arts)}")
        except Exception as e:
            print(f"  [{src}] pominięto: {e}")


def changes(results, state: dict, today: date, jump: float = 15.0) -> tuple[list[str], dict]:
    """Porównuje bieżące wyniki ze stanem z poprzedniego cyklu. Zwraca listę alarmów i nowy stan."""
    prev = state.get("kraje", {})
    seen = set(state.get("widziane", []))
    alerts, new_state, new_seen = [], {}, set(seen)
    recent = today - timedelta(days=2)
    for r in results:
        p = prev.get(r.country, {"indeks": 0, "poziom": "niski"})
        new_state[r.country] = {"indeks": round(r.index, 1), "poziom": r.level}
        reasons = []
        if LEVELS[r.level] > LEVELS.get(p["poziom"], 0):
            reasons.append(f"poziom {p['poziom']} -> {r.level}")
        elif r.index >= 40 and r.index - p["indeks"] >= jump:
            reasons.append(f"indeks {p['indeks']:.0f} -> {r.index:.0f}")
        fresh = []
        for x in r.evidence:
            key = x.get("url") or x["title"]
            if key in seen:
                continue
            new_seen.add(key)
            if x["date"] >= recent and not x.get("reactive") and not x.get("negated") and \
                    (x["category"] in PRIORITY_CATS or x.get("source") in PRIORITY_SOURCES):
                fresh.append(x)
        if fresh:
            reasons.append(f"nowe sygnały priorytetowe: {len(fresh)}")
        if reasons and state:  # pierwszy cykl tylko ustala punkt odniesienia
            ix = indices(r.country, r.level)
            lines = [f"{country_name(r.country)} ({r.country}): indeks {r.index:.0f}/100, {r.level}. " + "; ".join(reasons)]
            lines += [f"- {x['title'][:160]}" for x in (fresh or r.evidence)[:3]]
            if ix["down"]:
                lines.append("W dół: " + "; ".join(ix["down"][:3]))
            if ix["up"]:
                lines.append("W górę: " + "; ".join(ix["up"][:3]))
            alerts.append("\n".join(lines))
    return alerts, {"kraje": new_state, "widziane": sorted(new_seen)[-5000:], "czas": datetime.now().isoformat()}


def summary(results, n_articles: int, top: int = 10) -> str:
    """Krótki tekst do e-maila z codziennym raportem."""
    from .skutki import fronts
    L = [f"Analizator ruchów firm, {datetime.now():%Y-%m-%d %H:%M} UTC. {n_articles} artykułów z ostatniego roku.", "",
         "Najwyższe wskazania (indeks 0-100 to skala uwagi, nie prawdopodobieństwo):"]
    for r in results[:top]:
        prob = f", szansa wydarzenia w 60 dni wg modelu {r.prob:.0%}" if r.prob is not None else ""
        L.append(f"- {country_name(r.country)} ({r.country}): {r.index:.0f}, {r.level}{prob}. {', '.join(r.categories)}")
        if r.level != "niski":
            ix = indices(r.country, r.level)
            if ix["down"]:
                L.append("    w dół: " + "; ".join(ix["down"][:3]))
            if ix["up"]:
                L.append("    w górę: " + "; ".join(ix["up"][:3]))
            for x in r.evidence[:2]:
                L.append(f"    · {x['title'][:150]}")
    fr = fronts(results)
    if fr:
        L += ["", "Fronty (jeden kryzys w kilku krajach):"]
        L += [f"- {f['nazwa']}: " + ", ".join(f"{c} {i}" for c, i in f["kraje"]) for f in fr]
    L += ["", "Pełny raport: na stronie z hasłem albo w załączniku.",
          "To wskazówki z wiadomości, a nie prognoza ani rekomendacja inwestycyjna."]
    return "\n".join(L)


def cycle(db: str, out: str, srcs: list[str], days: int, topic: str | None, watchlist=None, alerts_out: str | None = None) -> int:
    base = os.path.dirname(os.path.abspath(db))
    state_path = os.path.join(base, "czuwanie_stan.json")
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    with store.local_copy(os.path.abspath(db)) as local:
        con = store.connect(local)
        _fetch(con, days, srcs)
        arts = store.load(con, (date.today() - timedelta(days=365)).isoformat())
        con.close()
    signals = extract_signals(arts, watchlist)
    results = assess(signals, today=date.today())
    with open(out, "w", encoding="utf-8") as f:
        f.write(report.to_html(results, len(arts), len(signals), "Analizator ruchów firm (tryb ciągły)"))
    alerts, new_state = changes(results, state, date.today())
    for a in alerts:
        notify("Analizator: " + a.split(":")[0], a, topic, os.path.join(base, "alerty.log"))
    if alerts_out:  # alarmy tylko z tego cyklu (np. dla GitHub Actions, które zakłada z nich zgłoszenie)
        with open(alerts_out, "w", encoding="utf-8") as f:
            f.write("\n\n".join(alerts))
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False)
    with open(os.path.join(base, "podsumowanie.txt"), "w", encoding="utf-8") as f:
        f.write(summary(results, len(arts)))
    print(f"{datetime.now():%H:%M} cykl: {len(arts)} artykułów, {len(results)} krajów, alarmów: {len(alerts)}")
    return len(alerts)


def watch(db: str, out: str, interval_min: int, once: bool, srcs: list[str], days: int, topic: str | None, watchlist=None,
          alerts_out: str | None = None) -> None:
    while True:
        try:
            cycle(db, out, srcs, days, topic, watchlist, alerts_out)
        except Exception as e:  # jeden nieudany cykl nie zatrzymuje czuwania
            print(f"cykl nieudany: {e}")
            if once:
                raise
        if once:
            return
        time.sleep(interval_min * 60)
