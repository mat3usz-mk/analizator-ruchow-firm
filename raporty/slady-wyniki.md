# Łączenie śladów: test historyczny (2026-11-17)

Zbieżność: w oknie W dni w kraju pojawiły się nowe sprawy (bez przedruków) z co najmniej K różnych kanałów (loty i przestrzeń powietrzna, ambasady, ewakuacje, ostrzeżenia, wycofanie firm, finanse i ubezpieczenia, waluta, sankcje, statki i dostawy, energia, giełda (krótka sprzedaż, opcje)). Kolejne dni zbieżności w odstępie do 7 dni to jeden epizod. Precyzja: odsetek epizodów, po których w ciągu 60 dni nastąpiło wydarzenie w tym kraju. Przewaga = precyzja / odsetek zwykłych dni kraju, po których nastąpiło wydarzenie.

Ślady w danych: firmy 23493, sankcje 18694, ambasady 5798, loty 3453, statki 3431, energia 1222, finanse 671, twarde gielda 539, twarde sankcje 285, twarde waluta 153, twarde energia 24.

## Które ślady i pary śladów poprzedzają wydarzenia

Para „A → B (do L dni)”: ślad B pojawia się, gdy ślad A był w tym kraju w ciągu L dni wcześniej (z innej sprawy). Przewaga liczona na latach 2019–2024, potem sprawdzona na 2025–2026, których dobór nie widział. „Ściągnięta” przewaga uwzględnia małą liczbę epizodów.

### Pojedyncze kanały

| kanał | epizodów 2019–24 | precyzja | przewaga | epizodów 2025–26 | precyzja | przewaga |
|---|---|---|---|---|---|---|
| loty i przestrzeń powietrzna | 1026 | 6% | 1.5× | 366 | 9% | 2.2× |
| ambasady, ewakuacje, ostrzeżenia | 1594 | 6% | 1.4× | 535 | 9% | 2.2× |
| wycofanie firm | 3527 | 4% | 1.0× | 1037 | 5% | 1.2× |
| finanse i ubezpieczenia | 368 | 7% | 1.6× | 115 | 9% | 2.1× |
| waluta | 112 | 4% | 0.9× | 19 | 0% | 0.0× |
| sankcje | 2482 | 5% | 1.2× | 681 | 5% | 1.3× |
| statki i dostawy | 961 | 7% | 1.8× | 327 | 9% | 2.3× |
| energia | 401 | 9% | 2.2× | 147 | 10% | 2.5× |
| giełda (krótka sprzedaż, opcje) | 338 | 5% | 1.2× | 136 | 10% | 2.3× |

### Najlepsze pary na latach 2019–2024 i jak wypadły w 2025–2026

| para | epizodów 2019–24 | precyzja | przewaga (ściągnięta) | epizodów 2025–26 | precyzja | przewaga |
|---|---|---|---|---|---|---|
| statki i dostawy → giełda (krótka sprzedaż, opcje) (do 2 dni) | 17 | 29% | 3.9× | 10 | 20% | 4.8× |
| energia → finanse i ubezpieczenia (do 7 dni) | 51 | 20% | 3.8× | 18 | 11% | 2.7× |
| giełda (krótka sprzedaż, opcje) → energia (do 7 dni) | 12 | 33% | 3.7× | 5 | 0% | 0.0× |
| energia → statki i dostawy (do 2 dni) | 90 | 17% | 3.6× | 27 | 26% | 6.3× |
| statki i dostawy → energia (do 7 dni) | 127 | 16% | 3.5× | 49 | 18% | 4.4× |
| giełda (krótka sprzedaż, opcje) → statki i dostawy (do 2 dni) | 14 | 29% | 3.5× | 7 | 14% | 3.4× |
| statki i dostawy → finanse i ubezpieczenia (do 7 dni) | 123 | 15% | 3.4× | 51 | 16% | 3.8× |
| statki i dostawy → finanse i ubezpieczenia (do 2 dni) | 74 | 16% | 3.4× | 36 | 22% | 5.4× |
| loty i przestrzeń powietrzna → statki i dostawy (do 2 dni) | 164 | 15% | 3.3× | 78 | 18% | 4.3× |
| energia → ambasady, ewakuacje, ostrzeżenia (do 7 dni) | 155 | 14% | 3.2× | 48 | 17% | 4.0× |
| statki i dostawy → energia (do 14 dni) | 163 | 14% | 3.2× | 62 | 18% | 4.3× |
| energia → statki i dostawy (do 7 dni) | 133 | 14% | 3.2× | 47 | 21% | 5.1× |
| energia → statki i dostawy (do 14 dni) | 158 | 14% | 3.2× | 57 | 21% | 5.1× |
| ambasady, ewakuacje, ostrzeżenia → energia (do 2 dni) | 90 | 14% | 3.1× | 32 | 16% | 3.8× |
| energia → loty i przestrzeń powietrzna (do 14 dni) | 122 | 14% | 3.1× | 56 | 12% | 3.0× |

