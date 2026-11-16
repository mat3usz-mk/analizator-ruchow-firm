"""Chłodna ocena wiadomości: oddziela rzeczowe informacje od straszenia, clickbaitu, spekulacji,
treści sponsorowanych i komunikatów marketingowych.

Zasada: fakt opisany spokojnie („Maersk suspends Red Sea transits”) waży normalnie. Ten sam temat podany
emocjonalnie („SHOCKING: World War 3 could start TONIGHT as panic grips…”) waży mało, bo częściej jest grą
na emocjach niż nową informacją. Treści sponsorowane, komunikaty z płatnych serwisów prasowych i raporty
„rynkowe” prawie nic nie ważą albo są pomijane.

Wszystko na regułach (bez AI), więc nie zużywa limitu i działa tak samo w czuwaniu, raporcie i teście historycznym.
"""
from __future__ import annotations

import re

# --- Język emocji, straszenia i clickbaitu -------------------------------------------------
_FEAR_EN = (r"shock\w*|terrif\w*|horrif\w*|panic\w*|chaos|meltdown|apocalyp\w*|armageddon|doomsday|nightmare|catastroph\w*|"
            r"bloodbath|carnage|mayhem|hysteria|frenzy|devastat\w*|brink of|on the edge of|world war (?:3|iii|three)|ww3|wwiii|"
            r"nuclear (?:war|armageddon|holocaust)|end of the world|all-out war|total war|imminent (?:war|attack|invasion|collapse)|"
            r"brace (?:yourself|for)|you won'?t believe|what happens next|here'?s why|this is why|the truth about|"
            r"bombshell|stunning|jaw-dropping|unthinkable|sinister|chilling|ominous|"
            r"fears? (?:grow|mount|soar|spark)|sparks? (?:fears|panic)|alarm bells|sends shockwaves|"
            r"crash(?:es)? (?:incoming|imminent)|collapse (?:is )?(?:coming|imminent)|get out (?:now|while)|"
            r"secret plan|they don'?t want you|insiders? (?:warn|reveal)|leaked|doom")
_FEAR_PL = (r"szok\w*|przeraż\w*|panik\w*|chaos\w*|apokalip\w*|armagedon\w*|koszmar\w*|katastrof\w*|masakr\w*|histeri\w*|"
            r"trzecia wojna|iii wojna|wojna światowa|koniec świata|na skraju|tuż przed wojną|lada (?:dzień|moment)|"
            r"nie uwierzysz|zobacz,? co|oto dlaczego|prawda o|wstrząsając\w*|porażając\w*|mrożąc\w*|alarmując\w*|"
            r"ujawniamy|tajny plan|eksperci biją na alarm|bije na alarm|drżyj|uciekaj\w*")
FEAR = re.compile(r"\b(?:" + _FEAR_EN + "|" + _FEAR_PL + r")", re.I)
# Spekulacja: pytania i „może/mogłoby” zamiast faktu
SPECULATION = re.compile(r"\b(?:could|might|may|would|is (?:this|it|the world)|are we|will (?:there|russia|china|iran|putin|xi)\b|"
                         r"what if|is .{3,40} (?:next|about to|preparing)|prepar\w+ for war|on course for|heading for|"
                         r"czy (?:to|grozi|czeka|będzie|wybuchnie)|może dojść|grozi nam|szykuje się|zbliża się)\b", re.I)
_SPECIAL = re.compile(r"[!?]{2,}|!\s*$")


