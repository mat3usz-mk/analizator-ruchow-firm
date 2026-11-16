# Analizator ruchów dużych firm (v0.3)

Narzędzie zbiera mało nagłaśniane wiadomości o decyzjach firm w konkretnych krajach
(ewakuacje personelu, wyjścia z rynku, sprzedaż aktywów, wycofywanie ubezpieczeń,
wstrzymane dostawy, ruchy w energetyce) i pokazuje, **gdzie te ruchy nietypowo
się zagęszczają**. Wynik to wskazówka, gdzie się przyjrzeć, a nie prognoza.

## Szybki start

Wymaga tylko Pythona 3.10+ (bez dodatkowych bibliotek).

```bash
python -m analizator demo                 # dane syntetyczne, działa bez internetu
python -m analizator run --days 30        # pobierz prawdziwe wiadomości i zrób raport.html
python -m unittest discover -s tests -t . # testy
```

Najlepiej uruchamiać `run` codziennie (np. Harmonogram zadań w Windows albo cron).
Baza `analizator.db` rośnie z każdym dniem i daje coraz lepsze tło do porównań:
po ~2 miesiącach wyniki mają sens, po pół roku są dużo stabilniejsze.

Opcjonalnie:
- `watchlist.txt`: firmy do śledzenia, po jednej w wierszu (np. Gazprom, Shell, Maersk).
  Pomaga poprawnie przypisać nagłówek do firmy.
- `feeds.txt`: własne kanały RSS, np. komunikaty giełdowe (ESPI/EBI przez portale), portale branżowe.
- Zmienna środowiskowa `SEC_USER_AGENT="Imię Nazwisko adres@email"` (albo plik `config.json` z kluczem
  `sec_user_agent`): włącza raporty 8-K/6-K w SEC. SEC wymaga, by automat się przedstawił.

## Jak to działa

### 1. Źródła (darmowe, bez kluczy)
| Źródło | Co daje | Ograniczenia |
|---|---|---|
| GDELT DOC 2.0 | globalny indeks wiadomości, ~65 języków, także lokalna prasa | tylko ostatnie ~90 dni, limit 1 zapytanie / 5 s |
| Google News RSS | szybki przegląd EN i PL | ok. 100 wyników na zapytanie |
| SEC EDGAR (pełnotekstowe) | oficjalne raporty spółek notowanych w USA: "suspend operations", "impairment", "force majeure" | tylko spółki z USA i notowane w USA |
| Własne RSS | komunikaty giełdowe, branżówki | trzeba dodać adresy |

Warte dodania później (część płatna): komunikaty giełd europejskich (ESPI, LSE RNS),
dane AIS o ruchu statków i tankowców, NOTAM-y i zawieszenia lotów, ostrzeżenia MSZ
dla podróżnych, raporty o poziomie magazynów gazu (AGSI+ od GIE, darmowe), aukcje
przepustowości gazociągów (ENTSOG, darmowe).

### 2. Rozpoznanie sygnału (`signals.py`)
Każdy nagłówek przechodzi przez reguły w EN i PL. Wynik: kategoria ruchu, kraj, firma.
Reguły są przejrzyste, więc przy każdym alarmie widać, jaki tekst go wywołał.
Zaprzeczenia ("denies", "no plans to", "wznawia") osłabiają sygnał.

| Kategoria | Waga | Przykład |
|---|---|---|
| Ewakuacja / relokacja personelu | 4 | "evacuates non-essential staff from …" |
| Wyjście z rynku / zawieszenie | 3 | "suspends operations in …" |
| Ubezpieczenia / ekspozycja | 3 | "insurers cancel war risk cover …" |
| Sprzedaż aktywów / odpisy | 2 | "sells stake in … unit" |
| Łańcuch dostaw | 2 | "halts shipments to …, force majeure" |
| Energia i surowce | 2 | "did not book additional transit capacity" |

