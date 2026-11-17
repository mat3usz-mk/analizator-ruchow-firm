"""Trafność na żywo: dziennik alarmów i ich rozliczenie.

Każdy alarm czuwania trafia do dane/alarmy.jsonl razem z prognozą rynkową (sprawdzone kierunki indeksów, okres, typowa skala).
Raz dziennie `python -m analizator.trafnosc --dane dane` rozlicza alarmy:
  - rynek: czy indeks po zapowiedzianym okresie ruszył w zapowiedzianą stronę (notowania z Yahoo/stooq),
  - wydarzenie: czy w ciągu 60 dni w kraju nastąpiło wydarzenie z listy wydarzenia.csv (lista uzupełniana ręcznie),
oraz dokłada wynik z testu historycznego (alarmy reguły łączonej 2025–2026 z raporty/epizody.json).
Wynik: dane/trafnosc.json, czytany przez raport (zakładka „Trafność”).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta

HORIZON_EVENT = 60


def forecast_items(country: str, level: str) -> list[dict]:
    """Sprawdzone kierunki indeksów dla kraju w formie do rozliczenia."""
    from .rynki import key, results, verdict
    from .skutki import indices
    raw = indices(country, level if level != "niski" else "podwyższony", verified=False)
    res = results()
    out = []
    for direction, labels in (("down", raw["down"]), ("up", raw["up"])):
        for lab in labels:
            k = key(lab)
            st = res.get(f"{k}|{direction}")
            if verdict(st) != "sprawdza się":
                continue
            h = st.get("najlepszy_okres")
            o = (st.get("okresy") or {}).get(h) if h else None
            out.append({"nazwa": lab.split(" (")[0].split(":")[0].strip(), "klucz": k, "kierunek": direction,
                        "dni": int(h) if h else 37, "mediana": o["mediana"] if o else None})
            if len(out) >= 4:
                return out
    return out


def log_alarm(path: str, r, reasons: list[str], od_razu: bool | None = None) -> None:
    rec = {"czas": datetime.now().isoformat(timespec="minutes"), "data": date.today().isoformat(), "kraj": r.country,
           "indeks": round(r.index, 1), "poziom": r.level, "impuls": round(getattr(r, "impulse", 0.0), 1),
           "szansa": None if r.prob is None else round(r.prob, 3), "powody": reasons,
           "prognozy": forecast_items(r.country, r.level), "od_razu": od_razu,
           "slady": [f"{x['a']} → {x['b']}" for x in (getattr(r, "slady", None) or [])[:3]]}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _events(paths=("wydarzenia.csv",)) -> list[dict]:
    from .backtest import load_events
    return [e for p in paths if os.path.exists(p) for e in load_events(p)]


def _event_after(events, country: str, d: date, days: int = HORIZON_EVENT):
    hits = [e for e in events if e["kraj"] == country and d <= e["data"] <= d + timedelta(days=days)]
    return min(hits, key=lambda e: e["data"]) if hits else None


def settle(alarms: list[dict], today: date | None = None, prices=None) -> list[dict]:
    """Rozlicza alarmy. `prices(klucz, start)` zwraca koszyk z rynki.basket (do testów można podać własną funkcję)."""
    from .rynki import basket
    today = today or date.today()
    prices = prices or basket
    events = _events()
    cache: dict[str, object] = {}
    out = []
    for a in alarms:
        d = date.fromisoformat(a["data"])
        progs = []
        for p in a.get("prognozy", []):
            k = p["klucz"]
            if k not in cache:
                cache[k] = prices(k, d - timedelta(days=10))
            b = cache[k]
            end = min(today, d + timedelta(days=p["dni"]))
            rs = [sign * r for s, sign, _ in (b[0] if b else []) if (r := s.ret(d, (end - d).days)) is not None] if (end - d).days >= 1 else []
            ret = sum(rs) / len(rs) if rs else None
            done = today >= d + timedelta(days=p["dni"])
            status = "w toku" if not done else ("brak notowań" if ret is None else
                                               ("sprawdziło się" if (ret > 0) == (p["kierunek"] == "up") else "nie sprawdziło się"))
            progs.append({**p, "zmiana": None if ret is None else round(ret, 4), "status": status,
                          "rozliczenie": (d + timedelta(days=p["dni"])).isoformat()})
        ev = _event_after(events, a["kraj"], d)
        ev_status = (f"wydarzenie {ev['data']}: {ev.get('opis', '')}" if ev else
                     ("brak wydarzenia w 60 dni" if today >= d + timedelta(days=HORIZON_EVENT) else "w toku"))
        out.append({**a, "prognozy": progs, "wydarzenie": ev_status})
    return out


def history(path: str = "raporty/epizody.json", start: str = "2025-03-01") -> dict:
    """Alarmy z testu historycznego (reguła łączona) od `start` i co po nich nastąpiło."""
    try:
        eps = [e for e in json.load(open(path, encoding="utf-8"))["epizody"] if e["data"] >= start]
    except (OSError, ValueError, KeyError):
        return {}
    events = _events()
    rows = []
    for e in eps:
        d = date.fromisoformat(e["data"])
        if d + timedelta(days=HORIZON_EVENT) > date.today():
            continue  # jeszcze nie da się rozliczyć
        ev = _event_after(events, e["kraj"], d)
        rows.append({"kraj": e["kraj"], "data": e["data"], "wydarzenie": f"{ev['data']}: {ev.get('opis', '')}" if ev else None})
    n = len(rows)
    ok = sum(1 for r in rows if r["wydarzenie"])
    return {"od": start, "alarmow": n, "trafnych": ok, "precyzja": round(ok / n, 3) if n else None, "alarmy": rows[-40:]}


def summary(settled: list[dict]) -> dict:
    progs = [p for a in settled for p in a["prognozy"] if p["status"] in ("sprawdziło się", "nie sprawdziło się")]
    evs = [a for a in settled if a["wydarzenie"] != "w toku"]
    return {"alarmow": len(settled),
            "prognoz_rozliczonych": len(progs), "prognoz_trafnych": sum(p["status"] == "sprawdziło się" for p in progs),
            "alarmow_rozliczonych": len(evs), "z_wydarzeniem": sum(a["wydarzenie"].startswith("wydarzenie") for a in evs)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.trafnosc")
    ap.add_argument("--dane", default="dane")
    a = ap.parse_args(argv)
    path = os.path.join(a.dane, "alarmy.jsonl")
    alarms = [json.loads(x) for x in open(path, encoding="utf-8")] if os.path.exists(path) else []
    settled = settle(alarms)
    out = {"czas": datetime.now().isoformat(timespec="minutes"), "na_zywo": summary(settled), "alarmy": settled[-100:],
           "historia": history()}
    with open(os.path.join(a.dane, "trafnosc.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"trafność: {out['na_zywo']}; historia: {({k: v for k, v in out['historia'].items() if k != 'alarmy'})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
