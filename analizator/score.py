"""Łączenie sygnałów w ocenę dla kraju: anomalia względem tła + szerokość + korelacje.

Logika w skrócie:
1. Każdy artykuł -> 0..n sygnałów (kategoria, kraj, firma, waga).
2. Sygnały łączymy po (firma, kategoria, kraj, tydzień), żeby 30 artykułów o jednej
   decyzji jednej firmy nie liczyło się jak 30 niezależnych ruchów.
3. Dla każdego kraju i tygodnia liczymy wynik = suma wag unikalnych ruchów.
4. Porównujemy ostatnie tygodnie z tłem (mediana i rozrzut z poprzednich tygodni).
   Liczy się nietypowość, nie sama liczba: o Rosji pisze się zawsze dużo.
5. Premia za szerokość: wiele RÓŻNYCH firm i RÓŻNYCH typów ruchów w tym samym
   czasie (np. ewakuacja + ubezpieczyciele + łańcuch dostaw) jest dużo
   mocniejszym sygnałem niż jedna firma, o której piszą wszyscy.
6. Indeks 0-100 to skala uwagi, NIE skalibrowane prawdopodobieństwo.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .oficjalne import ALL_SOURCES as ALL_OFFICIAL, STRUCTURED, country_of
from .rzetelnosc import AUTHORITATIVE, assess_article, is_credible
from .signals import CATEGORIES, COUNTRIES, classify


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass
class CountryAssessment:
    country: str
    index: float                 # 0-100, skala uwagi
    level: str                   # niski / podwyższony / wysoki
    confidence: str              # mała / średnia / duża (ile mamy danych)
    recent_score: float
    baseline: float
    zscore: float
    companies: int
    states: int
    quiet: int
    proactive_share: float
    categories: list[str]
    weekly: list[tuple[str, float]]
    evidence: list[dict] = field(default_factory=list)
    priority: int = 0              # liczba sygnałów priorytetowych (ewakuacje, ostrzeżenia, lotnictwo)
    own_index: float = 0.0         # indeks bez przeniesienia z sąsiadów
    spill_from: str | None = None  # kraje, z których przeniesiono ryzyko
    co_occurring: list[tuple[str, str, int]] = field(default_factory=list)
    parts: dict = field(default_factory=dict)  # składowe indeksu (do wyjaśnień i diagnostyki)
    unconfirmed: bool = False      # indeks obcięty poniżej alarmu: brak potwierdzenia w rzetelnych źródłach
    confirmations: int = 0         # liczba niezależnych rzetelnych źródeł + sygnałów pierwotnych
    model_note: str = ""           # zmiana alarmu przez regułę łączoną (model + ręczny indeks)
    impulse: float = 0.0           # nagły przyrost nowych sygnałów w ostatnich 48 h względem zwykłego tła kraju (z-score)
    impulse_info: dict = field(default_factory=dict)  # teraz / norma / nowe kategorie / świeże dowody
    prob: float | None = None      # szansa wydarzenia w horyzoncie wg modelu uczonego na historii (analizator/model.json)


# Wiarygodność źródeł: oficjalne raporty > agencje i prasa branżowa > reszta.
# Prasa branżowa (żegluga, ubezpieczenia, energia) to często pierwsze miejsce, gdzie widać "ciche" ruchy.
SOURCE_TIERS: dict[str, float] = {
    # oficjalne i źródła pierwotne
    "sec.gov": 1.3, "travel.state.gov": 1.3, "gov.uk": 1.3, "easa.europa.eu": 1.3, "faa.gov": 1.3, "ofac.treasury.gov": 1.2,
    "ted.europa.eu": 1.1, "consilium.europa.eu": 1.3, "press.un.org": 1.25, "iaea.org": 1.3, "webgate.ec.europa.eu": 1.3,
    "sanctionslist.fcdo.gov.uk": 1.3, "ioda.inetintel.cc.gatech.edu": 1.2, "portwatch.imf.org": 1.3, "finance.yahoo.com": 1.2, "acleddata.com": 1.25, "agsi.gie.eu": 1.25, "finra.org": 1.25, "nasdaq.com": 1.15, "dsca.mil": 1.3, "opensky-network.org": 1.2, "aisstream.io": 1.2, "stockwatch.pl": 1.1, "bankier.pl": 1.1,
    # agencje i duża prasa biznesowa
    "reuters.com": 1.15, "bloomberg.com": 1.15, "ft.com": 1.15, "wsj.com": 1.15, "nikkei.com": 1.1, "asia.nikkei.com": 1.1,
    "apnews.com": 1.05, "cnbc.com": 1.0, "economist.com": 1.05, "handelsblatt.com": 1.05, "lesechos.fr": 1.05,
    "interfax.com": 1.0, "interfax.com.ua": 1.0, "kyivindependent.com": 1.0, "themoscowtimes.com": 1.0,
    "pap.pl": 1.05, "bankier.pl": 1.0, "money.pl": 0.95, "businessinsider.com.pl": 0.95, "rp.pl": 1.0, "parkiet.com": 1.05,
    "pb.pl": 1.05, "wnp.pl": 1.0, "forsal.pl": 0.9,
    # prasa branżowa (wysoka wartość dla cichych sygnałów)
    "lloydslist.com": 1.25, "insuranceday.com": 1.2, "tradewindsnews.com": 1.2, "splash247.com": 1.15, "argusmedia.com": 1.2,
    "spglobal.com": 1.2, "upstreamonline.com": 1.15, "rigzone.com": 1.05, "offshore-energy.biz": 1.05, "hellenicshippingnews.com": 1.05,
    "freightwaves.com": 1.05, "theloadstar.com": 1.1, "insurancejournal.com": 1.1, "artemis.bm": 1.15, "beinsure.com": 1.0,
    "icis.com": 1.15, "fastmarkets.com": 1.15, "mining.com": 1.05, "energyintel.com": 1.2, "naturalgasintel.com": 1.1,
}
LOW_TRUST_HINTS = re.compile(r"blogspot|wordpress|medium\.com|substack|biggo|todaypress|newsbreak|msn\.com|yahoo\.com|tradingview", re.I)
_WORD = re.compile(r"[a-ząćęłńóśźż0-9]{4,}", re.I)


LEGACY_SEC = re.compile(r"\((?:8|6)-K filing\)\s*$")
# Zdania warunkowe w raportach SEC to opisy ryzyka („may result in…”), nie zdarzenia.
SEC_CONDITIONAL = re.compile(r"\b(?:may|might|could|would|if|should|potential\w*|possible|possibly|risks?|uncertaint\w*|"
                             r"no assurance|cannot assure|including but not limited|notwithstanding|shall not constitute|scope of)\b", re.I)


def source_weight(domain: str | None) -> float:
    d = (domain or "").lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
    if d in SOURCE_TIERS:
        return SOURCE_TIERS[d]
    for k, v in SOURCE_TIERS.items():
        if d.endswith("." + k):
            return v
    return 0.7 if LOW_TRUST_HINTS.search(d) else 0.9


def _tokens(title: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(title)}


def extract_signals(articles: list[dict], watchlist: list[str] | None = None) -> list[dict]:
    rows = []
    sec_seen: dict[str, list[set]] = defaultdict(list)
    for a in sorted(articles, key=lambda a: a.get("date") or ""):
        if not a.get("date") or not a.get("title"):
            continue
        # Stare wpisy SEC (przed v0.3) miały tytuł składany z frazy, bez sprawdzenia zdania: pomijamy je.
        if a.get("source") == "sec":
            if LEGACY_SEC.search(a["title"]):
                continue
            company, _, sentence = a["title"].partition(": ")
            if SEC_CONDITIONAL.search(sentence):
                continue
            # to samo zdanie tej samej spółki w kolejnym raporcie kwartalnym to nie nowe zdarzenie
            tok = _tokens(sentence)
            if any(len(tok & old) / max(len(tok | old), 1) >= 0.6 for old in sec_seen[company.lower()]):
                continue
            sec_seen[company.lower()].append(tok)
        official = a.get("source") in PRIMARY_SOURCES
        if a.get("source") in STRUCTURED:  # pomiar albo oficjalna lista: kraj i kategoria podane wprost, bez zgadywania z tytułu
            cat, w, actor = STRUCTURED[a["source"]]
            c = country_of(a)
            if c in COUNTRIES:
                rows.append({"emotion": 0.0, "source_class": None, "quality": 1.0, "quality_reasons": [],
                             "date": date.fromisoformat(a["date"][:10]), "country": c, "category": cat, "base_weight": w,
                             "company": a["source"], "actor": actor, "negated": False, "reactive": False, "title": a["title"],
                             "url": a.get("url"), "matched": a["source"], "source": a["source"], "domain": a.get("domain"),
                             "credibility": source_weight(a.get("domain"))})
            continue
        q = {"mult": 1.0, "emotion": 0.0, "class": None, "reasons": []} if official else assess_article(a["title"], a.get("domain"))
        if q["mult"] <= 0:
            continue  # raport rynkowy / reklama: pomijamy w całości
        for s in classify(a["title"], watchlist):
            if not s.country:
                continue
            rows.append({"emotion": q["emotion"], "source_class": q["class"], "quality": q["mult"], "quality_reasons": q["reasons"],
                "date": date.fromisoformat(a["date"][:10]), "country": s.country, "category": s.category,
                "base_weight": s.weight, "company": s.company, "actor": s.actor, "negated": s.negated, "reactive": s.reactive,
                "title": a["title"], "url": a.get("url"), "matched": s.matched, "source": a.get("source"),
                "domain": a.get("domain"), "credibility": source_weight(a.get("domain") or ("sec.gov" if a.get("source") == "sec" else None)),
            })
    _cluster_stories(rows)
    for r in rows:
        # cichy sygnał: wyprzedzający ruch, opisany przez 1-2 źródła, z wiarygodnego miejsca
        r["quiet"] = (r["coverage"] <= 2 and not r["reactive"] and not r["negated"] and r["actor"] != "nieznany"
                      and r["base_weight"] >= 2.0 and r["credibility"] >= 0.9 and r["quality"] >= 0.9)
        art = 1.0 if r.get("source") in PRIMARY_SOURCES else PARAMS.get("artykuly", 1.0)
        r["weight"] = round(r["base_weight"] * r["credibility"] * r["quality"] * (1.25 if r["quiet"] else 1.0) * art, 2)
    return rows


def _cluster_stories(rows: list[dict]) -> None:
    """Łączy nagłówki o tym samym wydarzeniu (ta sama firma albo podobne słowa, do 10 dni)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["country"], r["category"])].append(r)
    for (c, cat), items in groups.items():
        clusters: list[dict] = []
        active: list[dict] = []  # tylko historie z ostatnich 10 dni (przy wieloletniej historii pełna lista byłaby kwadratowa)
        for r in sorted(items, key=lambda r: r["date"]):
            tok = _tokens(r["title"])
            hit = None
            active = [cl for cl in active if (r["date"] - cl["last"]).days <= 10]
            for cl in active:
                same_company = r["company"] and cl["company"] and r["company"].split()[0].lower() == cl["company"].split()[0].lower()
                jac = len(tok & cl["tok"]) / max(len(tok | cl["tok"]), 1)
                # przedruki tej samej wiadomości w ciągu kilku dni mają różne tytuły, więc próg dla bliskich dat jest niższy
                close = (r["date"] - cl["last"]).days <= 3
                if same_company or jac >= 0.35 or (close and jac >= 0.2):
                    hit = cl
                    break
            if not hit:
                hit = {"id": f"{c}-{cat}-{len(clusters)}", "tok": set(tok), "company": r["company"], "last": r["date"], "rows": []}
                clusters.append(hit)
                active.append(hit)
            hit["rows"].append(r)
            hit["tok"] |= tok
            hit["last"] = r["date"]
            hit["company"] = hit["company"] or r["company"]
        for cl in clusters:
            domains = {x.get("domain") or x.get("url") for x in cl["rows"]}
            for x in cl["rows"]:
                x["story"] = cl["id"]
                x["key"] = (cl["company"].split()[0] if cl["company"] else cl["id"]).lower()
                x["coverage"] = len(domains)


