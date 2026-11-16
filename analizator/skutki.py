"""Możliwe skutki rynkowe i polityczne, gdy w danym kraju rośnie napięcie.

To baza wiedzy o TYPOWYCH reakcjach w podobnych sytuacjach z przeszłości
(Ukraina 2014/2022, Morze Czerwone 2023-24, Cieśnina Ormuz, napięcia wokół Tajwanu),
a nie model cenowy. Każdą hipotezę trzeba sprawdzić: rynek mógł już ją wycenić,
a skutki zależą od skali i od tego, czy w ogóle dojdzie do eskalacji.

NIE jest to rekomendacja inwestycyjna.
"""
from __future__ import annotations

# Role kraju w gospodarce świata -> co zwykle dzieje się przy eskalacji
ROLES: dict[str, dict] = {
    "eksporter_ropy_gazu": {
        "label": "duży eksporter ropy / gazu",
        "up": ["producenci ropy i gazu spoza regionu (Equinor, Shell, TotalEnergies, ExxonMobil)",
               "eksporterzy LNG z USA (Cheniere)", "armatorzy tankowców (Frontline, DHT)"],
        "down": ["energochłonny przemysł w Europie (chemia: BASF; nawozy: Yara, Grupa Azoty; stal)",
                 "linie lotnicze (Lufthansa, Ryanair, Wizz Air)", "firmy z aktywami w tym kraju"],
        "effects": ["sankcje lub embargo na surowce", "pułapy cenowe", "uwalnianie rezerw strategicznych",
                    "dopłaty i osłony cenowe dla odbiorców energii", "podatki od nadzwyczajnych zysków energetyki"],
    },
    "tranzyt_energii": {
        "label": "kraj tranzytowy dla energii",
        "up": ["operatorzy alternatywnych tras i terminali LNG", "magazyny gazu i handlowcy"],
        "down": ["odbiorcy zależni od tej trasy (np. Europa Środkowa)", "spółki gazowe zależne od tranzytu"],
        "effects": ["przerwy w tranzycie", "wzrost cen gazu w UE", "nadzwyczajne zakupy wspólne UE", "przyspieszenie dywersyfikacji"],
    },
    "waskie_gardlo_zeglugi": {
        "label": "wąskie gardło żeglugi",
        "up": ["armatorzy kontenerowi (Maersk, Hapag-Lloyd, ZIM) przez wyższe stawki", "armatorzy tankowców",
               "ubezpieczyciele morscy (wyższe składki)"],
        "down": ["detaliści i producenci zależni od importu z Azji", "europejskie firmy przemysłowe (dłuższe dostawy)"],
        "effects": ["omijanie trasy (dłuższe rejsy, np. wokół Afryki)", "składki za ryzyko wojenne", "eskorty marynarki wojennej",
                    "wzrost inflacji towarów"],
    },
    "polprzewodniki_technologia": {
        "label": "kluczowy producent półprzewodników / elektroniki",
        "up": ["producenci chipów poza regionem (Intel, Samsung, GlobalFoundries)", "zbrojeniówka i cyberbezpieczeństwo"],
        "down": ["firmy zależne od TSMC (Apple, Nvidia, AMD)", "producenci aut i elektroniki", "giełdy azjatyckie"],
        "effects": ["kontrole eksportu technologii", "subsydia dla fabryk chipów w USA/UE", "sankcje finansowe", "blokada morska lub lotnicza"],
    },
    "zboza_rolnictwo": {
        "label": "duży eksporter zbóż / nawozów",
        "up": ["producenci zbóż i nawozów spoza regionu (Nutrien, CF Industries, ADM, Bunge)"],
        "down": ["przetwórcy żywności", "importerzy żywności (Afryka Płn., Bliski Wschód)"],
        "effects": ["zakazy eksportu żywności", "wzrost cen żywności", "korytarze zbożowe", "dopłaty dla rolników", "spory o import w UE"],
    },
    "metale_surowce": {
        "label": "ważny dostawca metali / surowców krytycznych",
        "up": ["producenci metali spoza regionu (KGHM dla miedzi i srebra, Glencore, Anglo American)", "recykling metali"],
        "down": ["przemysł motoryzacyjny i bateryjny", "producenci elektroniki"],
        "effects": ["ograniczenia eksportu surowców krytycznych", "budowa zapasów strategicznych", "nowe umowy surowcowe UE/USA"],
    },
    "flanka_nato": {
        "label": "państwo frontowe / flanka NATO",
        "up": ["zbrojeniówka (Rheinmetall, BAE Systems, Saab, Kongsberg, Leonardo, Lockheed Martin)",
               "firmy budujące infrastrukturę obronną"],
        "down": ["lokalna giełda i waluta w pierwszej reakcji", "turystyka i nieruchomości w regionie"],
        "effects": ["wzrost wydatków na obronę", "fundusze UE na bezpieczeństwo", "przepisy nadzwyczajne", "ulgi dla przemysłu obronnego"],
    },
    "centrum_finansowe": {
        "label": "regionalne centrum finansowe / logistyczne",
        "up": ["konkurencyjne centra (Singapur, Londyn, Zurych)", "złoto i aktywa bezpieczne"],
        "down": ["banki z ekspozycją na region", "linie lotnicze i hub lotniczy"],
        "effects": ["odpływ kapitału", "kontrole kapitałowe", "przenosiny siedzib firm"],
    },
}

