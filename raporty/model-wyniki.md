# Model uczony na historii (2026-11-16)

Uczenie: 2019-03-01..2024-12-31, test (model go nie widział): 2025-03-01..2026-11-16. Horyzont: wydarzenie w ciągu 60 dni. Dane: historia_gkg.db.

| | uczenie | **test** |
|---|---|---|
| wiersze (kraj × tydzień) | 17446 | 5346 |
| z wydarzeniem w horyzoncie | 698 (4%) | 225 (4%) |
| AUC ręczny indeks | 0.53 | 0.64 |
| **AUC model** | 0.66 | **0.73** |
| AUC ręczny, tylko kraje bez wydarzenia w ostatnich 90 dniach | 0.53 | 0.62 |
| **AUC model, tylko kraje bez wydarzenia w ostatnich 90 dniach** | 0.66 | **0.73** |
| Brier model / stała częstość (niżej = lepiej) | 0.0374 / 0.0384 | 0.0388 / 0.0403 |

AUC: 0,5 = losowo, 1,0 = idealnie. Mówi, czy kraje przed wydarzeniem dostają wyższą ocenę niż pozostałe.

## Wydarzenia w teście (ręczny indeks przy progu 40 kontra model przy progu dającym tyle samo alarmów, 6%)

| | ręczny | model |
|---|---|---|
| trafione wydarzenia | 68% | 61% |
| trafione z zaskoczenia | 67% | 35% |
| trafne alarmy (precyzja) | 11% | 17% |
| mediana wyprzedzenia (dni) | 44 | 54 |

## Alarm z połączenia modelu i ręcznego indeksu (test)

Reguła (progi dobrane tylko na latach uczenia): alarm, gdy ręczny indeks ≥ 40 i model daje co najmniej 4.0%, albo gdy sam model daje co najmniej 13.9%.

| | ręczny | model | połączony |
|---|---|---|---|
| trafione wydarzenia | 68% | 61% | 61% |
| trafione z zaskoczenia | 67% | 35% | 53% |
| trafne alarmy (precyzja) | 11% | 17% | 15% |
| mediana wyprzedzenia (dni) | 44 | 54 | 49 |
| prawdziwe alarmy | 29 | 18 | 23 |
| fałszywe alarmy | 229 | 91 | 131 |

W raporcie na żywo **używana jest reguła połączona**.

## Kalibracja na teście (czy „20%” znaczy 20%)

| szansa wg modelu | tygodni | średnio przewidziane | naprawdę z wydarzeniem |
|---|---|---|---|
| 0%–5% | 4338 | 3.0% | 2.7% |
| 5%–10% | 672 | 6.8% | 8.0% |
| 10%–20% | 313 | 13.4% | 14.4% |
| 20%–30% | 23 | 23.0% | 34.8% |

## Czego model się nauczył (wagi po standaryzacji, największe pierwsze)

Dodatnia waga: cecha podnosi szansę wydarzenia. Ujemna: obniża ją (często szum).

- liczba państw: +0.26
- siła sygnałów w tygodniu: +0.15
- odchylenie od normy kraju: -0.14
- więcej typów ruchów niż zwykle: -0.10
- kategoria: sankcje: +0.08
- kategoria: wyjscie_z_rynku: +0.08
- kategoria: energia_surowce: +0.08
- kategoria: lancuch_dostaw: +0.07
- kategoria: wstrzymane_inwestycje: -0.06
- kategoria: sprzedaz_aktywow: -0.05
- kategoria: ewakuacja_personelu: +0.05
- sygnały priorytetowe ponad normę: +0.03
- liczba sygnałów priorytetowych: +0.03
- kategoria: przeplywy_finansowe: -0.03
- jedna firma dominuje: -0.02

Model to wskazówka, nie wyrocznia: wydarzeń jest mało, a lista wydarzeń 2015–2024 była spisana z wiedzy ogólnej.
Nie jest to rekomendacja inwestycyjna.
