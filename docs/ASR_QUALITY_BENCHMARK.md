# VN-00 — protokół porównania jakości ASR bez ujawniania nagrań

**Status 06.11.2026:** działa narzędzie WER/CER dla wcześniej przygotowanych plików TXT. Brak rzeczywistego benchmarku modeli Whisper, czasu CPU/RAM i danych PL/EN. Nie oznacza to wyboru silnika.

## Kroki na komputerze użytkownika

1. Przygotuj legalne, własne nagranie OBS PL (5–10 min), EN i trudny zaszumiony fragment. Przygotuj ręcznie sprawdzony transkrypt referencyjny (UTF-8 TXT) z dokładnie tym, co zostało wypowiedziane. Nie przesyłaj plików do publicznego GitHub.
2. Uruchom na tych samych plikach i warunkach sprzętu **whisper.cpp** oraz **faster-whisper** (oddzielnie, każdy z kompatybilnym modelem, ustalonym językiem, bez tłumaczenia). Zapisz transkrypty do dwóch lokalnych TXT. Ustalenie rzeczywistych wersji modelu i licencji jest odrębnym dowodem.
3. Porównaj gotowe pliki lokalnie:

       python -m videonotes benchmark --reference wzorzec.txt --candidate whisper_cpp=wynik_cpp.txt --candidate faster_whisper=wynik_faster.txt --output raport_wynikow.json

4. Raport zawiera znormalizowane WER (liczba operacji Levenshteina / liczba wyrazów referencyjnych) i CER bez spacji. Normalizacja: Unicode NFC, casefold, usunięte znaki interpunkcyjne. WER może przekroczyć 1 przy wielu wstawieniach.
5. Obok jakości osobno zmierz czas inferencji, szczyt pamięci RAM, CPU/GPU, rozmiar modeli, licencje i możliwość dołączenia do pełnego instalatora Windows offline. Dopiero po tych dowodach wybierz silnik produkcyjny.

## Granice danych

- Porównywarka **nie wykonuje ASR** i nie dowodzi, jaki silnik wygenerował podany TXT. Etykiety są deklarowane przez użytkownika (`engine_provenance_verified: false`).
- Raport JSON przechowuje tylko hashe SHA-256 plików, liczniki i wartości WER/CER, nigdy nagrania ani tekstu transkryptu. Dane pozostają lokalne.
- Liczba słów ograniczona do 6000 na pojedynczy plik (osobny fragment benchmarkowy); limit wejścia to 300 KB. Bardzo długie nagranie trzeba podzielić na referencyjnie wyrównane fragmenty, nie porównywać tekstów o innym zakresie.
- Program **nie mierzy czasu ani RAM**; `speed_measured: false` i `peak_ram_measured: false` w raporcie. Benchmark sprzętowy jest osobną, nieukończoną bramką VN-00.