Z 15 najlepszych par z lat 2019–2024 w 2025–2026 przewagę ponad 1× utrzymało 14 (pozostałe: brak epizodów albo gorzej niż losowo).

### Najsłabsze pary (2019–2024)

| para | epizodów | precyzja | przewaga (ściągnięta) |
|---|---|---|---|
| waluta → wycofanie firm (do 7 dni) | 70 | 4% | 1.0× |
| ambasady, ewakuacje, ostrzeżenia → giełda (krótka sprzedaż, opcje) (do 2 dni) | 23 | 4% | 1.0× |
| giełda (krótka sprzedaż, opcje) → ambasady, ewakuacje, ostrzeżenia (do 2 dni) | 24 | 4% | 1.0× |
| waluta → wycofanie firm (do 14 dni) | 91 | 3% | 0.9× |
| waluta → wycofanie firm (do 2 dni) | 43 | 2% | 0.7× |
| statki i dostawy → waluta (do 2 dni) | 10 | 0% | 0.7× |
| finanse i ubezpieczenia → waluta (do 14 dni) | 15 | 0% | 0.6× |
| statki i dostawy → waluta (do 7 dni) | 15 | 0% | 0.6× |

### Reguła z wyuczonymi wagami par

Alarm, gdy w kraju zaszła para, której ściągnięta przewaga na latach 2019–2024 wynosi co najmniej P. Próg wybrany na latach uczenia: P = 3.0.

| P | epizodów 2019–24 | precyzja | przewaga | epizodów 2025–26 | precyzja | przewaga | wydarzeń złapanych ≤30 dni przed (2025–26) |
|---|---|---|---|---|---|---|---|
| 1.5 | 2239 | 4% | 1.0× | 650 | 4% | 1.0× | 25 z 31 (81%) |
| 2.0 | 1673 | 5% | 1.2× | 529 | 6% | 1.4× | 25 z 31 (81%) |
| 2.5 | 1032 | 6% | 1.4× | 373 | 7% | 1.7× | 19 z 31 (61%) |
| 3.0 | 454 | 10% | 2.5× | 195 | 11% | 2.7× | 15 z 31 (48%) |

## Lata 2019–2024 (wydarzenia z listy 2015–2024)

| wariant | okno | K | epizodów | precyzja | przewaga nad losowym | wydarzeń złapanych ≤7 dni przed | ≤30 dni przed |
|---|---|---|---|---|---|---|---|
| wszystkie | 2 dni | 2 | 1804 | 5% | 1.2× | 43 z 99 (43%) | 57 (58%) |
| wszystkie | 2 dni | 3 | 594 | 8% | 1.9× | 23 z 99 (23%) | 33 (33%) |
| wszystkie | 7 dni | 2 | 1977 | 4% | 1.1× | 56 z 99 (57%) | 70 (71%) |
| wszystkie | 7 dni | 3 | 1019 | 6% | 1.5× | 43 z 99 (43%) | 49 (49%) |
| twarde+ | 2 dni | 2 | 332 | 9% | 2.1× | 9 z 99 (9%) | 14 (14%) |
| twarde+ | 2 dni | 3 | 112 | 14% | 3.4× | 7 z 99 (7%) | 10 (10%) |
| twarde+ | 7 dni | 2 | 536 | 7% | 1.7× | 14 z 99 (14%) | 18 (18%) |
| twarde+ | 7 dni | 3 | 316 | 9% | 2.2× | 11 z 99 (11%) | 15 (15%) |
| twarde | 2 dni | 2 | 3 | 33% | 8.3× | 2 z 99 (2%) | 2 (2%) |
| twarde | 2 dni | 3 | 0 | brak | brak | 0 z 99 (0%) | 0 (0%) |
| twarde | 7 dni | 2 | 11 | 10% | 2.5× | 2 z 99 (2%) | 2 (2%) |
| twarde | 7 dni | 3 | 1 | 0% | 0.0× | 0 z 99 (0%) | 0 (0%) |

