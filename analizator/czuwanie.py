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
from .score import PRIORITY_CATS, PRIORITY_SOURCES, assess, category_label, country_name, extract_signals
from .skutki import indices

FAST_PRIMARY = ["travel_us", "travel_uk", "easa", "faa", "ofac", "opensky", "oficjalne_rss", "kursy", "agsi", "finra_short", "opcje", "kongres", "portwatch", "sankcje_ue_uk"]  # szybkie, bez AIS (3 min) i danych dziennych
# DSCA (sprzedaż broni USA) wyłączone: w teście 2025–2026 +1 trafienie przy +17 fałszywych alarmach (raporty/pierwotne-dsca.md)
LEVELS = {"niski": 0, "podwyższony": 1, "wysoki": 2}
IMPULSE_ALARM = 10.0  # test 2019–2026 (raporty/impuls-wyniki.md): precyzja 12–17%, ok. 4× lepiej niż losowo


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


STATUS: dict[str, str] = {}
LAST_ALARMS: list = []  # (wynik kraju, powody) z ostatniego wywołania changes(), do dziennika trafności


def _fetch(con, days: int, srcs: list[str]) -> None:
    sources.RETRIES = 2
    for src in srcs:
        try:
            if src == "pierwotne":
                from . import pierwotne
                # AIS (statki w cieśninach) tylko z kluczem; słucha strumienia ok. 3 min
                names = [n for n in FAST_PRIMARY if n != "agsi" or os.environ.get("AGSI_KEY")]
                names += ["ais"] if os.environ.get("AISSTREAM_API_KEY") else []
                arts = pierwotne.fetch_all(con, days, names=names)
            else:
                arts = sources.FETCHERS[src](days=days)
            n = store.save(con, arts)
            print(f"  [{src}] nowych: {n}")
            STATUS[src] = f"nowych: {n}"
        except Exception as e:
            print(f"  [{src}] pominięto: {e}")
            STATUS[src] = f"błąd: {str(e)[:160]}"


def _load_json(path: str):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def changes(results, state: dict, today: date, jump: float = 15.0) -> tuple[list[str], dict]:
    """Porównuje bieżące wyniki ze stanem z poprzedniego cyklu. Zwraca listę alarmów i nowy stan."""
    LAST_ALARMS.clear()
    prev = state.get("kraje", {})
    seen = set(state.get("widziane", []))
    alerts, new_state, new_seen = [], {}, set(seen)
    recent = today - timedelta(days=2)
    for r in results:
        p = prev.get(r.country, {"indeks": 0, "poziom": "niski"})
        new_state[r.country] = {"indeks": round(r.index, 1), "poziom": r.level, "impuls": round(r.impulse, 1),
                             "szansa": None if r.prob is None else round(r.prob, 3)}
        reasons = []
        if r.impulse >= IMPULSE_ALARM and p.get("impuls", 0) < IMPULSE_ALARM and r.impulse_info.get("historii", 0) >= 2:
            info = r.impulse_info
            reasons.append(f"nagły impuls: w 48 h {info['historii']} nowe sprawy, siła {info['teraz']:.1f} wobec zwykłych {info['norma']:.1f}")
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
            if x["date"] >= recent and not x.get("reactive") and not x.get("negated") and not x.get("reprint") and \
                    (x["category"] in PRIORITY_CATS or x.get("source") in PRIORITY_SOURCES):
                fresh.append(x)
        if fresh:
            reasons.append(f"nowe sygnały priorytetowe: {len(fresh)}")
        if reasons and state:  # pierwszy cykl tylko ustala punkt odniesienia
            from .skutki import forecast_lines
            lines = [f"{country_name(r.country)} ({r.country}): indeks {r.index:.0f}/100, poziom {r.level}.",
                     "Zmiana: " + "; ".join(reasons) + ".", "Fakty:"]
            lines += [f"- {x['date']} {x['title'][:160]}" for x in (fresh or r.evidence)[:3]]
            if getattr(r, "slady", None):
                sl = r.slady[0]
                lines += [f"Potwierdzenie: zbieżne niezależne ślady ({sl['a']} → {sl['b']}, do {sl['dni']} dni); alarmy z takim potwierdzeniem "
                          "w teście 2025–2026 trafne w 18% wobec 11% bez."]
            else:
                lines += ["Potwierdzenie: brak zbieżnych niezależnych śladów (w teście takie alarmy trafne w ok. 8%)."]
            lines += ["Prognoza:"] + [f"- {x}" for x in forecast_lines(r)]
            alerts.append("\n".join(lines))
            LAST_ALARMS.append((r, reasons))
    return alerts, {"kraje": new_state, "widziane": sorted(new_seen)[-5000:], "czas": datetime.now().isoformat()}


