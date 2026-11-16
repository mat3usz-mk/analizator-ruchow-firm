# Model uczony na historii (2026-11-16)

Uczenie: 2015-05-01..2024-12-31, test (model go nie widział): 2025-03-01..2026-11-16. Horyzont: wydarzenie w ciągu 60 dni. Dane: historia_gkg.db.

| | uczenie | **test** |
|---|---|---|
| wiersze (kraj × tydzień) | 16992 | 5262 |
| z wydarzeniem w horyzoncie | 693 (4%) | 225 (4%) |
| AUC ręczny indeks | 0.55 | 0.65 |
| **AUC model** | 0.66 | **0.70** |
| AUC ręczny, tylko kraje bez wydarzenia w ostatnich 90 dniach | 0.55 | 0.64 |
| **AUC model, tylko kraje bez wydarzenia w ostatnich 90 dniach** | 0.65 | **0.69** |
| Brier model / stała częstość (niżej = lepiej) | 0.0382 / 0.0391 | 0.0397 / 0.0409 |

AUC: 0,5 = losowo, 1,0 = idealnie. Mówi, czy kraje przed wydarzeniem dostają wyższą ocenę niż pozostałe.

## Wydarzenia w teście (ręczny indeks przy progu 40 kontra model przy progu dającym tyle samo alarmów, 6%)

| | ręczny | model |
|---|---|---|
| trafione wydarzenia | 68% | 58% |
| trafione z zaskoczenia | 69% | 35% |
| trafne alarmy (precyzja) | 18% | 19% |
| mediana wyprzedzenia (dni) | 47 | 49 |

## Kalibracja na teście (czy „20%” znaczy 20%)

| szansa wg modelu | tygodni | średnio przewidziane | naprawdę z wydarzeniem |
|---|---|---|---|
| 0%–5% | 4466 | 3.2% | 3.0% |
| 5%–10% | 537 | 6.8% | 9.3% |
| 10%–20% | 228 | 13.4% | 15.8% |
| 20%–30% | 26 | 23.8% | 23.1% |
| 30%–50% | 5 | 39.4% | 20.0% |

## Czego model się nauczył (wagi po standaryzacji, największe pierwsze)

Dodatnia waga: cecha podnosi szansę wydarzenia. Ujemna: obniża ją (często szum).

- liczba państw: +0.21
- siła sygnałów w tygodniu: +0.18
- kategoria: sankcje: +0.13
- więcej typów ruchów niż zwykle: -0.12
- kategoria: wstrzymane_inwestycje: -0.09
- kategoria: energia_surowce: +0.06
- kategoria: ubezpieczenia_finanse: +0.06
- odchylenie od normy kraju: -0.05
- kategoria: ewakuacja_personelu: +0.05
- więcej różnych firm i państw niż zwykle: -0.05
- udział ruchów wyprzedzających: -0.05
- kategoria: lancuch_dostaw: +0.05
- liczba sygnałów priorytetowych: +0.04
- kategoria: sprzedaz_aktywow: -0.04
- sygnały priorytetowe ponad normę: +0.03

Model to wskazówka, nie wyrocznia: wydarzeń jest mało, a lista wydarzeń 2015–2024 była spisana z wiedzy ogólnej.
Nie jest to rekomendacja inwestycyjna.
