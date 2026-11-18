# Impuls 48 h: dopracowanie (2026-11-18)

Siatka wariantów impulsu: okno (24/48/72 h), długość tła (14/28/56 dni), minimum nowych spraw, premia za nowe kategorie, waga artykułów względem twardych danych, wymóg 2 dni z rzędu, próg. Epizod: alarm impulsu, kolejne w odstępie do 7 dni łączone. Trafny epizod: wydarzenie w tym kraju w ciągu 30 dni. Złapane: wydarzenie, przed którym był epizod do 3/7/30 dni.

Reguła wyboru (z góry): na 2019–2024 precyzja co najmniej jak obecny impuls (13%) i co najmniej 30 epizodów, a z tych najwięcej złapanych do 7 dni. Potem sprawdzenie na 2025–2026 i test permutacyjny (losowe daty wydarzeń, 1000 losowań; p = odsetek losowań co najmniej tak dobrych).

| wariant | okres | epizodów | trafnych | precyzja | złapane ≤3 dni | ≤7 dni | ≤30 dni | p |
|---|---|---|---|---|---|---|---|---|
| okno 24 h, tło 56 dni, min. 1 spraw, premia 1.0, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 100 | 14 | 14% | 10 z 99 | 11 | 15 | 0.000 |
| okno 24 h, tło 56 dni, min. 1 spraw, premia 1.0, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 52 | 8 | 15% | 5 z 31 | 6 | 12 | 0.023 |
| okno 24 h, tło 56 dni, min. 2 spraw, premia 1.0, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 100 | 14 | 14% | 10 z 99 | 11 | 15 | 0.000 |
| okno 24 h, tło 56 dni, min. 2 spraw, premia 1.0, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 52 | 8 | 15% | 5 z 31 | 6 | 12 | 0.023 |
| okno 24 h, tło 56 dni, min. 3 spraw, premia 1.0, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 100 | 14 | 14% | 10 z 99 | 11 | 15 | 0.000 |
| okno 24 h, tło 56 dni, min. 3 spraw, premia 1.0, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 52 | 8 | 15% | 5 z 31 | 6 | 12 | 0.023 |
| okno 24 h, tło 56 dni, min. 1 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 94 | 13 | 14% | 9 z 99 | 10 | 14 | 0.000 |
| okno 24 h, tło 56 dni, min. 1 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 51 | 8 | 16% | 5 z 31 | 6 | 12 | 0.023 |
| okno 24 h, tło 56 dni, min. 2 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 94 | 13 | 14% | 9 z 99 | 10 | 14 | 0.000 |
| okno 24 h, tło 56 dni, min. 2 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 51 | 8 | 16% | 5 z 31 | 6 | 12 | 0.023 |
| okno 24 h, tło 56 dni, min. 3 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 94 | 13 | 14% | 9 z 99 | 10 | 14 | 0.000 |
| okno 24 h, tło 56 dni, min. 3 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 51 | 8 | 16% | 5 z 31 | 6 | 12 | 0.023 |
| okno 24 h, tło 56 dni, min. 1 spraw, premia 0.0, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 89 | 12 | 13% | 9 z 99 | 10 | 13 | 0.001 |
| okno 24 h, tło 56 dni, min. 1 spraw, premia 0.0, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 47 | 8 | 17% | 5 z 31 | 6 | 12 | 0.016 |
| okno 24 h, tło 56 dni, min. 2 spraw, premia 0.0, artykuły ×1.0, 1 dzień, próg 8 | 2019–2024 | 89 | 12 | 13% | 9 z 99 | 10 | 13 | 0.001 |
| okno 24 h, tło 56 dni, min. 2 spraw, premia 0.0, artykuły ×1.0, 1 dzień, próg 8 | 2025–2026 | 47 | 8 | 17% | 5 z 31 | 6 | 12 | 0.016 |
| **obecny** okno 48 h, tło 28 dni, min. 2 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 10 | 2019–2024 | 77 | 10 | 13% | 6 z 99 | 8 | 10 | 0.002 |
| **obecny** okno 48 h, tło 28 dni, min. 2 spraw, premia 0.5, artykuły ×1.0, 1 dzień, próg 10 | 2025–2026 | 46 | 8 | 17% | 3 z 31 | 4 | 10 | 0.006 |

## Obecny wariant przy różnych progach

| próg | okres | epizodów | precyzja | złapane ≤7 dni |
|---|---|---|---|---|
| 6 | 2019–2024 | 382 | 7% | 14 |
| 6 | 2025–2026 | 133 | 8% | 8 |
| 8 | 2019–2024 | 146 | 10% | 10 |
| 8 | 2025–2026 | 66 | 12% | 6 |
| 10 | 2019–2024 | 77 | 13% | 8 |
| 10 | 2025–2026 | 46 | 17% | 4 |
| 12 | 2019–2024 | 48 | 17% | 6 |
| 12 | 2025–2026 | 33 | 24% | 4 |
| 15 | 2019–2024 | 32 | 16% | 5 |
| 15 | 2025–2026 | 20 | 40% | 3 |

## Co napędza impulsy (obecny wariant, próg 6, kanał dominujący w oknie)

| kanał | okres | epizodów | trafnych | precyzja |
|---|---|---|---|---|
| sankcje | 2019–2024 | 188 | 11 | 6% |
| ambasady | 2019–2024 | 74 | 4 | 5% |
| loty | 2019–2024 | 61 | 2 | 3% |
| firmy | 2019–2024 | 42 | 6 | 14% |
| statki | 2019–2024 | 10 | 2 | 20% |
| waluta | 2019–2024 | 3 | 0 | 0% |
| energia | 2019–2024 | 2 | 0 | 0% |
| finanse | 2019–2024 | 2 | 0 | 0% |
| sankcje | 2025–2026 | 63 | 3 | 5% |
| loty | 2025–2026 | 27 | 2 | 7% |
| ambasady | 2025–2026 | 21 | 6 | 29% |
| firmy | 2025–2026 | 14 | 0 | 0% |
| statki | 2025–2026 | 6 | 0 | 0% |
| finanse | 2025–2026 | 2 | 0 | 0% |

Daty wydarzeń są przybliżone, więc wyprzedzenie 1–3 dni bywa niepewne. To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna.