COUNTRY_ROLES: dict[str, list[str]] = {
    "RU": ["eksporter_ropy_gazu", "zboza_rolnictwo", "metale_surowce"],
    "UA": ["tranzyt_energii", "zboza_rolnictwo"],
    "BY": ["tranzyt_energii", "flanka_nato"],
    "SA": ["eksporter_ropy_gazu"], "IQ": ["eksporter_ropy_gazu"], "KW": ["eksporter_ropy_gazu"], "LY": ["eksporter_ropy_gazu"],
    "QA": ["eksporter_ropy_gazu"], "AE": ["eksporter_ropy_gazu", "centrum_finansowe"], "NG": ["eksporter_ropy_gazu"],
    "VE": ["eksporter_ropy_gazu"], "KZ": ["eksporter_ropy_gazu", "metale_surowce"], "AZ": ["eksporter_ropy_gazu", "tranzyt_energii"],
    "NO": ["eksporter_ropy_gazu"], "GY": ["eksporter_ropy_gazu"],
    "IR": ["eksporter_ropy_gazu", "waskie_gardlo_zeglugi"], "OM": ["waskie_gardlo_zeglugi"],
    "YE": ["waskie_gardlo_zeglugi"], "EG": ["waskie_gardlo_zeglugi"], "PA": ["waskie_gardlo_zeglugi"], "SO": ["waskie_gardlo_zeglugi"],
    "TR": ["tranzyt_energii", "waskie_gardlo_zeglugi"],
    "TW": ["polprzewodniki_technologia", "waskie_gardlo_zeglugi"], "KR": ["polprzewodniki_technologia"],
    "CN": ["polprzewodniki_technologia", "metale_surowce"], "JP": ["polprzewodniki_technologia"], "PH": ["waskie_gardlo_zeglugi"],
    "IL": ["polprzewodniki_technologia"], "LB": [], "SY": [], "PS": [],
    "CD": ["metale_surowce"], "ZA": ["metale_surowce"], "MZ": ["eksporter_ropy_gazu"], "AR": ["zboza_rolnictwo"], "BR": ["zboza_rolnictwo"],
    "PL": ["flanka_nato"], "LT": ["flanka_nato"], "LV": ["flanka_nato"], "EE": ["flanka_nato"], "FI": ["flanka_nato"],
    "RO": ["flanka_nato"], "SE": ["flanka_nato"], "MD": ["flanka_nato"], "GE": ["tranzyt_energii"], "DE": [],
}