# Źródła pierwotne, które same w sobie są sygnałem priorytetowym (pomiar ruchu, ostrzeżenia urzędów)
PRIORITY_SOURCES = {"ais", "opensky", "travel_us", "travel_uk", "easa", "faa"}
PRIMARY_SOURCES = PRIORITY_SOURCES | {"sec", "ofac", "espi", "ted", "insiders"} | ALL_OFFICIAL
PRIORITY_CATS = {"ewakuacja_personelu", "ostrzezenia_panstw", "lotnictwo_przestrzen"}

# Powiązania ryzyka: alarm w kraju źródłowym podnosi część indeksu krajów powiązanych
# (bazy USA i infrastruktura w zasięgu Iranu, flanka NATO wobec Rosji, zależność paliwowa Kuby od Wenezueli...).
LINKS: dict[str, list[str]] = {
    "IR": ["QA", "AE", "KW", "IQ", "SA", "OM", "IL", "LB", "YE"],
    "IL": ["LB", "IR", "SY", "PS"],
    "RU": ["UA", "PL", "LT", "LV", "EE", "FI", "DK", "SE", "NO", "RO", "MD", "BY", "GE"],
    "BY": ["PL", "LT", "LV", "UA"],
    "UA": ["PL", "RO", "MD"],
    "VE": ["CU", "GY"],
    "PK": ["IN", "AF"], "IN": ["PK"], "AF": ["PK"],
    "CN": ["TW", "JP", "PH", "KR"], "TW": ["JP", "PH"],
    "KP": ["KR", "JP"],
    "YE": ["SA", "EG"],
    "SD": ["EG"],
}