**Co odróżnia mocny sygnał od szumu (v0.2):**
- **Ruch wyprzedzający vs reakcja.** "Firma ewakuuje ludzi" bez widocznego powodu to sygnał. "Lotnisko wstrzymało pracę
  po ataku dronów" opisuje to, co już się dzieje, więc waży ok. 3 razy mniej.
- **Cichy sygnał.** Ruch wyprzedzający opisany tylko przez 1–2 wiarygodne źródła (często prasa branżowa: żegluga,
  ubezpieczenia, energia). Dostaje premię, bo tego właśnie nie ma w mediach masowych.
- **Wiarygodność źródła.** Raporty SEC > agencje i prasa biznesowa/branżowa > reszta > agregatory.
- **Kraj docelowy.** "Poland's Orlen cancels Qatar LNG deal" dotyczy Kataru, nie Polski.
- **Aktor.** Firmy, państwa (ambasady, ostrzeżenia) i nieznani aktorzy liczą się osobno.
- **Filtr szumu.** Sport, kultura, wybory, zaprzeczenia ("nie wycofuje się") są odrzucane lub osłabiane.
- **Łączenie historii.** Nagłówki o tym samym wydarzeniu z wielu portali to jedna historia.

### 3. Korelacje i ocena (`score.py`)
- **Jeden ruch = jedna decyzja.** 30 artykułów o tym, że jedna firma wychodzi z kraju,
  liczy się jako jeden ruch w tygodniu, nie trzydzieści.
- **Nietypowość, nie liczba.** Ostatnie 3 tygodnie porównujemy z tłem z poprzednich
  tygodni dla tego samego kraju. O Rosji pisze się zawsze dużo, więc liczy się zmiana.
- **Szerokość.** Wiele różnych firm i różnych typów decyzji naraz (ewakuacja + ubezpieczyciele
  + dostawy) waży dużo więcej niż jedna głośna historia.
- **Kara za koncentrację.** Jeśli większość sygnału pochodzi od jednej firmy, indeks spada.
- **Ruchy występujące razem.** Raport pokazuje, które typy decyzji pojawiają się w kraju jednocześnie.

### 4. Wynik i niepewność
Raport HTML (`raport.html`) i CSV. Dla każdego kraju: indeks 0–100, poziom
(niski / podwyższony / wysoki), **pewność danych** (ile tygodni tła i ile sygnałów),
wykres tygodniowy oraz lista dowodów z linkami.

### 5. Możliwe skutki (`skutki.py`)
Dla krajów z podwyższonym poziomem raport pokazuje hipotezy: jaką rolę gra kraj w gospodarce (eksporter energii,
wąskie gardło żeglugi, chipy, zboża, flanka NATO…), jakie branże i spółki zwykle zyskują lub tracą przy eskalacji,
jakie decyzje państw są typowe (sankcje, embargo, pułapy cen, dopłaty, ulgi, wydatki na obronę) oraz które firmy
z dowodów mają ekspozycję. To baza typowych reakcji z przeszłości, **nie rekomendacja inwestycyjna**: rynek mógł już
to wycenić.

### 6. Codzienny przegląd AI
Każde uruchomienie zapisuje `kandydaci.json` (najważniejsze kraje i dowody). Codzienne zadanie w chmurze uruchamia
Claude'a, który czyta kandydatów, odrzuca fałszywe trafienia, szuka powiązań między pozornie niezwiązanymi ruchami
(np. ubezpieczyciele + przekierowane tankowce + ostrzeżenia ambasad w jednym regionie), sprawdza najważniejsze
sygnały w wyszukiwarce i zapisuje `raporty/wnioski-RRRR-MM-DD.md`.