# Dodatkowe wnioski z samego typu ruchów firm (niezależnie od kraju)
CATEGORY_HINTS: dict[str, str] = {
    "ewakuacja_personelu": "Firmy i państwa wycofują ludzi: zwykle wyprzedza to zawieszenie lotów i działalności.",
    "ostrzezenia_panstw": "Ostrzeżenia rządów: często poprzedzają zamknięcie przestrzeni powietrznej i ewakuacje obywateli.",
    "ubezpieczenia_finanse": "Ubezpieczyciele i banki ograniczają ryzyko: wyższe koszty transportu i finansowania w regionie.",
    "lancuch_dostaw": "Zmiany dostaw: możliwe niedobory i wzrost cen u odbiorców zależnych od tego kraju.",
    "energia_surowce": "Ruchy w energii: możliwy wzrost cen gazu/ropy, ważne dla Europy i Polski.",
    "wstrzymane_inwestycje": "Firmy wstrzymują inwestycje: spadek napływu kapitału, presja na lokalną walutę.",
    "przeplywy_finansowe": "Kapitał ucieka lub firmy przenoszą siedziby: ryzyko kontroli kapitałowych.",
    "wyjscie_z_rynku": "Wyjścia z rynku: odpisy u firm z ekspozycją, okazje dla lokalnych przejmujących.",
    "sprzedaz_aktywow": "Sprzedaż aktywów: firmy ograniczają ekspozycję, często z dyskontem.",
}


def implications(country: str, categories: list[str], exposed_companies: list[str], level: str = "podwyższony") -> dict:
    roles = [ROLES[r] for r in COUNTRY_ROLES.get(country, []) if r in ROLES]
    up, down, effects = [], [], []
    for r in roles:
        up += r["up"]
        down += r["down"]
        effects += r["effects"]
    if roles:
        # Każda eskalacja: zwykle zyskują zbrojeniówka i aktywa bezpieczne
        up += ["złoto i obligacje uznawane za bezpieczne"]
        if "flanka_nato" not in COUNTRY_ROLES.get(country, []):
            up += ["zbrojeniówka (Rheinmetall, BAE Systems, Lockheed Martin)"]
    idx = indices(country, level)
    return {
        "idx_up": idx["up"], "idx_down": idx["down"],
        "roles": [r["label"] for r in roles],
        "up": list(dict.fromkeys(up)),
        "down": list(dict.fromkeys(down)),
        "effects": list(dict.fromkeys(effects)),
        "hints": [CATEGORY_HINTS[c] for c in categories if c in CATEGORY_HINTS],
        "exposed": exposed_companies,
    }


# --- Konkretne indeksy i notowania -------------------------------------------
# Kierunek to TYPOWA pierwsza reakcja przy eskalacji (np. Krym 2014, Ukraina 2022, Ormuz/Morze Czerwone 2019-24,
# manewry wokół Tajwanu 2022-24). Siła i czas reakcji bywają różne, a rynek mógł już wycenić ryzyko.

# Główny indeks giełdy kraju (zwykle spada, gdy rośnie ryzyko w tym kraju)
LOCAL_INDEX: dict[str, str] = {
    "PL": "WIG20 (GPW)", "RU": "MOEX Russia (MOEX)", "UA": "PFTS (mała płynność)", "TW": "TAIEX (TWSE)", "IL": "TA-35 (TASE)",
    "TR": "BIST 100 (XU100)", "KR": "KOSPI", "JP": "Nikkei 225", "CN": "CSI 300 i Hang Seng (HSI)", "HK": "Hang Seng (HSI)",
    "SA": "Tadawul All Share (TASI)", "AE": "DFM General i FTSE ADX General", "QA": "QE Index (Katar)", "KW": "Boursa Kuwait Premier",
    "EG": "EGX 30", "IN": "Nifty 50 i Sensex", "PK": "KSE-100", "DE": "DAX", "FR": "CAC 40", "GB": "FTSE 100", "FI": "OMX Helsinki 25",
    "SE": "OMX Stockholm 30", "NO": "OBX (Oslo)", "EE": "OMX Tallinn", "LV": "OMX Riga", "LT": "OMX Vilnius", "RO": "BET (Bukareszt)",
    "HU": "BUX", "CZ": "PX (Praga)", "NG": "NGX All-Share", "ZA": "FTSE/JSE Top 40", "BR": "Ibovespa", "AR": "S&P Merval",
    "MX": "S&P/BMV IPC", "PH": "PSEi", "KZ": "KASE Index", "JO": "ASE General (Amman)", "MA": "MASI", "VN": "VN-Index",
    "TH": "SET Index", "ID": "Jakarta Composite (JCI)", "MY": "FTSE Bursa Malaysia KLCI", "SG": "Straits Times (STI)",
    "GE": "brak płynnego indeksu", "BY": "brak płynnego indeksu", "IR": "TEDPIX (Teheran, niedostępny z zagranicy)",
    "VE": "IBC (Caracas, mała płynność)", "LB": "BLOM Stock Index (mała płynność)",
}