def emotion_score(title: str) -> tuple[float, list[str]]:
    """0 = rzeczowy tytuł, 1 = mocno emocjonalny. Zwraca też powody (do raportu)."""
    reasons, s = [], 0.0
    # końcówka z nazwą serwisu („... - CHANNELAFRICA”, „... | Reuters”) nie należy do treści tytułu
    title = re.split(r"\s+(?:-|\||–|—|&#x2013;|&#x2014;)\s+(?=[^-|–—]{2,40}$)", title)[0]
    fear = FEAR.findall(title)
    if fear:
        s += 0.35 * min(len(fear), 2)
        reasons.append("język strachu: " + ", ".join(sorted({f.lower() for f in fear})[:3]))
    if SPECULATION.search(title) or title.strip().endswith("?"):
        s += 0.25
        reasons.append("spekulacja zamiast faktu")
    if _SPECIAL.search(title):
        s += 0.2
        reasons.append("wykrzykniki")
    words = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻ]{4,}", title)
    caps = [w for w in words if w.isupper() and len(w) >= 5 and w not in _ACRONYMS]
    if len(caps) >= 2 or (words and len(caps) / len(words) > 0.3):
        s += 0.3
        reasons.append("WIELKIE LITERY")
    if re.match(r"^\s*(?:BREAKING|URGENT|ALERT|PILNE|SZOK|HIT)\b\s*[:!|-]", title):
        s += 0.2
        reasons.append("krzykliwy nagłówek")
    return min(s, 1.0), reasons


_ACRONYMS = {"NATO", "OPEC", "EASA", "OFAC", "NOTAM", "UNHCR", "IAEA", "ESPI", "SWIFT", "IRGC", "ASEAN", "OSCE", "WHO", "USA",
             "FAA", "LNG", "GDP", "IMF", "NASA", "UNSC", "ECOWAS", "BRICS", "TASS", "OBWE", "ORLEN", "KGHM", "PKO", "PZU",
             "CEO", "CFO", "EBITDA", "WTI", "UPDATE", "FOCUS", "ANALYSIS", "EXCLUSIVE"}

# --- Treści sponsorowane, komunikaty prasowe, raporty „rynkowe” ------------------------------
PR_WIRES = {"prnewswire.com", "globenewswire.com", "businesswire.com", "accesswire.com", "einpresswire.com", "newsfilecorp.com",
            "openpr.com", "prweb.com", "issuewire.com", "newswire.com", "prlog.org", "24-7pressrelease.com", "pressreleasepoint.com",
            "marketscreener.com/news/latest", "einnews.com", "newswires.einpresswire.com", "presswire.com", "pr.com"}
SPONSORED = re.compile(r"\b(?:sponsored|advertorial|paid (?:post|content|partnership)|partner content|brand ?studio|promoted|"
                       r"press release|news release|artykuł sponsorowany|materiał (?:partnera|promocyjny|sponsorowany)|"
                       r"tekst sponsorowany|reklama|partner publikacji|komunikat prasowy)\b", re.I)
MARKET_SPAM = re.compile(r"\b(?:market (?:size|share|report|research|analysis|outlook|forecast|trends?|growth)|CAGR|"
                         r"forecast (?:to|till|until|period) 20\d\d|20\d\d-20\d\d|industry (?:report|analysis)|"
                         r"top \d+ (?:companies|players|stocks)|stocks? to (?:buy|watch)|best stocks|price prediction|"
                         r"webinar|whitepaper|download (?:the|our)|sign up|subscribe)\b", re.I)

# --- Źródła o słabej rzetelności ---------------------------------------------------------------
# Tabloidy i portale sensacyjne: często przedrukowują temat z dramatyzmem, rzadko wnoszą nową informację.
TABLOIDS = {"express.co.uk", "dailystar.co.uk", "thesun.co.uk", "mirror.co.uk", "dailymail.co.uk", "metro.co.uk", "nypost.com",
            "dailyexpress.co.uk", "the-sun.com", "news.com.au", "thedailybeast.com", "newsweek.com", "ibtimes.co.uk",
            "fakt.pl", "se.pl", "superexpress.pl", "pudelek.pl", "o2.pl", "pikio.pl", "natemat.pl", "wprost.pl",
            "dorzeczy.pl", "tvp.info", "wpolityce.pl", "niezalezna.pl", "bild.de", "blick.ch", "unilad.com", "ladbible.com"}