def summary(results, n_articles: int, top: int = 10) -> str:
    """Krótki tekst do e-maila z codziennym raportem."""
    from .skutki import fronts
    L = [f"Analizator ruchów firm, {datetime.now():%Y-%m-%d %H:%M} UTC. {n_articles} artykułów z ostatniego roku.", "",
         "Najwyższe wskazania (indeks 0-100 to skala uwagi, nie prawdopodobieństwo):"]
    for r in results[:top]:
        prob = f", szansa wydarzenia w 60 dni wg modelu {r.prob:.0%}" if r.prob is not None else ""
        L.append(f"- {country_name(r.country)} ({r.country}): {r.index:.0f}, {r.level}{prob}. {', '.join(category_label(c) for c in r.categories)}")
        if r.level != "niski" or r.impulse >= 6:
            from .skutki import forecast_lines
            L += [f"    {x}" for x in forecast_lines(r)[1:]]
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
        from . import pierwotne, ryby
        try:
            insiders, congress = pierwotne.insider_panel(con), ryby.congress_panel(con)
        except Exception as e:
            print(f"  [panele] {e}")
            insiders, congress = [], []
        try:
            from .rozjazd import cached
            div = cached(os.path.join(base, "rozjazd.json"), insiders)
            for r in insiders:
                r["rozjazd"] = next((d for d in div if d["ticker"] == r["ticker"]), None)
        except Exception as e:
            print(f"  [rozjazd] {e}")
        con.close()
    signals = extract_signals(arts, watchlist)
    results = assess(signals, today=date.today())
    with open(out, "w", encoding="utf-8") as f:
        f.write(report.to_html(results, len(arts), len(signals), "Analizator ruchów firm (tryb ciągły)",
                                insiders=insiders, congress=congress, trafnosc=_load_json(os.path.join(base, "trafnosc.json"))))
    alerts, new_state = changes(results, state, date.today())
    from .trafnosc import log_alarm
    for r, reasons in LAST_ALARMS:
        try:
            log_alarm(os.path.join(base, "alarmy.jsonl"), r, reasons)
        except Exception as e:
            print(f"  [trafność] nie zapisano alarmu: {e}")
    for a in alerts:
        notify("Analizator: " + a.split(":")[0], a, topic, os.path.join(base, "alerty.log"))
    if alerts_out:  # alarmy tylko z tego cyklu (np. dla GitHub Actions, które zakłada z nich zgłoszenie)
        with open(alerts_out, "w", encoding="utf-8") as f:
            f.write("\n\n".join(alerts))
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False)
    with open(os.path.join(base, "podsumowanie.txt"), "w", encoding="utf-8") as f:
        f.write(summary(results, len(arts)))
    # materiał dla nocnego przeglądu AI (te same dane i źródła co czuwanie)
    report.to_candidates_json(results, os.path.join(base, "kandydaci.json"))
    from . import pierwotne as _p
    with open(os.path.join(base, "zrodla.json"), "w", encoding="utf-8") as f:
        json.dump({"czas": datetime.now().isoformat(timespec="minutes"), "artykuly": len(arts),
                   "zrodla": {**STATUS, **{f"pierwotne/{k}": v for k, v in _p.STATUS.items()}}}, f, ensure_ascii=False, indent=1)
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
