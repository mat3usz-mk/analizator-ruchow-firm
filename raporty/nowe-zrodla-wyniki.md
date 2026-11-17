# Nowe źródła i test permutacyjny (2026-11-17)

Każde źródło sprawdzone osobno. Trafny alarm: wydarzenie w tym kraju w ciągu 60 dni. Wartość p z testu permutacyjnego: odsetek losowań (daty wydarzeń losowo przesunięte albo kraje zamienione), w których wynik był co najmniej tak dobry jak naprawdę; mniej niż 0,05 = raczej nie przypadek.

## Test permutacyjny

| alarm | okres | alarmów | trafnych | losowo (przesunięcie) | p | losowo (zamiana krajów) | p |
|---|---|---|---|---|---|---|---|
| impuls 48 h ≥ 10 | 2019–2024 | 78 | 16 (21%) | 7.4 | 0.001 | 8.6 | 0.006 |
| impuls 48 h ≥ 6 | 2019–2024 | 368 | 37 (10%) | 27.0 | 0.023 | 28.0 | 0.025 |
| wyuczone pary śladów | 2019–2024 | 455 | 46 (10%) | 36.1 | 0.056 | 35.6 | 0.028 |
| twarde dane + potwierdzenie (48 h) | 2019–2024 | 310 | 25 (8%) | 19.9 | 0.118 | 20.4 | 0.173 |
| impuls 48 h ≥ 10 | 2025–2026 (test) | 44 | 11 (25%) | 6.0 | 0.015 | 7.9 | 0.075 |
| impuls 48 h ≥ 6 | 2025–2026 (test) | 126 | 16 (13%) | 12.4 | 0.144 | 14.6 | 0.362 |
| wyuczone pary śladów | 2025–2026 (test) | 190 | 22 (12%) | 21.9 | 0.540 | 24.5 | 0.810 |
| twarde dane + potwierdzenie (48 h) | 2025–2026 (test) | 95 | 15 (16%) | 11.2 | 0.114 | 11.3 | 0.076 |

## Nowe źródła osobno

Samo źródło jako alarm:

| źródło | okres | sygnałów | epizodów | precyzja | przewaga nad losowym | p (przesunięcie) | p (zamiana) |
|---|---|---|---|---|---|---|---|
| wiki | 2019–2024 | 174 | 71 | 8% | 2.1× | 0.328 | 0.268 |
| wiki | 2025–2026 (test) | 19 | 5 | 0% | 0.0× | 1.000 | 1.000 |
| ton | 2019–2024 | 1084 | 670 | 3% | 0.7× | 0.963 | 0.953 |
| ton | 2025–2026 (test) | 232 | 154 | 3% | 0.8× | 0.713 | 0.864 |

Dołożone do ręcznego indeksu (próg 40, wydarzenie w 60 dni):

| wariant | okres | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |
|---|---|---|---|---|---|---|
| bez nowych źródeł | 2019–2024 | 48% | 26% | 9% | 90 | 967 |
| + wiki | 2019–2024 | 47% | 26% | 8% | 89 | 975 |
| + ton | 2019–2024 | 49% | 29% | 8% | 91 | 1053 |
| bez nowych źródeł | 2025–2026 (test) | 71% | 38% | 11% | 30 | 248 |
| + wiki | 2025–2026 (test) | 71% | 38% | 11% | 30 | 248 |
| + ton | 2025–2026 (test) | 71% | 50% | 10% | 30 | 275 |

## Zapasy ropy EIA (sygnał globalny)

Nietypowy tydzień (zmiana zapasów ≥ 2,5 odchylenia od 52 tygodni). Czy w ciągu 30 dni nastąpił kryzys energetyczny albo blokada gdziekolwiek, wobec zwykłego tygodnia.

| okres | nietypowych tygodni | z wydarzeniem w 30 dni | zwykle (każdy tydzień) |
|---|---|---|---|
| 2019–2024 | 11 | 2 (18%) | 19% |
| 2025–2026 (test) | 3 | 2 (67%) | 29% |

Reguła Sahm (bezrobocie w USA) pominięta: wskaźnik miesięczny, dotyczy tylko gospodarki USA i nie ma związku z krajami, dla których analizator szuka wydarzeń. Google Trends pominięte: brak oficjalnego dostępu do historii (tylko nieoficjalne pobieranie strony, blokowane przy większej liczbie zapytań); zamiast tego odsłony Wikipedii z oficjalnego API Wikimedia.

To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna.