# Parametry indeksu. Strojone na 2025 r., sprawdzane na 2026 r. (README: test historyczny).
PARAMS: dict[str, float] = {
    "w_z": 0.6, "w_actors": 0.5, "w_priority": 2.0, "prio_offset": 0.0, "priority_cap": 3.0, "w_quiet": 0.25, "w_cats": 0.3,
    "bias": -3.0, "spill": 0.0, "spill_min": 40.0, "sec_cap": 3.0, "baseline_weeks": 26.0,
    "confirm": 1.0, "confirm_domains": 2.0,  # alarm wymaga potwierdzenia (źródło pierwotne albo 2 niezależne rzetelne media)
    "artykuly": 1.0,  # mnożnik wagi artykułów prasowych względem źródeł pierwotnych i pomiarów (sprawdzany w teście historycznym)
}


def _dom(e: dict) -> str:
    d = (e.get("domain") or "").lower().removeprefix("www.")
    if not d and e.get("url"):
        d = re.sub(r"^https?://(?:www\.)?", "", e["url"]).split("/")[0].lower()
    return d or (e.get("source") or "?")


def _robust(base: list[float], floor: float) -> tuple[float, float]:
    if len(base) >= 2:
        med = statistics.median(base)
        mad = statistics.median([abs(v - med) for v in base]) * 1.4826
        return med, max(mad, statistics.pstdev(base), floor)
    return (base[0] if base else 0.0), floor * 1.5


