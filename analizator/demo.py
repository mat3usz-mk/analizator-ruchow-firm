"""Dane SYNTETYCZNE do pokazania działania. Firmy są zmyślone, nagłówki generowane.

Scenariusz: przez pół roku w kilku krajach pojawia się zwykły szum (pojedyncze
sprzedaże aktywów, przekierowania dostaw). W ostatnich 4 tygodniach w jednym
kraju (tu: Mołdawia, wybrana przypadkowo) rośnie liczba RÓŻNYCH ruchów różnych
firm: ewakuacje, ubezpieczyciele, wstrzymane dostawy. W drugim kraju (Turcja)
jest dużo artykułów, ale wszystkie o jednej firmie: analizator ma to rozróżnić.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

FIRMS = [
    "Nordvik Energy", "Halberg Gas", "Corvant Group", "Belmora Bank", "Astrel Motors", "Quellin Oil",
    "Varden Holdings", "Ostria Airlines", "Kestrel Logistics Group", "Talmar Bank", "Brenno AG", "Sarvik plc",
]
COUNTRIES = ["Moldova", "Turkey", "Kazakhstan", "Serbia", "Georgia"]
NOISE_TEMPLATES = [
    "{firm} sells stake in {country} retail unit",
    "{firm} reroutes some shipments via {country}",
    "{firm} posts quarterly results, cites {country} demand",
    "{firm} opens new office in {country}",
]
ESCALATION_TEMPLATES = [
    "{firm} evacuates non-essential staff from {country}",
    "Insurers cancel war risk cover for flights over {country}",
    "{firm} suspends operations in {country}",
    "{firm} halts shipments to {country}, cites force majeure",
    "{firm} to reduce exposure to {country}",
    "{firm} relocates employees from {country} office",
]


def generate(today: date | None = None, weeks: int = 26, seed: int = 7) -> list[dict]:
    rnd = random.Random(seed)
    today = today or date.today()
    start = today - timedelta(weeks=weeks)
    arts = []

    def add(d: date, title: str):
        arts.append({"url": f"https://example.invalid/{len(arts)}", "title": title, "date": d.isoformat(),
                     "source": "demo", "domain": "example.invalid", "lang": "en"})

    d = start
    while d <= today:
        for country in COUNTRIES:
            if rnd.random() < 0.12:
                add(d, rnd.choice(NOISE_TEMPLATES).format(firm=rnd.choice(FIRMS), country=country))
        d += timedelta(days=1)

    # Eskalacja: Mołdawia, ostatnie 4 tygodnie, coraz więcej różnych firm
    for i in range(28):
        day = today - timedelta(days=27 - i)
        if rnd.random() < 0.15 + i / 40:
            add(day, rnd.choice(ESCALATION_TEMPLATES).format(firm=rnd.choice(FIRMS), country="Moldova"))

    # Hałas medialny: Turcja, jedna firma, dużo artykułów o tym samym
    for i in range(25):
        add(today - timedelta(days=rnd.randint(0, 13)), "Halberg Gas suspends operations in Turkey after dispute")
    return arts
