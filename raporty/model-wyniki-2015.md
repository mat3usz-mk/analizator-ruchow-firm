# Model uczony na historii (2026-11-17)

Uczenie: 2015-05-01..2024-12-31, test (model go nie widział): 2025-03-01..2026-11-17. Horyzont: wydarzenie w ciągu 60 dni. Dane: historia_gkg.db.

| | uczenie | **test** |
|---|---|---|
| wiersze (kraj × tydzień) | 31274 | 5346 |
| z wydarzeniem w horyzoncie | 1215 (4%) | 225 (4%) |
| AUC ręczny indeks | 0.57 | 0.64 |
| **AUC model** | 0.68 | **0.72** |
| AUC ręczny, tylko kraje bez wydarzenia w ostatnich 90 dniach | 0.57 | 0.63 |
| **AUC model, tylko kraje bez wydarzenia w ostatnich 90 dniach** | 0.69 | **0.73** |
| Brier model / stała częstość (niżej = lepiej) | 0.0364 / 0.0373 | 0.0389 / 0.0403 |

AUC: 0,5 = losowo, 1,0 = idealnie. Mówi, czy kraje przed wydarzeniem dostają wyższą ocenę niż pozostałe.

## Wydarzenia w teście (ręczny indeks przy progu 40 kontra model przy progu dającym tyle samo alarmów, 7%)

| | ręczny | model |
|---|---|---|
| trafione wydarzenia | 68% | 61% |
| trafione z zaskoczenia | 64% | 33% |
| trafne alarmy (precyzja) | 11% | 17% |
| mediana wyprzedzenia (dni) | 40 | 55 |

## Alarm z połączenia modelu i ręcznego indeksu (test)

Reguła (progi dobrane tylko na latach uczenia): alarm, gdy ręczny indeks ≥ 40 i model daje co najmniej 5.5%, albo gdy sam model daje co najmniej 10.0%.

| | ręczny | model | połączony |
|---|---|---|---|
| trafione wydarzenia | 68% | 61% | 74% |
| trafione z zaskoczenia | 64% | 33% | 55% |
| trafne alarmy (precyzja) | 11% | 17% | 13% |
| mediana wyprzedzenia (dni) | 40 | 55 | 51 |
| prawdziwe alarmy | 28 | 18 | 27 |
| fałszywe alarmy | 222 | 88 | 182 |

W raporcie na żywo **używana jest reguła połączona**.

## Kalibracja na teście (czy „20%” znaczy 20%)

| szansa wg modelu | tygodni | średnio przewidziane | naprawdę z wydarzeniem |
|---|---|---|---|
| 0%–5% | 3970 | 3.1% | 2.5% |
| 5%–10% | 923 | 6.7% | 6.9% |
| 10%–20% | 412 | 13.5% | 12.6% |
| 20%–30% | 40 | 22.9% | 25.0% |
| 30%–50% | 1 | 30.3% | 100.0% |

## Czego model się nauczył (wagi po standaryzacji, największe pierwsze)

Dodatnia waga: cecha podnosi szansę wydarzenia. Ujemna: obniża ją (często szum).

- siła sygnałów w tygodniu: +0.20
- liczba państw: +0.19
- kategoria: wyjscie_z_rynku: +0.15
- więcej typów ruchów niż zwykle: -0.13
- długość historii kraju: +0.12
- kategoria: sankcje: +0.12
- liczba firm: -0.10
- odchylenie od normy kraju: -0.08
- kategoria: energia_surowce: +0.06
- kategoria: lancuch_dostaw: +0.05
- udział ruchów wyprzedzających: +0.05
- kategoria: lotnictwo_przestrzen: +0.05
- kategoria: ewakuacja_personelu: +0.05
- jedna firma dominuje: -0.04
- kategoria: przeplywy_finansowe: -0.04

Model to wskazówka, nie wyrocznia: wydarzeń jest mało, a lista wydarzeń 2015–2024 była spisana z wiedzy ogólnej.
Nie jest to rekomendacja inwestycyjna.