### 7. Test na danych historycznych
```bash
python -m analizator backfill --from 2025-01-01 --to 2026-11-14 --db historia.db   # długie: GDELT ma limit 1 zapytanie / 5 s
python -m analizator backtest --db historia.db --events wydarzenia.csv --from 2025-03-01 --to 2026-11-14
```
`backfill` pobiera historię oknami po 14 dni (da się przerwać i wznowić). `backtest` liczy oceny tydzień po
tygodniu **tylko z danych sprzed danego tygodnia** i porównuje je z `wydarzenia.csv` (data, kraj, opis, typ, źródło).
Wynik (`backtest.html`): odsetek trafionych wydarzeń, wyprzedzenie w dniach, fałszywe alarmy i tabela kalibracji
(przy jakim indeksie jak często coś się działo). Kalibracja to podstawa, żeby kiedyś mówić o prawdopodobieństwie.

Szybsza i pełniejsza historia GDELT (bez limitu API, ok. 65 min na 2 lata, wymaga domeny `data.gdeltproject.org`):
`python3 -m analizator.gdelt_pliki --from 2025-01-01 --to 2026-11-15 --db /tmp/h_gdelt_pliki.db` (surowe pliki GKG, zapisuje tylko tytuły z sygnałem).
Uwaga: pełne dane bez normalizacji dają stały alarm, wyniki w `raporty/backtest-v03-wnioski.md`.

### 8. Źródła pierwotne (v0.3, `pierwotne.py`)
Informacje u źródła, zanim trafią do artykułów. Działają „na żywo”, więc ich historia buduje się z każdym dniem.

| Źródło | Co daje | Domena do dozwolenia |
|---|---|---|
| ESPI/EBI | raporty bieżące spółek z GPW/NewConnect (w tym transakcje osób zarządzających, MAR) | www.stockwatch.pl |
| Ostrzeżenia USA | zmiana poziomu ostrzeżenia dla podróżnych (1–4) | travel.state.gov |
| Ostrzeżenia UK (FCDO) | „advises against all travel”, ewakuacje | www.gov.uk |
| EASA CZIB | nowe biuletyny o strefach konfliktu dla lotnictwa | www.easa.europa.eu |
| FAA | zmiany zakazów i NOTAM-ów dla przestrzeni powietrznej krajów | www.faa.gov |
| OFAC | nowe sankcje USA (Recent Actions) | ofac.treasury.gov |
| TED | skoki liczby przetargów obronnych (CPV 35*) w krajach UE i NATO | api.ted.europa.eu |
| OpenSky | spadek ruchu lotniczego nad krajem względem 14 dni | opensky-network.org |
| Form 4 | sprzedaż/zakup akcji przez insiderów spółek zbrojeniowych i energetycznych z USA (osobny panel) | www.sec.gov |
| AIS (aisstream.io) | ruch statków i tankowców przez Ormuz, Bab el-Mandeb, Suez, Cieśninę Tajwańską, Bosfor, Cieśniny Duńskie, porty Odessy; spadek o połowę względem 14 dni = sygnał | stream.aisstream.io + zmienna AISSTREAM_API_KEY |

Niedostępne za darmo albo wymagające klucza: NOTAM-y z API FAA (darmowy klucz), ogłoszenia o pracę i rejestry spółek (brak darmowych API),
zgłoszenia MAR w innych krajach UE (każdy nadzorca osobno).

### 9. Wyniki testu historycznego (v0.3, 31 wydarzeń 03.2025–11.2026, ocena codzienna)
| | v0.2 (bez SEC) | v0.3 |
|---|---|---|
| Trafione wydarzenia | 13% | 32% (10/31) |
| Trafne alarmy | 35% | 21% |
| Mediana wyprzedzenia | 10 dni | 24 dni |

Kalibracja v0.3: indeks 0–20 → wydarzenie w ciągu 60 dni w 4% dni, 40–60 → 15%, 80–100 → 17%.
Parametry strojone na 2025 r.; w 2026 r. (dane niewidziane przy strojeniu) trafione 6 z 11 wydarzeń.

