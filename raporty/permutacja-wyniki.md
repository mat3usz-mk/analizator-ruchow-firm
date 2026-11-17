# Test permutacyjny alarmów (2026-11-17)

Alarmy: początki epizodów reguły łączonej (model + ręczny indeks), raporty/epizody.json. Trafny alarm: wydarzenie w tym kraju w ciągu 60 dni. Losowań: 2000. Przesunięcie: wydarzenia dostają losowe daty w tym samym okresie. Zamiana: wydarzenia losowo zamieniają się krajami. Wartość p: odsetek losowań co najmniej tak dobrych jak rzeczywistość (mniej niż 5% = wynik raczej nieprzypadkowy).

| okres | alarmów | trafnych naprawdę | trafnych losowo (przesunięcie) | p | trafnych losowo (zamiana krajów) | p |
|---|---|---|---|---|---|---|
| 2019–2024 | 635 | 34 (5%) | 30.3 | 0.229 | 28.6 | 0.119 |
| 2025–2026 (test) | 183 | 14 (8%) | 10.3 | 0.108 | 15.2 | 0.769 |

Jak czytać: „przesunięcie” sprawdza, czy alarmy trafiają w czas, a nie tylko w kraje, w których często coś się dzieje. „Zamiana” sprawdza, czy trafiają we właściwy kraj, a nie tylko w okresy, gdy na świecie jest dużo wydarzeń. To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna.