# Indeksy sektorowe, surowcowe i globalne zależnie od roli kraju: (w górę, w dół)
ROLE_INDICES: dict[str, tuple[list[str], list[str]]] = {
    "eksporter_ropy_gazu": (["ropa Brent (ICE) i WTI (NYMEX)", "gaz TTF (ICE Endex)", "STOXX Europe 600 Oil & Gas (SXEP)",
                             "S&P 500 Energy (XLE)", "OBX Oslo (producent spoza regionu)"],
                            ["STOXX Europe 600 Travel & Leisure (SXTP)", "STOXX Europe 600 Chemicals (SX4P)", "DAX (energochłonny przemysł)"]),
    "tranzyt_energii": (["gaz TTF (ICE Endex)", "STOXX Europe 600 Utilities (SX6P), producenci gazu"],
                        ["STOXX Europe 600 Chemicals (SX4P)", "DAX", "WIG20 (zależność od gazu)"]),
    "waskie_gardlo_zeglugi": (["frachty kontenerowe (Drewry WCI, SCFI)", "ropa Brent (ICE) i WTI (NYMEX)", "Baltic Dirty Tanker Index"],
                              ["STOXX Europe 600 Retail (SXRP)", "STOXX Europe 600 Automobiles & Parts (SXAP)"]),
    "polprzewodniki_technologia": (["STOXX Europe Total Market Aerospace & Defense", "S&P Aerospace & Defense Select (XAR)"],
                                   ["PHLX Semiconductor (SOX)", "Nasdaq 100", "TAIEX", "KOSPI", "Nikkei 225"]),
    "zboza_rolnictwo": (["pszenica i kukurydza (CBOT)", "nawozy: Green Markets/Urea (NOLA)"],
                        ["STOXX Europe 600 Food & Beverage (SX3P)"]),
    "metale_surowce": (["miedź, aluminium, nikiel (LME)", "STOXX Europe 600 Basic Resources (SXPP)"],
                       ["STOXX Europe 600 Automobiles & Parts (SXAP)"]),
    "flanka_nato": (["STOXX Europe Total Market Aerospace & Defense", "Rheinmetall, Saab, Kongsberg (składniki indeksów obronnych)"],
                    ["WIG20 (GPW)", "mWIG40 (GPW)", "OMX Baltic Benchmark", "kurs PLN i walut regionu (EUR/PLN w górę)"]),
    "centrum_finansowe": (["złoto (XAU/USD)"], ["STOXX Europe 600 Banks (SX7P)"]),
}
SAFE_HAVENS = ["złoto (XAU/USD)", "indeks zmienności VIX", "obligacje USA i Niemiec (rentowność w dół)", "frank szwajcarski (CHF)"]


def indices(country: str, level: str = "podwyższony") -> dict:
    """Konkretne indeksy, które przy eskalacji w danym kraju typowo rosną (up) i spadają (down)."""
    up, down = [], []
    for r in COUNTRY_ROLES.get(country, []):
        u, d = ROLE_INDICES.get(r, ([], []))
        up += u
        down += d
    if country in LOCAL_INDEX:
        down.insert(0, f"{LOCAL_INDEX[country]}: lokalna giełda")
    if level in ("podwyższony", "wysoki") or COUNTRY_ROLES.get(country):
        up += SAFE_HAVENS[:2] if level != "wysoki" else SAFE_HAVENS
    if level == "wysoki":
        down += ["MSCI Emerging Markets (przy szerszej eskalacji)"]
    return {"up": _uniq(up), "down": _uniq(down)}


