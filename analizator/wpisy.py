"""Wpisy Donalda Trumpa a wydarzenia i rynki: czy wpisy wyprzedzają wydarzenia i czy rynek ruszał się już przed nimi.

Źródła: tweety z okresu prezydentury 2017–2021 (publiczne archiwum na GitHubie) i wpisy z Truth Social od 2022 r.
(archiwum trumpstruth.org; pobieranie za zgodą osoby z 16.11.2026, powoli, z przerwą między stronami).

    python -m analizator.wpisy --pobierz --out raporty/wpisy-wyniki.md
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import os
import re
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

TWEETS_URL = "https://raw.githubusercontent.com/MarkHershey/CompleteTrumpTweetsArchive/master/data/realDonaldTrump_in_office.csv"
TRUTH_URL = "https://trumpstruth.org/?sort=desc&per_page=100"
UA = "Mozilla/5.0 (analizator ruchow firm; test historyczny, kontakt w repozytorium)"
TRUTH_FROM = "2022-02-01"


def _get(url: str, tries: int = 4) -> str:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"  ponawiam ({e})", flush=True)
            time.sleep(10 * (i + 1))
    return ""


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_truth(page: str) -> list[tuple[str, str, str]]:
    """(id, czas UTC ISO, tekst wpisu + tytuł podlinkowanego artykułu)."""
    out = []
    for block in page.split('<div class="status" ')[1:]:
        m_id = re.search(r'statuses/(\d+)', block)
        m_t = re.search(r'<time datetime="([^"]+)"', block)
        if not (m_id and m_t):
            continue
        body = re.search(r'class="status__content"[^>]*>(.*?)</div>', block, re.S)
        card = re.search(r'class="status-card__title">(.*?)</div>', block, re.S)
        txt = " ".join(_text(x.group(1)) for x in (body, card) if x)
        out.append((m_id.group(1), m_t.group(1)[:19], txt))
    return out


def _cursor(ts: str) -> str:
    return base64.b64encode(json.dumps({"status_created_at": ts.replace("T", " "), "_pointsToNextItems": True},
                                       separators=(",", ":")).encode()).decode()


def fetch_truth(path: str, since: str = TRUTH_FROM, delay: float = 1.5) -> int:
    """Idzie od najnowszych wpisów wstecz (kursor = data najstarszego wpisu na stronie). Dopisuje do CSV, można wznawiać."""
    seen, oldest = set(), None
    if os.path.exists(path):
        for r in csv.reader(open(path, encoding="utf-8")):
            seen.add(r[0])
            oldest = min(oldest or r[1], r[1])
    f = open(path, "a", encoding="utf-8", newline="")
    w = csv.writer(f)
    url = TRUTH_URL + (f"&cursor={_cursor(oldest)}" if oldest else "")
    pages = 0
    while True:
        items = parse_truth(_get(url))
        new = [x for x in items if x[0] not in seen]
        for x in new:
            seen.add(x[0])
            w.writerow(x)
        pages += 1
        if not items:
            break
        low = min(x[1] for x in items)
        if pages % 20 == 0:
            f.flush()
            print(f"  strona {pages}: do {low}, wpisów {len(seen)}", flush=True)
        if low < since or (not new and oldest is not None and low >= oldest):
            break
        oldest = low
        url = TRUTH_URL + f"&cursor={_cursor(low)}"
        time.sleep(delay)
    f.close()
    return len(seen)


def load_posts(tweets_csv: str | None, truth_csv: str | None) -> list[tuple[datetime, str]]:
    posts = []
    if tweets_csv and os.path.exists(tweets_csv):
        for r in list(csv.reader(open(tweets_csv, encoding="utf-8")))[1:]:
            if len(r) >= 4:
                try:
                    posts.append((datetime.strptime(r[1].strip(), "%Y-%m-%d %H:%M"), r[3]))
                except ValueError:
                    pass
    if truth_csv and os.path.exists(truth_csv):
        for r in csv.reader(open(truth_csv, encoding="utf-8")):
            if len(r) >= 3:
                posts.append((datetime.fromisoformat(r[1]), r[2]))
    return sorted(posts)


# --- Test względem wydarzeń --------------------------------------------------------
def mention_impulse(posts, start: date, end: date) -> tuple[dict, dict]:
    from .score import _impulse
    from .signals import detect_countries
    by_c: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for t, txt in posts:
        for c in set(detect_countries(txt)):
            by_c[c][t.date()] += 1
    imp = {}
    for c, days in by_c.items():
        res, t = {}, start
        while t <= end:
            win = {f"{d}{k}": (d, 1.0, "wpis", None) for i in range(30) for d in [t - timedelta(days=i)] for k in range(days.get(d, 0))}
            if win:
                z, info = _impulse(win, t)
                if info["historii"]:
                    res[t] = (z, info["historii"])
            t += timedelta(days=1)
        imp[c] = res
    return imp, by_c


def before_after(by_c, events, start: date, end: date) -> dict:
    bef = aft = base = n = 0
    for e in events:
        if not (start + timedelta(days=60) <= e["data"] <= end - timedelta(days=8)):
            continue
        p = by_c.get(e["kraj"], {})
        n += 1
        bef += sum(p.get(e["data"] - timedelta(days=i), 0) for i in range(1, 8))
        aft += sum(p.get(e["data"] + timedelta(days=i), 0) for i in range(0, 7))
        base += sum(p.get(e["data"] - timedelta(days=i), 0) for i in range(30, 60)) * 7 / 30
    return {"wydarzen": n, "przed": bef, "po": aft, "norma": round(base, 1)}


# --- Test rynkowy: czy notowania ruszały się przed wpisem, czy po nim -------------------
MARKET_TOPICS = [  # (nazwa, wzorzec w treści, symbol, znak oczekiwanego ruchu)
    ("cła i handel (S&P 500)", r"\btariff", "^GSPC", -1),
    ("Chiny (Hang Seng)", r"\bChin(a|ese)\b", "^HSI", -1),
    ("Iran (ropa Brent)", r"\bIran", "BZ=F", 1),
    ("Rosja i Ukraina (DAX)", r"\b(Russia|Ukrain|Putin|Zelensk)", "^GDAXI", -1),
    ("ropa (Brent)", r"\b(oil|OPEC|drill)", "BZ=F", 0),
]


def market_test(posts, start: date, end: date, burst: int = 3) -> list[dict]:
    """Dni, w których temat pojawił się w co najmniej `burst` wpisach (a w poprzednich 7 dniach rzadko). Dla każdego takiego
    dnia: ruch notowań 5 dni przed wpisami i 5 dni po (od zamknięcia dnia przed wpisem). Wynik ze znakiem oczekiwanego
    kierunku; dla 0 – wartość bezwzględna."""
    from .rynki import Series, prices
    out = []
    for name, pat, sym, sign in MARKET_TOPICS:
        rx = re.compile(pat, re.I)
        days = defaultdict(int)
        for t, txt in posts:
            if start <= t.date() <= end and rx.search(txt):
                days[t.date()] += 1
        peaks = [d for d, n in sorted(days.items())
                 if n >= burst and sum(days.get(d - timedelta(days=i), 0) for i in range(1, 8)) < n]
        p = prices(sym, start - timedelta(days=30))
        if not p or not peaks:
            out.append({"temat": name, "symbol": sym, "dni": len(peaks), "przed": None, "po": None, "losowo": None})
            continue
        s = Series(p)
        f = (lambda x: abs(x)) if sign == 0 else (lambda x: sign * x)
        pre = [f(r) for d in peaks if (r := s.ret(d - timedelta(days=6), 5)) is not None]
        post = [f(r) for d in peaks if (r := s.ret(d - timedelta(days=1), 6)) is not None]
        rnd = [f(r) for t in s.d[::3] if start <= t <= end and (r := s.ret(t, 5)) is not None]
        avg = lambda xs: sum(xs) / len(xs) if xs else None
        out.append({"temat": name, "symbol": sym, "dni": len(peaks), "przed": avg(pre), "po": avg(post), "losowo": avg(rnd),
                    "przed_zgodne": sum(1 for x in pre if x > 0) / len(pre) if pre else None,
                    "po_zgodne": sum(1 for x in post if x > 0) / len(post) if post else None})
    return out


def _p(x):
    return "brak" if x is None else f"{x * 100:+.2f}%".replace(".", ",")


def write(path: str, ev_res: dict, ba: dict, mk: dict, meta: dict) -> None:
    L = [f"# Wpisy Donalda Trumpa: wydarzenia i rynki ({date.today().isoformat()})", "",
         f"Dane: {meta['tweety']} tweetów 2017–2021 i {meta['truth']} wpisów z Truth Social od 2022 r. "
         "Impuls wpisów o kraju liczony tak samo jak impuls w analizatorze (48 h względem 4 tygodni).", ""]
    for period, rows in ev_res.items():
        L += [f"## Wydarzenia: {period}", "", "| próg | epizodów | impuls ≤3 dni przed | ≤30 dni przed | precyzja (30 dni) | przewaga nad losowym |",
              "|---|---|---|---|---|---|"]
        for r in rows:
            n = r["wydarzen"] or 1
            h = r["trafienia"]
            prec = "brak" if r["precyzja"] is None else f"{r['precyzja']:.0%}"
            lift = "brak" if r["lift"] is None else f"{r['lift']:.1f}×"
            L.append(f"| {r['prog']} | {r['epizodow']} | {h[3]} z {r['wydarzen']} ({h[3] / n:.0%}) | "
                     f"{h[30]} z {r['wydarzen']} ({h[30] / n:.0%}) | {prec} | {lift} |")
        b = ba[period]
        L += ["", f"Wpisy o kraju wydarzenia: 7 dni przed {b['przed']}, 7 dni po (z dniem wydarzenia) {b['po']}, norma na 7 dni {b['norma']} "
              f"({b['wydarzen']} wydarzeń).", ""]
    for period, rows in mk.items():
        L += [f"## Rynki: {period}", "",
              "Dni, w których temat pojawił się w co najmniej 3 wpisach po spokojnym tygodniu. Ruch w kierunku oczekiwanym "
              "(spadek indeksu, wzrost ropy; przy samej ropie: wielkość ruchu bez znaku).", "",
              "| temat | dni | 5 dni przed wpisami | dzień wpisów + 5 dni | zwykły ruch w 5 dni | przed: zgodnie z kierunkiem | po: zgodnie |",
              "|---|---|---|---|---|---|---|"]
        for r in rows:
            pz = "brak" if r.get("przed_zgodne") is None else f"{r['przed_zgodne']:.0%}"
            po = "brak" if r.get("po_zgodne") is None else f"{r['po_zgodne']:.0%}"
            L.append(f"| {r['temat']} | {r['dni']} | {_p(r['przed'])} | {_p(r['po'])} | {_p(r['losowo'])} | {pz} | {po} |")
        L.append("")
    L += ["Jak czytać: jeśli ruch „przed” jest wyraźnie większy od zwykłego, a „po” nie, rynek wiedział wcześniej (wpis był reakcją). "
          "Jeśli większy jest ruch „po”, wpisy same poruszały rynkiem. Dane dzienne nie pokazują ruchów w ciągu dnia.",
          "Daty wydarzeń są przybliżone. To test na danych historycznych, nie rekomendacja inwestycyjna."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None) -> int:
    from .backtest import load_events
    from .impuls import evaluate
    ap = argparse.ArgumentParser(prog="analizator.wpisy")
    ap.add_argument("--pobierz", action="store_true")
    ap.add_argument("--tweety", default="trump_tweety.csv")
    ap.add_argument("--truth", default="trump_truth.csv")
    ap.add_argument("--out", default="raporty/wpisy-wyniki.md")
    a = ap.parse_args(argv)
    if a.pobierz:
        if not os.path.exists(a.tweety):
            open(a.tweety, "w", encoding="utf-8").write(_get(TWEETS_URL))
        print(f"Truth Social: {fetch_truth(a.truth)} wpisów", flush=True)
    tw = load_posts(a.tweety, None)
    tr = load_posts(None, a.truth)
    posts = sorted(tw + tr)
    d = date.fromisoformat
    periods = [("2017–2021 (tweety, lista 2015–2024)", "wydarzenia_2015_2024.csv", d("2017-03-01"), d("2021-01-08")),
               (f"2022–2024 (Truth Social, lista 2015–2024)", "wydarzenia_2015_2024.csv", d("2022-03-01"), d("2024-12-31")),
               (f"2025–{date.today():%Y} (Truth Social, lista 2025–2026)", "wydarzenia.csv", d("2025-03-01"), date.today())]
    ev_res, ba, mk = {}, {}, {}
    for label, csv_path, s, e in periods:
        imp, by_c = mention_impulse([p for p in posts if s - timedelta(days=40) <= p[0].date() <= e], s, e)
        evs = load_events(csv_path)
        ev_res[label] = [evaluate(imp, evs, s, e, thr) for thr in (2.5, 4.0, 6.0)]
        ba[label] = before_after(by_c, evs, s, e)
        mk[label] = market_test(posts, s, e)
        print(label, ba[label], [(r["prog"], r["epizodow"], r["prawdziwe"], r["lift"]) for r in ev_res[label]], flush=True)
        print("  rynki:", mk[label], flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write(a.out, ev_res, ba, mk, {"tweety": len(tw), "truth": len(tr)})
    print(open(a.out, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