### 10. Poprawki v0.4 (16.11.2026, po teście na nowych danych)
- Ewakuacja liczy się tylko, gdy dotyczy personelu, dyplomatów, obywateli lub ambasady; katastrofy naturalne, niewybuchy, epidemie i choroby zwierząt są pomijane.
- Rutynowe ostrzeżenia dla podróżnych mają 40% wagi; pełną tylko podwyższenia i „do not travel / leave immediately”.
- Wyjście z rynku i sprzedaż aktywów bez kontekstu bezpieczeństwa: 15% wagi (50% w branży wrażliwej).
- „amid … war”, „following attack”, „due to airspace closure” = sygnał w trakcie kryzysu (niska waga).
- Lotnictwo i ewakuacje z kontekstem napięć (bez reakcji na atak): waga ×1,25.
- Przedruki z tych samych 3 dni łączone łatwiej (podobieństwo słów od 0,2).
- Nadwyżka sygnałów priorytetowych, cichych i liczby kategorii liczona względem normy kraju (w odchyleniach), nie w sztukach.
- SEC: pomijane zdania warunkowe („may”, „could”, „risk”…) i zdania powtarzane przez tę samą spółkę.
- Wynik: na danych jak w codziennym zadaniu w 2026 r. trafione te same 6 z 11 wydarzeń, fałszywe alarmy 16 zamiast 25 (szczegóły: `raporty/backtest-v03-wnioski.md`, sekcja 7).
  Poprzednie wersje plików: `kopia-v0.3/`.

## Tryb ciągły, indeksy giełdowe i fronty (v0.5)