def _damp_sec(signals: list[dict], baseline_weeks: int, cap: float) -> list[dict]:
    """SEC liczy się tylko jako nadwyżka ponad normę kraju i z limitem wagi na tydzień.

    W raportach spółek kraje ryzykowne (Chiny, Rosja, Izrael) pojawiają się stale, więc sam poziom nic nie mówi.
    """
    sec = [x for x in signals if x.get("source") == "sec"]
    if not sec:
        return signals
    counts: dict[str, dict[date, set]] = defaultdict(lambda: defaultdict(set))
    for x in sec:
        counts[x["country"]][week_start(x["date"])].add(x["key"])
    factor: dict[tuple[str, date], float] = {}
    for c, weeks in counts.items():
        first = min(weeks)
        for wk, keys in weeks.items():
            n = len(keys)
            hist = [len(weeks.get(wk - timedelta(weeks=i), ())) for i in range(1, baseline_weeks + 1) if wk - timedelta(weeks=i) >= first]
            mean = sum(hist) / len(hist) if hist else 0.0
            sd = statistics.pstdev(hist) if len(hist) >= 2 else 1.0
            excess = n - mean - sd
            f = max(0.0, min(1.0, excess / n)) if len(hist) >= 4 else 0.0
            # limit łącznej wagi SEC dla kraju w tygodniu
            total = sum(x["weight"] for x in sec if x["country"] == c and week_start(x["date"]) == wk) or 1.0
            factor[(c, wk)] = f * min(1.0, cap / (total * f)) if f > 0 else 0.0
    out = []
    for x in signals:
        if x.get("source") == "sec":
            x = {**x, "weight": round(x["weight"] * factor.get((x["country"], week_start(x["date"])), 0.0), 3)}
        out.append(x)
    return out


IMPULSE_DAYS, IMPULSE_BASE_DAYS = 2, 28