def _uniq(xs: list[str]) -> list[str]:
    seen, out = set(), []
    for x in xs:
        k = x.split(" (")[0].split(":")[0].strip().lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


# --- Fronty: jeden kryzys bywa rozbity na kilka krajów ---------------------------
# Tylko do prezentacji (indeksy krajów się nie zmieniają: przenoszenie ryzyka na sąsiadów psuło precyzję w teście).
FRONTS: dict[str, tuple[str, list[str]]] = {
    "zatoka": ("Zatoka Perska i Cieśnina Ormuz", ["IR", "IQ", "KW", "SA", "AE", "QA", "OM", "BH"]),
    "morze_czerwone": ("Morze Czerwone i Jemen", ["YE", "SA", "EG", "SO", "ER", "DJ", "SD"]),
    "lewant": ("Izrael i Lewant", ["IL", "LB", "SY", "PS", "JO", "IR"]),
    "flanka": ("Wschodnia flanka NATO, Rosja, Ukraina", ["PL", "LT", "LV", "EE", "FI", "BY", "RU", "UA", "MD", "RO", "SE", "NO"]),
    "tajwan": ("Tajwan i Morze Południowochińskie", ["TW", "CN", "PH", "JP", "KR", "VN"]),
    "kaukaz": ("Kaukaz", ["GE", "AM", "AZ", "TR"]),
    "azja_pld": ("Indie i Pakistan", ["IN", "PK", "AF"]),
    "sahel": ("Sahel i Afryka Zachodnia", ["ML", "NE", "BF", "NG", "TD"]),
    "wenezuela": ("Wenezuela i Karaiby", ["VE", "GY", "CO", "CU"]),
}

# Indeksy wspólne dla frontu (dokładane do indeksów krajów)
FRONT_INDICES: dict[str, tuple[list[str], list[str]]] = {
    "zatoka": (["ropa Brent (ICE) i WTI (NYMEX)", "gaz TTF (ICE Endex)", "Baltic Dirty Tanker Index"], ["STOXX Europe 600 Travel & Leisure (SXTP)", "Nikkei 225 i KOSPI (importerzy ropy)"]),
    "morze_czerwone": (["frachty kontenerowe (Drewry WCI, SCFI)"], ["STOXX Europe 600 Retail (SXRP)"]),
    "lewant": (["ropa Brent (ICE) i WTI (NYMEX)", "złoto (XAU/USD)"], ["TA-35 (TASE)"]),
    "flanka": (["STOXX Europe Total Market Aerospace & Defense", "gaz TTF (ICE Endex)", "pszenica (CBOT, Euronext)"], ["WIG20 (GPW)", "DAX", "kurs PLN (EUR/PLN w górę)"]),
    "tajwan": (["STOXX Europe Total Market Aerospace & Defense"], ["TAIEX (TWSE)", "PHLX Semiconductor (SOX)", "Nasdaq 100", "Hang Seng (HSI)"]),
    "azja_pld": (["złoto (XAU/USD)"], ["Nifty 50 i Sensex", "KSE-100"]),
    "wenezuela": (["ropa ciężka i rafinerie USA (S&P 500 Energy, XLE)"], []),
}


def fronts(results, min_index: float = 25.0) -> list[dict]:
    """Fronty, w których co najmniej dwa kraje mają podwyższone wskazania albo sygnały priorytetowe."""
    by = {r.country: r for r in results}
    out = []
    for key, (label, members) in FRONTS.items():
        act = [by[c] for c in members if c in by and (by[c].index >= min_index or getattr(by[c], "priority", 0))]
        if len(act) < 2:
            continue
        act.sort(key=lambda r: -r.index)
        up, down = FRONT_INDICES.get(key, ([], []))
        out.append({"klucz": key, "nazwa": label, "kraje": [(r.country, round(r.index)) for r in act],
                    "max": max(r.index for r in act), "suma": round(sum(r.index for r in act)),
                    "kategorie": sorted({c for r in act for c in r.categories}),
                    "idx_up": up, "idx_down": down})
    return sorted(out, key=lambda f: -f["suma"])
