# Reddit: nastroje wprost i odwrotnie (2026-11-18)

Dane: kopia Reddita (paczki „top 40k subreddits” do końca 2024 r. albo archiwum Arctic Shift), dzienne liczby wpisów ze słowem w tytule. Skok: co najmniej 3× mediana z 28 dni. Trafny alarm: wydarzenie w tym kraju w ciągu 60 dni. p (przesunięcie): odsetek losowań z losowymi datami wydarzeń, w których wynik był co najmniej tak dobry; dla „odwrotnie” liczy się, czy wynik jest wyraźnie GORSZY od losowego (p odwrotnie małe).

## A. Uwaga o kraju (r/worldnews; kraje z wydarzeniami od 2019 r.)

Skok sam jako alarm:

| subreddit | okres | epizodów | precyzja | przewaga nad losowym | p wprost | p odwrotnie |
|---|---|---|---|---|---|---|
| r/worldnews | 2019–2021 | 1221 | 5% | 1.5× | 0.160 | 0.882 |
| r/worldnews | 2022–2024 | 1116 | 5% | 1.3× | 0.146 | 0.885 |

Bramka dla alarmów ręcznego indeksu (próg 40, wydarzenie w 60 dni):

| okres | wariant | trafione wydarzenia | z zaskoczenia | precyzja | prawdziwe alarmy | fałszywe alarmy |
|---|---|---|---|---|---|---|
| 2019–2021 | bez Reddita | 39% | 17% | 10% | 43 | 392 |
| 2019–2021 | wprost: alarm tylko przy skoku na Reddicie w 14 dniach | 27% | 14% | 13% | 33 | 226 |
| 2019–2021 | odwrotnie: alarm tylko BEZ skoku na Reddicie w 14 dniach | 31% | 18% | 7% | 21 | 298 |
| 2022–2024 | bez Reddita | 57% | 43% | 8% | 48 | 529 |
| 2022–2024 | wprost: alarm tylko przy skoku na Reddicie w 14 dniach | 34% | 26% | 13% | 36 | 239 |
| 2022–2024 | odwrotnie: alarm tylko BEZ skoku na Reddicie w 14 dniach | 45% | 41% | 6% | 26 | 416 |

Silny impuls 48 h a Reddit:

| okres | wariant | impulsów | trafnych | p (przesunięcie) |
|---|---|---|---|---|
| 2019–2021 | impuls ≥ 10 (wszystkie) | 28 | 3 (11%) | 0.591 |
| 2019–2021 | impuls ≥ 10 i skok na Reddicie w 3 dniach | 18 | 2 (11%) | 0.635 |
| 2019–2021 | impuls ≥ 10 bez skoku na Reddicie | 10 | 1 (10%) | 0.638 |
| 2022–2024 | impuls ≥ 10 (wszystkie) | 47 | 12 (26%) | 0.005 |
| 2022–2024 | impuls ≥ 10 i skok na Reddicie w 3 dniach | 29 | 9 (31%) | 0.005 |
| 2022–2024 | impuls ≥ 10 bez skoku na Reddicie | 18 | 3 (17%) | 0.211 |

## B. Giełda (r/wallstreetbets)

Kurs ETF 30 dni od dnia po skoku wzmianek, wobec zwykłego dnia. p wprost: czy po skoku kurs rośnie bardziej niż zwykle; p odwrotnie: czy spada bardziej niż zwykle (1000 losowań tylu samo zwykłych dni).

| wzmianki | skoków | kurs po skoku | zwykle | różnica | w górę po skoku | w górę zwykle | p wprost | p odwrotnie |
|---|---|---|---|---|---|---|---|---|
| ropa (XLE) | 135 | +2,8% | +1,0% | +1,8% | 53% | 54% | 0.024 | 0.976 |
| złoto (GLD) | 127 | +0,5% | +1,1% | -0,6% | 56% | 58% | 0.949 | 0.051 |
| zbrojeniówka (ITA) | 1 | +3,5% | +0,9% | +2,7% | 100% | 60% | 0.308 | 0.692 |
| Chiny (FXI) | 179 | +0,4% | -0,2% | +0,6% | 50% | 46% | 0.143 | 0.857 |
| Tajwan (EWT) | 11 | -0,1% | +0,9% | -1,0% | 45% | 59% | 0.724 | 0.276 |
| strach na WSB: puts ≥ 2× calls (SPY) | 219 | +2,5% | +1,2% | +1,3% | 71% | 70% | 0.000 | 1.000 |

Odporność (epizody bez nachodzenia: po skoku 30 dni przerwy; różnica wobec zwykłego dnia):

| wzmianki | epizodów | różnica | p wprost | p odwrotnie | bez 2020 r. | w kolejnych latach (epizody: różnica) |
|---|---|---|---|---|---|---|
| ropa (XLE) | 29 | -3,1% | 0.948 | 0.052 | -0,9% | 2019 (1: -6,9%), 2020 (6: -11,1%), 2021 (7: -2,5%), 2022 (9: +0,5%), 2023 (3: -5,9%), 2024 (3: -2,6%) |
| złoto (GLD) | 33 | +0,1% | 0.454 | 0.546 | +0,1% | 2019 (3: -1,7%), 2020 (8: -0,0%), 2021 (6: +0,9%), 2022 (6: +1,7%), 2023 (5: +0,0%), 2024 (5: -1,4%) |
| zbrojeniówka (ITA) | 1 | +2,7% | 0.280 | 0.720 | +2,4% | 2022 (1: +2,7%) |
| Chiny (FXI) | 42 | -0,3% | 0.576 | 0.424 | +0,2% | 2019 (7: +0,2%), 2020 (6: -2,4%), 2021 (8: +0,3%), 2022 (7: -0,7%), 2023 (8: +0,4%), 2024 (6: +1,6%) |
| Tajwan (EWT) | 5 | +0,9% | 0.391 | 0.609 | +1,3% | 2021 (1: +6,5%), 2022 (2: +0,9%), 2024 (2: +0,6%) |
| strach na WSB: puts ≥ 2× calls (SPY) | 39 | -0,6% | 0.787 | 0.213 | -0,5% | 2019 (5: +1,1%), 2020 (3: -0,3%), 2021 (4: +2,3%), 2022 (11: -1,1%), 2023 (10: -0,7%), 2024 (6: -0,8%) |

Uwaga: kolejne dni na giełdzie nie są niezależne (okna 30 dni nachodzą na siebie), więc p dla giełdy jest raczej zbyt optymistyczne. X/Twitter pominięty: brak darmowego dostępu do archiwum (API płatne, Nitter wyłączony). Reddit bez archiwum Arctic Shift nie daje historii (Pushshift zamknięty, PullPush blokuje automaty). To test historyczny, nie gwarancja i nie rekomendacja inwestycyjna.
