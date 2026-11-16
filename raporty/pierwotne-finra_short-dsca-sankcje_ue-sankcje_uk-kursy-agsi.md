# Źródła pierwotne kontra artykuły: test historyczny (2026-11-16)

Ręczny indeks, próg alarmu 40, wydarzenie w ciągu 60 dni. Źródła pierwotne w teście: finra_short (539 sygnałów), sankcje_ue (218 sygnałów), sankcje_uk (210 sygnałów), kursy (153 sygnałów), dsca (102 sygnałów), agsi (24 sygnałów).

Uwagi: listy sankcji zawierają tylko obowiązujące dziś wpisy (zdjęte z listy znikają z historii), IODA ma pełne dane dopiero od ok. 2022 r., a PortWatch od 2019 r. Artykuły to tytuły z GDELT od 2019 r.

## Lata 2022–2024 (wydarzenia z listy 2015–2024)

| wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy | mediana wyprzedzenia |
|---|---|---|---|---|---|---|
| A: tylko artykuły | 55% | 29% | 8% | 46 | 506 | 48 dni |
| B: artykuły + źródła pierwotne | 53% | 31% | 8% | 44 | 525 | 44 dni |
| C: jak B, artykuły z wagą 0,5 | 57% | 33% | 9% | 46 | 478 | 48 dni |
| D: jak B, artykuły z wagą 0,25 | 24% | 14% | 14% | 24 | 153 | 49 dni |
| E: tylko źródła pierwotne | 0% | 0% | 20% | 1 | 4 | brak |

## Test 2025-03 – 2026-11 (wydarzenia 2025–2026)

| wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy | mediana wyprzedzenia |
|---|---|---|---|---|---|---|
| A: tylko artykuły | 68% | 67% | 10% | 28 | 247 | 46 dni |
| B: artykuły + źródła pierwotne | 74% | 67% | 10% | 31 | 272 | 46 dni |
| C: jak B, artykuły z wagą 0,5 | 74% | 75% | 11% | 32 | 257 | 46 dni |
| D: jak B, artykuły z wagą 0,25 | 52% | 52% | 15% | 20 | 115 | 38 dni |
| E: tylko źródła pierwotne | 10% | 8% | 8% | 4 | 44 | 10 dni |

Precyzja = odsetek alarmów, po których w ciągu 60 dni nastąpiło wydarzenie. To test na danych historycznych, nie gwarancja.
Nie jest to rekomendacja inwestycyjna.
