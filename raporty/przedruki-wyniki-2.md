# Warianty parametrów: test historyczny (2026-11-17)

Ręczny indeks, próg alarmu 40, wydarzenie w ciągu 60 dni. „przedruk” = waga wzmianki o zdarzeniu starszym niż 7 dni (przedruk albo ponowny opis starej decyzji); 1,0 = jak dotąd.

## Lata 2019–2024 (wydarzenia z listy 2015–2024)

| wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy | mediana wyprzedzenia |
|---|---|---|---|---|---|---|
| przedruk=0.5 | 48% | 24% | 8% | 93 | 1054 | 44 dni |
| przedruk=0.15,przedruk_dni=14 | 48% | 27% | 8% | 92 | 1038 | 42 dni |
| przedruk=0.5,przedruk_dni=14 | 49% | 29% | 8% | 94 | 1048 | 42 dni |

## Test 2025-03 – 2026-11 (wydarzenia 2025–2026)

| wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy | mediana wyprzedzenia |
|---|---|---|---|---|---|---|
| przedruk=0.5 | 68% | 70% | 9% | 30 | 301 | 46 dni |
| przedruk=0.15,przedruk_dni=14 | 68% | 70% | 9% | 30 | 300 | 40 dni |
| przedruk=0.5,przedruk_dni=14 | 68% | 70% | 9% | 30 | 300 | 46 dni |

To test na danych historycznych, nie gwarancja i nie rekomendacja inwestycyjna.
