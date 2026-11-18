#!/usr/bin/env bash
# Stałe miejsce na pobrane dane: wydanie „dane” w repozytorium (bez terminu ważności).
# Trafiają tam tylko dane publiczne (GDELT, SEC, źródła pierwotne, liczniki Reddita, EIA, Wikipedia), nigdy ACLED.
#   bash .github/dane.sh pobierz plik.db ...   pobiera brakujące pliki (plik już obecny, np. z artefaktu, ma pierwszeństwo)
#   bash .github/dane.sh wyslij plik.db ...    odsyła pliki po przebiegu (skompresowane gzip)
# Wymaga GH_TOKEN i GH_REPO w środowisku.
set -u
cmd=$1; shift
for f in "$@"; do
  case "$f" in *acled*|*klucze*) echo "dane: $f pominięty (dane z kontem nie są publikowane)"; continue;; esac
  case $cmd in
    pobierz)
      if [ -s "$f" ]; then echo "dane: $f już jest"; continue; fi
      if gh release download dane -p "$f.gz" -O "$f.gz" --clobber 2>/dev/null; then
        gunzip -f "$f.gz" && echo "dane: $f z wydania ($(du -h "$f" | cut -f1))"
      else
        rm -f "$f.gz"; echo "dane: brak $f w wydaniu, zostanie pobrany od zera"
      fi;;
    wyslij)
      [ -s "$f" ] || { echo "dane: brak $f, nic do wysłania"; continue; }
      gzip -kf "$f"
      for i in 1 2 3; do gh release upload dane "$f.gz" --clobber && { echo "dane: $f zapisany w wydaniu"; break; }; sleep 10; done
      rm -f "$f.gz";;
  esac
done
exit 0
