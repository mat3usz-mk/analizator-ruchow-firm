"""Rozpoznawanie sygnałów w nagłówkach: kategoria ruchu, kraj docelowy, firma, typ aktora.

Celowo regułowe i przejrzyste: każdy sygnał da się wytłumaczyć wzorcem,
który go złapał. Codzienny przegląd AI (patrz README) filtruje resztę.

Najważniejsze rozróżnienie: ruch WYPRZEDZAJĄCY (firma sama ewakuuje ludzi,
wstrzymuje inwestycję, choć nic się jeszcze nie stało) jest dużo cenniejszy
niż ruch REAKTYWNY ("po ataku dronów lotnisko wstrzymało pracę"). Te drugie
opisują to, co już się dzieje, więc dostają niską wagę.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- Kategorie ruchów ---------------------------------------------------------
# waga = jak mocno dany typ ruchu sugeruje, że aktor spodziewa się kłopotów
# w danym kraju. Wagi są początkowe i do strojenia na danych historycznych.
CATEGORIES: dict[str, dict] = {
    "ewakuacja_personelu": {
        "label": "Ewakuacja / relokacja personelu",
        "weight": 4.0,
        "patterns": [
            r"\bevacuat\w* (?:\w+ ){0,3}(?:staff|employees|personnel|workers|diplomats|citizens|nationals|expats|families|embassy|consulate)",
            r"\b(?:staff|employees|personnel|workers|diplomats|citizens|nationals|expats|embassy|consulate)\w* (?:\w+ ){0,3}evacuat\w*",
            r"\brelocat\w* (?:its |some |all )?(?:staff|employees|personnel|workers|families|expats)",
            r"non-(?:essential|emergency) (?:staff|personnel|employees|diplomats|government)", r"\border\w* (?:the )?departure of\b", r"\bpulls? (?:out )?(?:staff|employees|expats)",
            r"\b(?:staff|employees|families) to leave\b", r"\bordered to leave\b",
            r"\bewaku\w* (?:\w+ ){0,2}(?:pracownik|personel|dyplomat|obywatel|ambasad|rodzin)\w*", r"\brelokuj\w*|\brelokacj\w*", r"wycofuje (?:pracownik|personel|dyplomat)\w*",
        ],
    },
    "ostrzezenia_panstw": {
        "label": "Ostrzeżenia państw (ambasady, podróże, granice, flota)",
        "weight": 3.5,
        "patterns": [
            r"\btravel (?:advisory|warning)", r"\bdo not travel\b", r"\bordered departure\b", r"\bauthori[sz]ed departure\b",
            r"\bembassy (?:evacuat\w*|staff)", r"\bcarrier strike group\b", r"\baircraft carrier (?:to|heads|moves|deploy\w*)",
            r"\b(?:closes?|shuts?|seals?) (?:\w+ )?border(?: crossings?)?\b", r"\bborder crossings? (?:closed|shut)",
            r"\bzamyka (?:\w+ )?granic\w*|\bzamknięci\w* (?:\w+ )?przejś\w* granicz\w*", r"\blotniskowiec\w*", r"\bleave (?:the country )?immediately\b",
            r"\bembassy (?:closes|suspends|shuts|reduces)", 
            r"\bopuści\w* (?:kraj|terytorium)", r"\bambasad\w* (?:zawiesz|zamyk|ogranicz)\w*", r"\bostrzeżeni\w* (?:dla podróżnych|przed podróż)",
        ],
    },
    "lotnictwo_przestrzen": {
        "label": "Lotnictwo: zawieszone loty, omijanie przestrzeni, ostrzeżenia FAA/EASA",
        "weight": 4.0,
        "patterns": [
            r"\b(?:suspend|halt|cancel|stop|pause)\w* (?:all |its |some )?(?:flights|services|routes)\b",
            r"\b(?:avoid|avoids|avoiding|reroute\w*|divert\w*)\s+(?:\w+\s+){0,2}airspace", r"\bairspace (?:closed|closure|shut|restrictions?)",
            r"\b(?:closes?|shuts?) (?:its )?airspace", r"\bFAA (?:warning|warns|advisory|notice|bans?|prohibits)", r"\bEASA\b",
            r"\b(?:suspend|halt|stop|pause|avoid|cancel)\w*[^.]{0,40}\bairspace\b", r"\bconflict zone (?:information )?bulletin", r"\bNOTAM\b", r"\bno-fly zone",
            r"\bzawiesz\w* (?:\w+ )?(?:loty|połączenia)", r"\bomija\w* (?:\w+ )?przestrze\w* powietrzn\w*", r"\bzamkni\w* przestrze\w* powietrzn\w*",
        ],
    },
    "sankcje": {
        "label": "Sankcje i embarga",
        "weight": 2.5,
        "patterns": [
            r"\bsanctions? (?:action|designations?|package|on|against)\b", r"\b[A-Z][a-z]+-related designations\b", r"\bembargo\b",
            r"\bexport (?:ban|controls?)\b", r"\bpakiet\w* sankcj\w*", r"\bsankcj\w* (?:na|wobec)\b", r"\bembarg\w*",
        ],
    },
    "wyjscie_z_rynku": {
        "label": "Wyjście z rynku / zawieszenie działalności",
        "weight": 3.0,
        "patterns": [
            r"\bexit\w* (?:the |from )?(?:market|country|operations|business)", r"\bwithdraw\w* from (?:the |its |a )?(?:market|project|deal|contract|joint venture|JV|tender|licen[cs]e|field|block|venture|investment)",
            r"\bpull\w* out of (?:the |its |a )?(?:market|project|deal|contract|joint venture|JV|tender|venture|investment)", r"\bsuspend\w* (?:all |its )?(?:operations|production|business|flights|sales|activities)",
            r"\bhalt\w* (?:all |its )?(?:operations|production|flights)", r"\bshut\w* down (?:its )?(?:plant|factory|office|operations)",
            r"\bclos\w* (?:its )?(?:office|offices|plant|factory|branch|branches|stores)\b", r"\bwind\w* down\b",
            r"\bwycof\w* (?:się )?z (?:rynk\w*|kraju|projekt\w*|inwestycj\w*|umowy|kontrakt\w*|przetargu)", r"\bzawiesz\w* (?:działalność|produkcję|loty|sprzedaż)", r"\bopuszcza rynek",
            r"\bzamyka (?:biuro|fabrykę|zakład|oddział)", r"\bzawieszeni\w* (?:\w+ )?(?:działalności|produkcji|sprzedaży|lotów|operacji)",
            r"\bwycofani\w* (?:się )?z (?:rynk\w*|kraju|Ukrain\w*|Rosj\w*|Białorus\w*)", r"\bzamknięci\w* (?:biura|fabryki|zakładu|oddziału)",
        ],
    },
    "wstrzymane_inwestycje": {
        "label": "Wstrzymane / odłożone inwestycje",
        "weight": 2.5,
        "patterns": [
            r"\b(?:puts?|placed?) (?:\w+ ){0,3}(?:investment|project|expansion|plans?) on hold", r"\bfreez\w* (?:\w+ ){0,3}investments?",
            r"\bshelv\w* (?:\w+ ){0,3}(?:plans?|project|investment)", r"\bpostpon\w* (?:\w+ ){0,3}(?:investment|project|expansion|plant)",
            r"\bpaus\w* (?:\w+ ){0,3}(?:investment|expansion|construction)", r"\bscraps? (?:\w+ ){0,3}(?:plans?|project|investment)",
            r"\bwstrzym\w* (?:\w+ ){0,3}inwestycj\w*", r"\bzamraża (?:\w+ ){0,3}inwestycj\w*", r"\bodkład\w* (?:\w+ ){0,3}(?:inwestycj|budow)\w*",
        ],
    },
    "sprzedaz_aktywow": {
        "label": "Sprzedaż aktywów / odpisy",
        "weight": 2.0,
        "patterns": [
            r"\bsell\w* (?:its |a |the )?(?:stake|assets?|unit|subsidiary|business|operations)", r"\bdivest\w*",
            r"\basset sale", r"\bwrite-?downs?\b|\bwrites? down\b", r"\bimpairment",
            r"sprzeda\w* (?:udziały|aktywa|spółkę|oddział)", r"\bsprzedaż\w* (?:udziałów|aktywów|spółki|zorganizowanej)", r"\bodpis\w*",
        ],
    },
    "przeplywy_finansowe": {
        "label": "Przepływy finansowe (repatriacja kapitału, przeniesienie siedziby)",
        "weight": 3.0,
        "patterns": [
            r"\brepatriat\w* (?:\w+ ){0,2}(?:capital|profits?|funds|cash|earnings|dividends|assets|money)", r"\bcorrespondent bank\w*", r"\bcapital controls?", r"\bmov\w* (?:its )?(?:headquarters|HQ|domicile)",
            r"\bredomicil\w*", r"\bcap\w* (?:withdrawals|transfers)", r"\bhalts? (?:payments|transfers|transactions)",
            r"\bprzenos\w* siedzib\w*", r"\bwstrzym\w* (?:przelewy|płatności|transakcje)",
        ],
    },
    "ubezpieczenia_finanse": {
        "label": "Ubezpieczenia / ograniczanie ekspozycji",
        "weight": 3.0,
        "patterns": [
            r"\bwar[- ]risk (?:cover|premium|premiums|rates?|insurance|policies)", r"\binsurers? (?:cancel|withdraw|pull|drop|refuse|hike|raise)\w*",
            r"\b(?:cancel|withdraw)\w* (?:insurance|cover(?:age)?)", r"\breduc\w* (?:its )?exposure", r"\bcut\w* (?:credit|lending) lines?",
            r"\bstops? lending", r"\bhik\w* (?:\w+ )?premiums", r"ogranicz\w* ekspozycj\w*", r"ubezpieczyciel\w* (?:wycof|rezygn|podnos)\w*",
        ],
    },
    "lancuch_dostaw": {
        "label": "Zmiany w łańcuchu dostaw i zapasach",
        "weight": 2.0,
        "patterns": [
            r"\breroute\w* (?:ships|vessels|cargo|shipments|tankers|flights|supplies)", r"\bforce majeure",
            r"\b(?:halt|suspend|stop)\w* (?:shipments|deliveries|exports|imports|supplies)", r"\bstockpil\w*",
            r"\bbuild\w* (?:up )?(?:inventor\w*|stocks)", r"\bshift\w* (?:production|sourcing|supply)",
            r"\b(?:new|alternative|second) suppliers?", r"\bdual[- ]sourc\w*",
            r"łańcuch\w* dostaw", r"wstrzym\w* (?:dostaw|eksport|import)\w*", r"wstrzymani\w* (?:dostaw|eksportu|importu)", r"przenosi produkcję", r"\bgromadz\w* zapas\w*",
        ],
    },
    "energia_surowce": {
        "label": "Energia i surowce (tranzyt, magazyny, kontrakty)",
        "weight": 2.0,
        "patterns": [
            r"\bgas transit", r"\btransit (?:capacity|contract|volumes?)", r"\bstorage (?:levels?|fill|sites?)",
            r"\b(?:not|didn't|did not|declin\w*) (?:to )?book\w* (?:additional )?capacity", r"\bpipeline (?:flows?|deliveries)",
            r"\bcancel\w* (?:\w+ )?(?:LNG|gas|oil|supply) (?:deal|contract|cargo\w*)", r"\btanker\w* (?:divert|avoid)\w*",
            r"tranzyt\w* gazu", r"magazyn\w* gazu", r"przepustowoś\w*", r"zrywa (?:\w+ )?kontrakt",
        ],
    },
}

# Zaprzeczenia osłabiają sygnał (firma dementuje, "nie planuje", wznawia).
NEGATION = re.compile(
    r"\b(?:denies|denied|no plans? to|rules? out|not (?:exit|leav|withdraw|sell)\w*|won't|will not|resum\w*|returns? to|reopen\w*|back in|lifts?)\b"
    r"|\bdementuje|\bnie (?:planuje|wycofuj\w*|zawiesz\w*|sprzeda\w*|zamierza)|\bnie ma (?:planów|sygnałów)|\bwznawia|\bwraca",
    re.I,
)

# Reakcja na to, co już się dzieje (atak, awaria, katastrofa). Niska waga: to nie jest sygnał wyprzedzający.
REACTIVE = re.compile(
    r"\b(?:attack\w*|strikes?\b|airstrike\w*|drone\w*|missile\w*|shelling|explosion\w*|blast|outage|blackout|fire\b|flood\w*|earthquake|"
    r"storm|hurricane|typhoon|cyberattack\w*|hack\w*|bombing|fighting|clashes|sabotage|"
    r"amid (?:[\w.,-]+ ){0,4}(?:war|hostilities)\b|as war\b|following (?:the )?(?:attack|strikes?)|due to (?:\w+ ){0,2}airspace closure|"
    r"atak\w*|ostrzał\w*|nalot\w*|dron\w*|rakiet\w*|awari\w*|pożar\w*|powodz\w*|eksplozj\w*|wybuch\w*|sabotaż\w*)",
    re.I,
)

# Rzeczy, które pasują do wzorców, ale nie są ruchami biznesowymi ani państwowymi.
NOISE = re.compile(
    r"\b(?:marathon|olympic\w*|world cup|championship|tournament|football|soccer|club|league|match|athlete|eurovision|festival|"
    r"film|movie|concert|album|semifinal\\w*|quarterfinal\\w*|advances|GP|MotoGP|F1|squad|injury|injured|rider|player|coach|team|race|sport\\w*|olympics|election|re-election|candidate|campaign|lobby|divests? from israel|bds|celebrity|tennis|grand prix|"
    r"maraton|kadr\\w*|kontuzj\\w*|zawodnik\\w*|trener\\w*|mistrzostw\w*|turniej\w*|piłk\w*|klub\w*|wybor\w*|kandydat\w*|porodówk\w*|szpital\w*|festiwal\w*|film\w*)\b",
    re.I,
)

# Katastrofy naturalne, niewybuchy, epidemie: ewakuacje i ostrzeżenia z tych powodów nie zapowiadają kryzysów politycznych.
DISASTER = re.compile(
    r"\b(?:wildfires?|bushfires?|forest fires?|floods?|flooding|flash flood\w*|torrential|heavy rain\w*|rainfall|monsoon|hurricane|typhoon|cyclone|"
    r"tornado\w*|earthquake|quake|tsunami|volcan\w*|eruption|landslides?|mudslides?|heatwave|snowstorm|blizzard|tropical storm|winter storm|"
    r"unexploded|(?:WWII|WW2|World War (?:II|2)|wartime) (?:bomb|shell|ordnance)|bomb (?:found|discovered|disposal)|gas leak|chemical leak|"
    r"ebola|cholera|measles|mpox|disease outbreak|pandemic|epidemic|screwworm|livestock|cattle|bird flu|avian|swine fever|foot-and-mouth|"
    r"pożar\w* (?:lasu|lasów)|powód\w*|trzęsieni\w* ziemi|huragan\w*|tajfun\w*|niewybuch\w*|epidemi\w*)\b",
    re.I,
)

# Ostrzeżenia dla podróżnych bywają rutynowe (coroczne aktualizacje, karnawał). Mocne są tylko podwyższenia i „nie podróżuj / wyjedź”.
STRONG_ADVISORY = re.compile(
    r"\b(?:do not travel|level 4|reconsider travel|leave (?:the country )?immediately|raises?|raised|elevat\w*|upgrad\w*|ordered departure|authori[sz]ed departure|"
    r"advises? against all|nie podróżuj\w*|natychmiast\w* opuści\w*)",
    re.I,
)
_ROUTINE_ADVISORY = re.compile(r"\btravel (?:advisory|warning)|\bostrzeżeni\w* (?:dla podróżnych|przed podróż)", re.I)

# Turnieje w nazwach własnych ("Qatar Open", "Dubai Masters", "Davis Cup") — wielkość liter ma znaczenie.
NOISE_CASED = re.compile(r"\b(?:Open|Masters|Cup|Rally|Tour|Classic|Championships?|Games|Grand Slam|ATP|WTA|FIFA|UEFA|NBA|NFL|NHL|Formula 1)\b")

# Kontekst bezpieczeństwa: bez niego wyjście firmy z rynku to zwykle biznes, nie zapowiedź kryzysu.
SECURITY_CONTEXT = re.compile(
    r"\b(?:tension\w*|security|safety|sanction\w*|war\b|conflict|geopolitic\w*|military|unrest|protests?|instability|escalat\w*|"
    r"threat\w*|crisis|invasion|blockade|evacuat\w*|risk\w*|"
    r"napię\w*|bezpieczeństw\w*|sankcj\w*|wojn\w*|konflikt\w*|kryzys\w*|zagrożeni\w*|niestabiln\w*)",
    re.I,
)
SENSITIVE_SECTOR = re.compile(
    r"\b(?:airlines?|airways|carrier|insurer\w*|reinsur\w*|shipping|shipowner\w*|tanker\w*|container|oil|gas|LNG|energy|refin\w*|"
    r"pipeline|bank\w*|lender\w*|defen[cs]e|arms|mining|grain|fertili[sz]er|linie lotnicze|ubezpieczyc\w*|armator\w*|bank\w*|gazow\w*|naftow\w*)",
    re.I,
)
_CONTEXT_NEEDED = {"wyjscie_z_rynku", "sprzedaz_aktywow", "wstrzymane_inwestycje"}

# Aktorzy państwowi: rządy, ambasady, wojsko. Liczą się, ale osobno od firm.
GOV_ACTOR = re.compile(
    r"^(?:the )?(?:US|U\.S\.|UK|EU|NATO|UN|EASA|FAA|OFAC|Washington|London|Paris|Berlin|Moscow|Beijing|Kremlin|State Department|Foreign Office|"
    r"[A-Z][a-z]+ (?:government|embassy|ministry|military|army|navy))\b|\bembassy\b|\bministry\b|\bMSZ\b|\brząd\w*\b|\bambasad\w*",
    re.I,
)

# --- Kraje (ISO-2 -> warianty nazw EN/PL) -------------------------------------
COUNTRIES: dict[str, list[str]] = {
    "UA": ["Ukraine", "Ukrainian", "Kyiv", "Kiev", "Ukrain", "Kijów", "Kijow", "Odesa", "Odessa", "Kharkiv"],
    "RU": ["Russia", "Russian", "Moscow", "Kremlin", "Rosj", "Rosyj", "Moskw"],
    "BY": ["Belarus", "Belarusian", "Minsk", "Białoru", "Bialoru"],
    "TW": ["Taiwan", "Taiwanese", "Taipei", "Tajwan"],
    "CN": ["China", "Chinese", "Beijing", "Shanghai", "Chin[ay]\\w*", "Pekin"],
    "IR": ["Iran\\b", "Iranian", "Tehran", "Teheran", "Strait of Hormuz", "Hormuz", "Ormuz"],
    "IL": ["Israel", "Israeli", "Tel Aviv", "Izrael"],
    "PS": ["Gaza", "West Bank", "Palestin", "Strefie Gazy", "Strefy Gazy"],
    "LB": ["Lebanon", "Lebanese", "Beirut", "Liban", "Bejrut", "Hezbollah"],
    "SY": ["Syria", "Syrian", "Damascus", "Syri"],
    "IQ": ["Iraq", "Iraqi", "Baghdad", "Irak", "Kurdistan"],
    "YE": ["Yemen", "Houthi", "Jemen", "Red Sea", "Morze Czerwone", "Morzu Czerwonym", "Bab el-Mandeb"],
    "SA": ["Saudi Arabia", "Saudi", "Riyadh", "Arabi[a-z]* Saudyjsk"],
    "QA": ["Qatar", "Katar", "Doha"],
    "AE": ["United Arab Emirates", "UAE", "Dubai", "Abu Dhabi", "Emirat\\w* Arabsk", "Dubaj"],
    "KW": ["Kuwait", "Kuwejt"],
    "OM": ["Oman\\b"],
    "TR": ["Turkey", "Türkiye", "Turkish", "Ankara", "Istanbul", "Turcj", "Stambu"],
    "GE": ["Georgia\\b", "Tbilisi", "Gruzj"],
    "AM": ["Armenia", "Yerevan", "Armeni"],
    "AZ": ["Azerbaijan", "Baku", "Azerbejdżan"],
    "KZ": ["Kazakhstan", "Kazachstan"],
    "MD": ["Moldova", "Transnistria", "Mołdaw", "Naddniestrz"],
    "RS": ["Serbia", "Belgrade", "Serbi"],
    "XK": ["Kosovo", "Kosow"],
    "BA": ["Bosnia", "Republika Srpska", "Sarajevo", "Bośni"],
    "VE": ["Venezuela", "Wenezuel", "Caracas"],
    "GY": ["Guyana", "Gujan"],
    "CU": ["Cuba", "Kub[aiy]\\b", "Havana"],
    "PA": ["Panama Canal", "Panama\\b", "Kanał Panamski"],
    "KP": ["North Korea", "Pyongyang", "Korea Północn", "Kore\\w* Północn"],
    "KR": ["South Korea", "Seoul", "Korea Południow"],
    "JP": ["Japan", "Japoni", "Tokyo"],
    "PH": ["Philippines", "Filipin", "South China Sea", "Morze Południowochińskie"],
    "PK": ["Pakistan\\b"],
    "IN": ["India\\b", "Indii\\b", "Indiach"],
    "AF": ["Afghanistan", "Afganistan", "Kabul"],
    "EG": ["Egypt", "Egipt", "Suez", "Sues"],
    "LY": ["Libya", "Libi"],
    "SD": ["Sudan\\b"],
    "ET": ["Ethiopia", "Etiopi"],
    "SO": ["Somalia", "Somali"],
    "NG": ["Nigeria", "Nigeri"],
    "ML": ["Mali\\b"],
    "NE": ["Niger\\b"],
    "BF": ["Burkina Faso"],
    "CD": ["Congo", "DRC", "Kongo"],
    "MZ": ["Mozambique", "Mozambik"],
    "MM": ["Myanmar", "Burma", "Birm"],
    "PL": ["Poland", "Polish", "Polsk", "Polsce", "Warsaw", "Warszaw"],
    "DE": ["Germany", "German", "Niemc", "Niemiec", "Berlin"],
    "LT": ["Lithuania", "Litw", "Vilnius", "Wilno", "Wilni"],
    "LV": ["Latvia", "Łotw", "Riga\\b"],
    "EE": ["Estonia", "Estoni", "Tallinn"],
    "FI": ["Finland", "Finlandi", "Helsinki"],
    "SE": ["Sweden", "Szwecj", "Gotland"],
    "NO": ["Norway", "Norweg", "Norwegi"],
    "DK": ["Denmark", "Dani[ia]\\b", "Greenland", "Grenlandi"],
    "RO": ["Romania", "Rumuni"],
    "HU": ["Hungary", "Węgr"],
    "SK": ["Slovakia", "Słowacj"],
    "CZ": ["Czech", "Czech\\w*\\b"],
    "ZA": ["South Africa", "RPA"],
    "AR": ["Argentina", "Argentyn"],
    "BR": ["Brazil", "Brazyli"],
    "MX": ["Mexico", "Meksyk"],
}
_COUNTRY_RES = {code: re.compile(r"\b(?:" + "|".join(names) + r")", re.I) for code, names in COUNTRIES.items()}
# Kraje, które łatwo złapać fałszywie (Georgia stan USA, India w Indiana, Berlin jako miasto decyzji...)
_COUNTRY_GUARDS = {
    "GE": re.compile(r"\bAtlanta|\bGeorgia,? U\.?S|\bGeorgia (?:state|governor|senate|bulldogs|tech)", re.I),
    "IN": re.compile(r"Indiana|Indian Ocean", re.I),
    "CZ": re.compile(r"\bczech\w* (?:list|się)", re.I),
}
_ALL_COUNTRY_NAMES = "|".join(n for names in COUNTRIES.values() for n in names)
# Kraj docelowy ruchu: "w/z/do Polski", "in/from/to/over Ukraine"
_TARGET_PREP = re.compile(
    r"\b(?:in|from|to|into|over|out of|across|near|off|with|at|within|through|z|ze|w|we|do|na|nad|przez|wobec)\s+(?:the\s+|its\s+)?(?:" + _ALL_COUNTRY_NAMES + r")",
    re.I,
)
# "exit Russia", "leaves Belarus": wyjście wprost z nazwą kraju
_EXIT_COUNTRY = re.compile(
    r"\b(?:(?:exit|exits|exiting|leave|leaves|leaving|quits?|quitting)\s+(?:the\s+)?|(?:withdraw\w*|pull\w* out)\s+(?:of|from)\s+(?:the\s+)?"
    r"|wycof\w* (?:się )?(?:z|ze)\s+)(?:" + _ALL_COUNTRY_NAMES + r")", re.I)

# --- Firmy --------------------------------------------------------------------
_SUFFIX = r"(?:Inc|Corp|Corporation|plc|PLC|AG|SE|SA|S\.A\.|NV|N\.V\.|ASA|AB|Ltd|LLC|Group|Holdings?|Oil|Gas|Energy|Bank|Airlines?|Airways|Motors?|Petroleum|Mining|Steel|Logistics|Shipping)"
_COMPANY_SUFFIX_RE = re.compile(r"\b((?:[A-Z][\w&.\-]+ ){0,3}[A-Z][\w&.\-]+ " + _SUFFIX + r")\b")
_STOP_WORDS = {
    "The", "A", "An", "US", "U.S.", "UK", "EU", "Why", "How", "What", "Exclusive", "Analysis", "Update", "Breaking", "Report",
    "Reports", "Factbox", "Explainer", "Live", "Watch", "Opinion", "Sources", "Source", "Insurers", "Banks", "Banki", "Firms",
    "Companies", "Kolejna", "Kolejny", "Firma", "Spółka", "Gigant", "All", "Some", "Many", "Several", "Major", "Top", "Big",
    "Global", "Foreign", "Western", "European", "American", "Chinese", "Russian", "Polish", "New", "More", "After", "Amid",
}


_VERB_STOP = (
    r"^(?:Suspends?|Halts?|Exits?|Withdraws?|Sells?|Evacuates?|Relocates?|To|Will|Says|Said|Plans|Is|Are|Has|Have|Cuts?|Moves?|"
    r"Closes?|Pulls?|Cancels?|Terminates?|Ends?|Loses?|Stops?|Freezes?|Puts?|Shelves?|Postpones?|Pauses?|Scraps?|Reroutes?|"
    r"Orders?|Hikes?|Raises?|Reduces?|Warns?|Faces?|Seeks?|Considers?|Agrees?|Signs?|Wins?|Opens?|Buys?|Acquires?|Expands?|"
    r"Wycofuje|Zawiesza|Sprzedaje|Zamyka|Wstrzymuje|Zrywa|Ewakuuje|Przenosi|Ogranicza|Kupuje|Przejmuje)$"
)
_COMMON_WORDS = {
    "low", "lowest", "high", "europe", "european", "strait", "global", "world", "oil", "gas", "energy", "prices", "markets", "market",
    "stocks", "shares", "investors", "traders", "analysts", "experts", "officials", "government", "minister", "president", "war",
    "crisis", "conflict", "tensions", "attack", "breaking", "latest", "today", "week", "how", "why", "what", "when", "where", "who",
    "this", "that", "these", "here", "there", "it", "its", "one", "two", "three", "first", "second", "major", "huge", "massive",
    "mięsny", "polski", "polska", "zagraniczny", "zagraniczne", "duży", "wielki", "rynek", "rząd", "minister", "eksperci",
}


@dataclass
class Signal:
    category: str
    weight: float
    country: str | None
    company: str | None
    matched: str
    negated: bool
    reactive: bool = False
    actor: str = "firma"   # firma / panstwo / nieznany


def detect_countries(text: str) -> list[str]:
    found = []
    for code, rx in _COUNTRY_RES.items():
        if rx.search(text):
            guard = _COUNTRY_GUARDS.get(code)
            if guard and guard.search(text):
                continue
            found.append(code)
    return found


def target_countries(text: str) -> list[str]:
    """Kraje, których dotyczy ruch. Najpierw te po przyimku ("in Ukraine"), inaczej wszystkie wspomniane.

    "Poland's Orlen cancels Qatar LNG deal" -> lepiej QA niż PL, ale bez przyimka zostawiamy oba.
    """
    mentioned = detect_countries(text)
    targeted = []
    for m in list(_TARGET_PREP.finditer(text)) + list(_EXIT_COUNTRY.finditer(text)):
        targeted += [c for c in detect_countries(m.group(0)) if c in mentioned]
    if targeted:
        return list(dict.fromkeys(targeted))
    # Bez przyimka: odrzuć kraj występujący tylko jako "Poland's"/"Polski" (kraj pochodzenia firmy), jeśli są inne
    possessive = {c for c in mentioned if re.search(r"\b(?:" + "|".join(COUNTRIES[c]) + r")\w*(?:'s|’s|-(?:controlled|owned|backed|based|listed))\b", text, re.I)}
    rest = [c for c in mentioned if c not in possessive]
    return rest or mentioned


def _clean_name(tokens: list[str]) -> str | None:
    while tokens and (tokens[0] in _STOP_WORDS or tokens[0].endswith("'s") and detect_countries(tokens[0])):
        tokens = tokens[1:]
    name = " ".join(tokens).strip(" ,:;-–—'\"")
    name = re.sub(r"'s$", "", name)
    if not name or len(name) < 2 or name in _STOP_WORDS or detect_countries(name) and len(name.split()) == 1:
        return None
    return name


def detect_company(text: str, watchlist: list[str] | None = None, match_start: int | None = None) -> str | None:
    if watchlist:
        for name in watchlist:
            if re.search(r"\b" + re.escape(name) + r"\b", text, re.I):
                return name
    # Raporty spółek: "ORLEN: Zawieszenie...", "Acme Corp: The Company suspended..."
    m = re.match(r"^([A-ZĄĆĘŁŃÓŚŹŻ0-9][\w&.\-' ]{1,60}?):\s", text)
    if m and not detect_countries(m.group(1)) and m.group(1).split()[0] not in {"UK", "US", "EU", "OFAC", "Exclusive", "Analysis", "Update", "Breaking"}:
        return m.group(1).strip()
    m = _COMPANY_SUFFIX_RE.search(text)
    if m:
        name = _clean_name(m.group(1).split())
        if name:
            return name
    # Nazwa przed słowem-kluczem: kolejne wyrazy z wielkiej litery tuż przed dopasowaniem
    head = text[:match_start] if match_start else text
    words = head.split()
    if not words:
        return None
    # Pierwsza grupa wyrazów z wielkiej litery na początku nagłówka
    title_case = sum(1 for w in words if w[:1].isupper()) / len(words) > 0.6 and len(words) > 4
    lead = []
    for w in words[:5]:
        if re.match(r"^[A-ZĄĆĘŁŃÓŚŹŻ0-9][\w&.\-']*$", w) and not re.match(
                _VERB_STOP, w) and not re.match(r"^\d", w):
            lead.append(w)
        else:
            break
    if title_case:
        lead = lead[:2]
        if lead and lead[0].lower() in _COMMON_WORDS:
            return None
    name = _clean_name(lead[:4])
    if name and name.split()[0].lower() in _COMMON_WORDS:
        return None
    return name


def classify(title: str, watchlist: list[str] | None = None) -> list[Signal]:
    """Zwraca listę sygnałów znalezionych w tekście (zwykle 0 lub 1-2)."""
    text = " ".join(title.split())
    if NOISE.search(text) or NOISE_CASED.search(text) or DISASTER.search(text):
        return []
    security = bool(SECURITY_CONTEXT.search(text))
    sector = bool(SENSITIVE_SECTOR.search(text))
    countries = target_countries(text)
    negated = bool(NEGATION.search(text))
    reactive = bool(REACTIVE.search(text))
    gov = bool(GOV_ACTOR.search(text))
    measurement = bool(re.match(r"(?:Air traffic over|Defence procurement surge|Ship traffic through|Tanker traffic through)", text))
    out: list[Signal] = []
    for key, cat in CATEGORIES.items():
        extra = [_EXIT_COUNTRY.pattern] if key == "wyjscie_z_rynku" else []
        for pat in cat["patterns"] + extra:
            m = re.search(pat, text, re.I)
            if m:
                company = None if gov or measurement else detect_company(text, watchlist, m.start())
                actor = ("pomiar" if measurement else "panstwo" if gov or key in ("ostrzezenia_panstw", "sankcje")
                         else ("firma" if company else "nieznany"))
                w = cat["weight"]
                if negated:
                    w *= 0.2
                if reactive:
                    w *= 0.35
                if actor == "nieznany":
                    w *= 0.6
                if key in _CONTEXT_NEEDED and not security:
                    # bez kontekstu bezpieczeństwa wyjście z rynku czy sprzedaż aktywów to zwykle biznes
                    w *= 0.5 if sector else 0.15
                if key == "ostrzezenia_panstw" and _ROUTINE_ADVISORY.search(m.group(0)) and not STRONG_ADVISORY.search(text):
                    w *= 0.4
                if key in ("lotnictwo_przestrzen", "ewakuacja_personelu") and security and not reactive and not negated:
                    # to typy sygnałów, które w teście dawały realne wyprzedzenie (FAA i Wenezuela, Dubaj, Bejrut)
                    w *= 1.25
                for c in countries or [None]:
                    out.append(Signal(key, w, c, company, m.group(0), negated, reactive, actor))
                break
    # Lotnictwo jest bardziej konkretne niż ogólne "zawieszenie działalności" z tego samego nagłówka
    if any(s.category == "lotnictwo_przestrzen" for s in out):
        out = [s for s in out if s.category != "wyjscie_z_rynku"]
    # "Ewakuacja" i "wyjście" w jednym nagłówku o państwie to zwykle ten sam fakt: zostaw silniejszy
    if gov and len({s.category for s in out}) > 1:
        best = max(out, key=lambda s: s.weight).category
        out = [s for s in out if s.category == best]
    return out