def _impulse(stories: dict, today: date) -> tuple[float, dict]:
    """Ile nowych historii pojawiło się w ostatnich 48 h w porównaniu ze zwykłym tłem kraju z poprzednich 4 tygodni.

    Liczy wagi (źródła pierwotne ważą więcej), nie same artykuły. Kryzys, który trwa od tygodni, ma wysokie tło,
    więc daje mały impuls; nagły skok w spokojnym kraju daje duży."""
    cut = today - timedelta(days=IMPULSE_DAYS)
    now = [v for v in stories.values() if v[0] > cut]
    base = [v for v in stories.values() if v[0] <= cut]
    w_now = sum(min(v[1], 3.0) for v in now)
    w_base = sum(min(v[1], 3.0) for v in base) * IMPULSE_DAYS / IMPULSE_BASE_DAYS
    new_cats = sorted({v[2] for v in now} - {v[2] for v in base})
    z = (w_now - w_base) / math.sqrt(w_base + 1.0) + 0.5 * len(new_cats) * (1 if now else 0)
    fresh = [v[3] for v in sorted(now, key=lambda v: (-v[1], v[0]))]
    return round(z, 2), {"teraz": round(w_now, 1), "norma": round(w_base, 1), "nowe_kategorie": new_cats,
                         "historii": len(now), "dowody": fresh[:4]}