**Tryb ciągły** (`python -m analizator watch`). Co `--interval` minut (domyślnie 20) pobiera najszybsze źródła: GDELT i Google News
z ostatnich 2 dni oraz ostrzeżenia USA/UK, EASA, FAA, OFAC i OpenSky. Potem liczy indeksy i zapisuje `raport_biezacy.html`.
Powiadamia **tylko o zmianach**: kraj wchodzi na wyższy poziom, indeks powyżej 40 skacze o 15 punktów albo pojawia się nowy sygnał
priorytetowy (ewakuacja, ostrzeżenie rządu, lotnictwo, źródło pierwotne) z ostatnich 2 dni. Pierwszy cykl niczego nie zgłasza,
tylko ustala punkt odniesienia. Powiadomienia trafiają do `alerty.log` obok bazy, na ekran i na telefon przez
[ntfy.sh](https://ntfy.sh): wystarczy zainstalować darmową aplikację ntfy, zasubskrybować trudny do zgadnięcia temat
i podać go w `--ntfy` albo w zmiennej `NTFY_TOPIC`. Tryb ciągły nie używa AI, więc nie zużywa limitu Claude.

```
python -m analizator watch --db analizator.db --interval 20            # pętla (serwer, komputer włączony stale)
python -m analizator watch --db analizator.db --once                   # jeden cykl (cron: */20 * * * *)
```

**Indeksy giełdowe.** Przy każdym kraju o podwyższonym poziomie raport podaje konkretne indeksy i notowania, które przy eskalacji
**typowo** rosną (np. ropa Brent i WTI, gaz TTF, STOXX Europe 600 Oil & Gas, indeksy obronne, złoto, VIX) i spadają
(lokalna giełda: WIG20, TAIEX, TA-35, BIST 100, Tadawul…; sektory: STOXX 600 Travel & Leisure, Chemicals, Retail, PHLX Semiconductor…).
Te same listy są w CSV (`indeksy_w_gore`, `indeksy_w_dol`) i w `kandydaci.json`. To kierunki z podobnych sytuacji w przeszłości
(Krym 2014, Ukraina 2022, Morze Czerwone 2023–24, Ormuz, manewry wokół Tajwanu), a nie prognoza ceny ani rekomendacja inwestycyjna.
Rynek mógł już wycenić ryzyko.

**Fronty.** Jeden kryzys bywa rozbity na kilka krajów (np. Zatoka Perska, Morze Czerwone, wschodnia flanka NATO, Tajwan).
Na górze raportu jest zestawienie frontów, w których co najmniej dwa kraje mają indeks od 25 w górę albo sygnały priorytetowe.
Jest też w pliku `fronty.json`. Indeksy krajów liczone są osobno, bo przenoszenie ryzyka na sąsiadów pogarszało precyzję w teście.

**ESPI.** Najpierw kanał RSS Bankiera (`www.bankier.pl/rss/espi.xml`, trzeba dodać domenę `www.bankier.pl` w środowisku),
potem stockwatch.pl, który odrzuca automaty (403). **Sieć:** host zablokowany przez sieć środowiska nie jest już ponawiany.
**Baza:** zawsze praca na lokalnej kopii, ścieżki bezwzględne liczone na starcie (poprawka błędu `kandydaci.json` z 16.11).

## Model uczony na historii (v0.6)

Zamiast samych ręcznie dobranych wag analizator może używać modelu (regresja logistyczna w czystym Pythonie, `analizator/ucz.py`),
który uczy się na latach 2015–2024, które składowe oceny kraju naprawdę poprzedzały wydarzenia. Daje **szansę wydarzenia w kraju
w ciągu 60 dni** z kalibracją sprawdzoną na latach 2025–2026, których model nie widzi przy uczeniu.

- Wydarzenia do uczenia: `wydarzenia_2015_2024.csv` (ok. 150, spisane z wiedzy ogólnej z linkami do Wikipedii). Test: `wydarzenia.csv`.
- Historia wiadomości: pliki GDELT GKG (próbka: jeden plik na godzinę), pobierane równolegle rok po roku przez workflow
  „Historia i uczenie modelu” (GitHub Actions, uruchamiany ręcznie). Wynik trafia do `analizator/model.json`
  i `raporty/model-wyniki.md` (AUC, trafienia, precyzja i kalibracja: model kontra ręczny indeks na tych samych danych).
- Gdy `analizator/model.json` istnieje, raport pokazuje przy kraju „szansa wydarzenia w 60 dni wg modelu”. Bez pliku działa jak dotąd.
- Ręcznie: `python -m analizator.ucz --db historia_gkg.db` (opcje: `--train-to`, `--test-from`, `--horizon`).

## Ograniczenia (ważne)
- **Indeks to nie prawdopodobieństwo.** Żeby mówić "X% szans na konflikt w 30 dni",
  trzeba skalibrować model na wielu historycznych przypadkach (i przypadkach, w których
  nic się nie stało). Tego jeszcze nie ma.
- **Efekt wiedzy po fakcie.** Przed 24.02.2022 część sygnałów była widoczna (wycofywanie
  ubezpieczeń lotniczych, linie zawieszające loty, ewakuacje ambasad i personelu,
  zachowanie Gazpromu przy magazynach w UE i rezerwacji przepustowości), ale wiele
  "oczywistych" wyjść firm nastąpiło dopiero po inwazji. Podobne sygnały pojawiały się
  też w sytuacjach, które nie skończyły się wojną. Fałszywe alarmy będą.
- **Reguły vs. język.** Reguły łapią typowe sformułowania. Mniej oczywiste przypadki
  (np. cicha zmiana dostawcy) wymagają warstwy AI, patrz niżej.
- **Źródła darmowe** pokrywają głównie media anglojęzyczne i duże serwisy.

## Następne kroki
1. **Walidacja historyczna:** zebrać dane z okresów przed znanymi wydarzeniami (Ukraina 2022,
   Górski Karabach 2020/2023, Izrael 10.2023, Morze Czerwone 12.2023) i okresów spokojnych,
   sprawdzić, ile tygodni wcześniej indeks rósł i ile było fałszywych alarmów. Dopiero
   wtedy można zamienić indeks w prawdopodobieństwo.
2. **Pełne teksty artykułów** zamiast samych nagłówków (wymaga dostępu do stron źródłowych).
3. **Dane twarde:** magazyny gazu (AGSI+), aukcje przepustowości (ENTSOG), ruch tankowców (AIS).
4. **Panel w przeglądarce** z historią i powiadomieniami.