# Propaganda państwowa i portale dezinformacyjne: sygnały z nich nie mogą same wywołać alarmu.
PROPAGANDA = {"rt.com", "sputniknews.com", "sputnikglobe.com", "tass.com", "tass.ru", "ria.ru", "presstv.ir", "tasnimnews.com",
              "globaltimes.cn", "almayadeen.net", "southfront.press", "zerohedge.com", "infowars.com", "naturalnews.com",
              "beforeitsnews.com", "globalresearch.ca", "veteranstoday.com", "thegatewaypundit.com", "news-front.info",
              "pravda.ru", "katehon.com", "geopolitica.ru", "strategic-culture.org", "neweasternoutlook.ru", "kresy.pl"}


def _domain(d: str | None) -> str:
    return (d or "").lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]


def domain_class(domain: str | None) -> str | None:
    d = _domain(domain)
    match = lambda pool: d in pool or any(d.endswith("." + x) for x in pool)
    if match(PROPAGANDA):
        return "propaganda"
    if match(TABLOIDS):
        return "tabloid"
    if match(PR_WIRES):
        return "komunikat_prasowy"
    return None


def assess_article(title: str, domain: str | None) -> dict:
    """Ocena jednego artykułu: mnożnik wagi (0 = pomiń) i powody."""
    emo, reasons = emotion_score(title)
    cls = domain_class(domain)
    mult = 1.0
    if MARKET_SPAM.search(title):
        return {"mult": 0.0, "emotion": emo, "class": "reklama_rynkowa", "reasons": ["raport rynkowy / treść reklamowa"]}
    if SPONSORED.search(title):
        cls = cls or "sponsorowany"
        reasons.append("oznaczenie treści sponsorowanej lub komunikatu prasowego")
    if cls in ("sponsorowany", "komunikat_prasowy"):
        mult *= 0.15
        if cls == "komunikat_prasowy":
            reasons.append("płatny serwis komunikatów prasowych")
    elif cls == "propaganda":
        mult *= 0.25
        reasons.append("źródło propagandowe lub dezinformacyjne")
    elif cls == "tabloid":
        mult *= 0.5
        reasons.append("tabloid / portal sensacyjny")
    if emo >= 0.5:
        mult *= 0.35
    elif emo >= 0.25:
        mult *= 0.7
    return {"mult": round(mult, 3), "emotion": round(emo, 2), "class": cls, "reasons": reasons}


def is_credible(e: dict) -> bool:
    """Czy sygnał może POTWIERDZAĆ alarm: rzeczowy, z rzetelnego źródła, nie sponsorowany."""
    return (e.get("credibility", 0.9) >= 0.9 and not e.get("source_class") and e.get("emotion", 0.0) < 0.5)


# Pojedynczy artykuł może sam potwierdzić alarm tylko wtedy, gdy opiera się na oficjalnym ostrzeżeniu albo opisuje ruch
# wielu firm naraz (np. „Six airlines suspend flights to Venezuela amid FAA warning”). Jedna linia lotnicza czy jedno
# zamknięte przejście graniczne to w teście historycznym najczęstsze fałszywe alarmy.
AUTHORITATIVE = re.compile(
    r"\b(?:FAA|EASA|NOTAM|CZIB|State Department|Department of State|embass(?:y|ies)|consulates?|foreign (?:ministry|office)|FCDO|"
    r"travel (?:advisory|warning)|do not travel|ordered departure|authorized departure|non-(?:essential|emergency) (?:staff|personnel)|"
    r"(?:several|multiple|many|major|foreign|international|european|western|gulf|\d+|two|three|four|five|six|seven|eight|nine|ten|dozen\w*) "
    r"(?:\w+ )?(?:airlines|carriers|companies|firms|banks|insurers|shipping (?:lines|companies)|oil (?:majors|companies))|"
    r"airlines (?:suspend|halt|cancel|avoid|stop)|insurers (?:cancel|withdraw|halt)|"
    r"(?-i:[A-Z][\w-]+(?: [A-Z][\w-]+)?(?:,| and| &| i) [A-Z][\w-]+(?: [A-Z][\w-]+)?) (?:\w+ )?(?:suspend|halt|cancel|avoid|stop|pause|zawieszaj|wstrzymuj)\w*|"
    r"ambasad\w*|konsulat\w*|MSZ|ostrzeżeni\w* dla podróżnych|(?:kilka|wiele|liczne) (?:linii|firm|banków))",
    re.I)