def assess(signals: list[dict], today: date | None = None, recent_weeks: int = 2,
           min_baseline_weeks: int = 8, params: dict | None = None, use_model: bool = True) -> list[CountryAssessment]:
    P = {**PARAMS, **(params or {})}
    bw = int(P["baseline_weeks"])
    today = today or max((s["date"] for s in signals), default=date.today())
    cur_week = week_start(today)
    first_recent = cur_week - timedelta(weeks=recent_weeks - 1)
    signals = _damp_sec(signals, bw, P["sec_cap"])

    # (kraj, tydzień, aktor, kategoria) -> najwyższa waga
    moves: dict[tuple, float] = {}
    by_country_ev: dict[str, list[dict]] = defaultdict(list)
    prio_hist: dict[str, dict[date, set]] = defaultdict(lambda: defaultdict(set))
    quiet_hist: dict[str, dict[date, set]] = defaultdict(lambda: defaultdict(set))
    cat_hist: dict[str, dict[date, set]] = defaultdict(lambda: defaultdict(set))
    # Impuls: dzienne, unikalne historie z ostatnich 30 dni (bez reakcji na zdarzenia i zaprzeczeń)
    imp_from = today - timedelta(days=IMPULSE_BASE_DAYS + IMPULSE_DAYS)
    daily: dict[str, dict[str, tuple]] = defaultdict(dict)
    for s in signals:
        if s["weight"] <= 0.05:
            continue
        if imp_from < s["date"] <= today and not s["reactive"] and not s["negated"]:
            st = s.get("story") or s.get("url") or s["title"]
            old = daily[s["country"]].get(st)
            if old is None or s["date"] < old[0]:  # historia liczy się od dnia, w którym pojawiła się pierwszy raz
                daily[s["country"]][st] = (s["date"], s["weight"], s["category"], s)
        wk = week_start(s["date"])
        key = (s["country"], wk, s["key"], s["category"])
        moves[key] = max(moves.get(key, 0.0), s["weight"])
        if s["date"] >= first_recent:
            by_country_ev[s["country"]].append(s)
        if ((s["category"] in PRIORITY_CATS or s.get("source") in PRIORITY_SOURCES)
                and not s["reactive"] and not s["negated"] and s["actor"] != "nieznany" and s["weight"] >= 1.5):
            prio_hist[s["country"]][wk].add(s["key"])
        if s["quiet"]:
            quiet_hist[s["country"]][wk].add(s["story"])
        cat_hist[s["country"]][wk].add(s["category"])

    weekly: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    actors: dict[str, dict[date, set]] = defaultdict(lambda: defaultdict(set))
    for (c, wk, comp, _cat), w in moves.items():
        weekly[c][wk] += w
        if w >= 0.8:
            actors[c][wk].add(comp)

    own: dict[str, CountryAssessment] = {}
    for c, series in weekly.items():
        all_weeks = sorted(series)
        span = [all_weeks[0] + timedelta(weeks=i) for i in range((cur_week - all_weeks[0]).days // 7 + 1)]
        values = {wk: series.get(wk, 0.0) for wk in span}
        recent_wks = [wk for wk in span if wk >= first_recent]
        base_wks = [wk for wk in span if wk < first_recent][-bw:]
        recent_score = max((values[wk] for wk in recent_wks), default=0.0)
        med, spread = _robust([values[wk] for wk in base_wks], 1.5)
        z = (recent_score - med) / spread
        n_act = max((len(actors[c].get(wk, ())) for wk in recent_wks), default=0)
        a_med, a_spread = _robust([float(len(actors[c].get(wk, ()))) for wk in base_wks], 1.0)
        z_act = (n_act - a_med) / a_spread
        # Sygnały priorytetowe (ewakuacje, ostrzeżenia, lotnictwo) ponad normę tego kraju
        prio_now = len(set().union(*[prio_hist[c].get(wk, set()) for wk in recent_wks])) if recent_wks else 0
        prio_base = (sum(len(prio_hist[c].get(wk, ())) for wk in base_wks) / max(len(base_wks), 1)) * len(recent_wks)
        # Nadwyżka względem normy kraju w odchyleniach (jak w rozkładzie Poissona): 3 ewakuacje tam, gdzie zwykle jest 0,
        # znaczą dużo więcej niż 3 ponad 10 w kraju, o którym stale się pisze. Dzięki temu więcej danych nie podnosi indeksu samo z siebie.
        prio_excess = max(0.0, (prio_now - prio_base - P["prio_offset"]) / math.sqrt(prio_base + 1.0))
        def _excess(hist: dict[date, set]) -> float:
            now = len(set().union(*[hist.get(wk, set()) for wk in recent_wks])) if recent_wks else 0
            base = (sum(len(hist.get(wk, ())) for wk in base_wks) / max(len(base_wks), 1)) * len(recent_wks)
            return max(0.0, (now - base) / math.sqrt(base + 1.0))
        quiet_excess = _excess(quiet_hist[c])
        cats_now = len(set().union(*[cat_hist[c].get(wk, set()) for wk in recent_wks])) if recent_wks else 0
        n_rw = max(len(recent_wks), 1)
        cat_windows = [len(set().union(*[cat_hist[c].get(wk, set()) for wk in base_wks[i:i + n_rw]]))
                       for i in range(0, max(len(base_wks) - n_rw + 1, 0))]
        cats_base = statistics.median(cat_windows) if cat_windows else 0.0

        ev = by_country_ev.get(c, [])
        live = [e for e in ev if not e["negated"] and e["weight"] > 0.05]
        companies = {e["key"] for e in live if e["actor"] == "firma"}
        states = {e["key"] for e in live if e["actor"] == "panstwo"}
        quiet = [e for e in live if e["quiet"]]
        proactive = [e for e in live if not e["reactive"]]
        cats = sorted({e["category"] for e in live})
        proactive_share = len(proactive) / max(len(live), 1)
        per_comp: dict[str, float] = defaultdict(float)
        for (cc, wk, comp, _cat), w in moves.items():
            if cc == c and wk >= first_recent:
                per_comp[comp] += w
        total = sum(per_comp.values()) or 1.0
        dominance = max(per_comp.values(), default=0.0) / total

        anomaly = (P["w_z"] * min(max(z, 0), 5) * (1.2 - dominance) + P["w_actors"] * min(max(z_act, 0), 5)
                   + P["w_cats"] * max(cats_now - max(cats_base, 1.0), 0) * (1 if z > 0 else 0) + P["w_quiet"] * min(quiet_excess, 3))
        raw = anomaly * (0.5 + 0.5 * proactive_share) + P["w_priority"] * min(prio_excess, P["priority_cap"]) + P["bias"]
        index = round(100 / (1 + math.exp(-raw)), 1)
        # Potwierdzenie: alarm tylko wtedy, gdy ruch widać w źródle pierwotnym albo w co najmniej dwóch niezależnych,
        # rzeczowych źródłach (nie tabloid, nie propaganda, nie komunikat sponsorowany, nie straszący nagłówek).
        # Rzeczowy sygnał priorytetowy (ewakuacja, ostrzeżenie rządu, lotnictwo) z rzetelnego źródła, oparty na oficjalnym
        # ostrzeżeniu albo o wielu firmach naraz, liczy się jak źródło pierwotne: w teście historycznym takie sygnały dawały
        # prawdziwe wyprzedzenie (np. Wenezuela: „Six airlines suspend flights … amid FAA warning”, 40 dni).
        primary = [e for e in live if (e.get("source") in PRIORITY_SOURCES or e.get("source") in ("sec", "ofac", "espi")
                                       or (e["credibility"] >= 1.2 and is_credible(e))
                                       or (e["category"] in PRIORITY_CATS and is_credible(e) and e.get("emotion", 0) == 0
                                           and e["actor"] != "nieznany" and AUTHORITATIVE.search(e["title"])))
                   and not e["reactive"]]
        cred_domains = {_dom(e) for e in live if is_credible(e) and not e["reactive"]}
        confirmed = bool(primary) or len(cred_domains) >= int(P["confirm_domains"])
        unconfirmed = False
        if P["confirm"] and not confirmed and index >= 40:
            index, unconfirmed = 39.0, True
        n_base = len(base_wks)
        confidence = "duża" if n_base >= 26 and len(live) >= 10 else "średnia" if n_base >= min_baseline_weeks and len(live) >= 4 else "mała"

        pairs: dict[tuple[str, str], set] = defaultdict(set)
        for i, a in enumerate(cats):
            for b in cats[i + 1:]:
                pairs[(a, b)] = {e["key"] for e in live if e["category"] in (a, b)}
        co = sorted(((a, b, len(v)) for (a, b), v in pairs.items()), key=lambda t: -t[2])[:5]

        seen, evidence = set(), []
        for e in sorted(live, key=lambda e: (-(e["category"] in PRIORITY_CATS), -e["quiet"], -e["weight"], e["date"])):
            if e["story"] in seen:
                continue
            seen.add(e["story"])
            evidence.append(e)
        imp, imp_info = _impulse(daily.get(c, {}), today)
        own[c] = CountryAssessment(
            country=c, index=index, level="", confidence=confidence, recent_score=round(recent_score, 1),
            baseline=round(med, 1), zscore=round(z, 2), companies=len(companies), states=len(states),
            quiet=len({e["story"] for e in quiet}), proactive_share=round(proactive_share, 2), categories=cats,
            weekly=[(wk.isoformat(), round(values[wk], 1)) for wk in span[-26:]],
            evidence=evidence[:15], co_occurring=co, priority=prio_now, own_index=index, unconfirmed=unconfirmed,
            confirmations=len(cred_domains) + len(primary), impulse=imp, impulse_info=imp_info,
            parts={"z": round(z, 2), "z_act": round(z_act, 2), "cats": len(cats), "cats_base": cats_base, "quiet": len(quiet), "quiet_excess": round(quiet_excess, 2), "prio_now": prio_now,
                   "prio_base": round(prio_base, 2), "prio_excess": round(prio_excess, 2), "proactive": round(proactive_share, 2),
                   "dominance": round(dominance, 2), "anomaly": round(anomaly, 2), "raw": round(raw, 2)},
        )

    # Przenoszenie ryzyka na kraje powiązane
    for src, targets in LINKS.items():
        s_idx = own[src].own_index if src in own else 0.0
        if s_idx < P["spill_min"]:
            continue
        for t in targets:
            if t not in own:
                own[t] = CountryAssessment(country=t, index=0.0, level="", confidence="mała", recent_score=0.0, baseline=0.0,
                                           zscore=0.0, companies=0, states=0, quiet=0, proactive_share=0.0, categories=[],
                                           weekly=[], own_index=0.0)
            spill = s_idx * P["spill"]
            combined = round(100 - (100 - own[t].index) * (100 - spill) / 100, 1)
            if combined > own[t].index:
                own[t].index = combined
                own[t].spill_from = src if not own[t].spill_from else own[t].spill_from + "," + src
    for r in own.values():
        r.level = "wysoki" if r.index >= 70 else "podwyższony" if r.index >= 40 else "niski"
    if use_model:
        from .ucz import features, gate, load_model, predict
        m = load_model()
        if m:
            rule = m.get("laczenie") if (m.get("laczenie") or {}).get("aktywne") else None
            for r in own.values():
                r.prob = round(predict(m, features(r)), 3)
                if not rule:
                    continue
                alarm = gate(r.index, r.prob, rule)
                if r.index >= 40 and not alarm:
                    r.index, r.model_note = 39.0, "model nie potwierdza"
                elif r.index < 40 and alarm:
                    r.index, r.model_note = 40.0, "podniesione przez model"
                r.level = "wysoki" if r.index >= 70 else "podwyższony" if r.index >= 40 else "niski"
    return sorted(own.values(), key=lambda r: -r.index)


def country_name(code: str) -> str:
    return re.sub(r"\\[bB]|[()?\\]", "", COUNTRIES.get(code, [code])[0])


def category_label(key: str) -> str:
    return CATEGORIES.get(key, {}).get("label", key)