Bramka na alarmy ręcznego indeksu (próg 40, wydarzenie w 60 dni):

| | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |
|---|---|---|---|---|---|
| bez bramki | 48% | 26% | 9% | 90 | 967 |
| bramka: wszystkie, 2 kanały w 14 dniach | 45% | 20% | 9% | 86 | 854 |
| bramka: twarde+, 2 kanały w 14 dniach | 10% | 6% | 10% | 20 | 181 |
| bramka: wyuczone pary (P 3.0) w 14 dniach | 20% | 11% | 17% | 36 | 174 |

## Test 2025-03 – 2026-11 (wydarzenia 2025–2026)

| wariant | okno | K | epizodów | precyzja | przewaga nad losowym | wydarzeń złapanych ≤7 dni przed | ≤30 dni przed |
|---|---|---|---|---|---|---|---|
| wszystkie | 2 dni | 2 | 559 | 7% | 1.7× | 22 z 31 (71%) | 23 (74%) |
| wszystkie | 2 dni | 3 | 239 | 11% | 2.6× | 14 z 31 (45%) | 19 (61%) |
| wszystkie | 7 dni | 2 | 604 | 5% | 1.2× | 23 z 31 (74%) | 27 (87%) |
| wszystkie | 7 dni | 3 | 342 | 8% | 1.9× | 18 z 31 (58%) | 22 (71%) |
| twarde+ | 2 dni | 2 | 122 | 15% | 3.5× | 3 z 31 (10%) | 9 (29%) |
| twarde+ | 2 dni | 3 | 51 | 19% | 4.6× | 3 z 31 (10%) | 5 (16%) |
| twarde+ | 7 dni | 2 | 213 | 10% | 2.5× | 7 z 31 (23%) | 14 (45%) |
| twarde+ | 7 dni | 3 | 131 | 15% | 3.5× | 7 z 31 (23%) | 12 (39%) |
| twarde | 2 dni | 2 | 3 | 0% | 0.0× | 0 z 31 (0%) | 0 (0%) |
| twarde | 2 dni | 3 | 0 | brak | brak | 0 z 31 (0%) | 0 (0%) |
| twarde | 7 dni | 2 | 8 | 0% | 0.0× | 0 z 31 (0%) | 0 (0%) |
| twarde | 7 dni | 3 | 0 | brak | brak | 0 z 31 (0%) | 0 (0%) |

Bramka na alarmy ręcznego indeksu (próg 40, wydarzenie w 60 dni):

| | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |
|---|---|---|---|---|---|
| bez bramki | 71% | 38% | 11% | 30 | 248 |
| bramka: wszystkie, 2 kanały w 14 dniach | 68% | 40% | 12% | 29 | 221 |
| bramka: twarde+, 2 kanały w 14 dniach | 39% | 14% | 19% | 14 | 59 |
| bramka: wyuczone pary (P 3.0) w 14 dniach | 42% | 35% | 18% | 14 | 63 |

Ślady z lotów i ambasad w latach historycznych pochodzą z nagłówków (bieżące strony FAA, EASA i ambasad nie mają archiwum), twarde dane to kursy walut, sankcje UE/UK, przejścia statków, krótka sprzedaż i magazyny gazu. Daty wydarzeń są przybliżone. To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna.
