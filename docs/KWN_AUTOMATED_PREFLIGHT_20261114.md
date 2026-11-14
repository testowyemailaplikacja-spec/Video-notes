# KWN — programistyczna redukcja bramek VN-00/01/06/07 (14.11.2026)

## VN-00 i VN-01: kompletność lokalnych próbek

Uruchom lokalnie, z własnym nagraniem PL i EN oraz ręcznie sprawdzoną referencją TXT:

~~~powershell
python scripts/asr_samples_preflight.py --pl-media "C:\KWN\pl.mkv" --pl-reference "C:\KWN\pl.txt" --en-media "C:\KWN\en.mkv" --en-reference "C:\KWN\en.txt"
~~~

Skrypt weryfikuje źródło, obecność strumieni audio za pomocą FFprobe, format referencji, oznaczenie języka, SHA-256 źródeł i brak równoległej zmiany plików. Raport celowo **nie** zawiera ścieżek, tekstów i nazw plików. Nie ustala legalności nagrania, nie rozpoznaje naturalności mowy i nie porównuje jeszcze modeli. Po preflighcie należy osobno wykonać istniejące `benchmark-real` na prawdziwych whisper.cpp oraz faster-whisper i zatwierdzić referencje odsłuchem. Nie przesyłać prywatnych plików do CI.

## VN-00 i VN-02: szersza diagnostyka GGUF

`python -m videonotes doctor --gguf-model ...` korzysta teraz z rzeczywistego odczytu 24-bajtowego nagłówka GGUF v2/v3: wersja, niezerowa liczba tensorów, limit meta/długości. Nie uznaje samego podpisu czterech bajtów `GGUF` za wystarczający. Poprawny nagłówek nie potwierdza zgodności wag, licencji, wykonania przez llama-cli ani poprawności semantycznej.

## VN-06: wstępny przegląd licencji FFmpeg

~~~powershell
python scripts/ffmpeg_license_preflight.py --ffmpeg "C:\KWN\ffmpeg.exe"
~~~

Wynik wypisuje tylko SHA-256 konkretnego binarium oraz trzy kluczowe flagi kompilacji (`--enable-gpl`, `--enable-nonfree`, `--enable-version3`), o ile są obecne w `ffmpeg -buildconf`. Nie wypisuje konfiguracji ścieżek i nie nadaje uprawnienia do dystrybucji: `license_verified=false`, `redistribution_authorized=false`. Osoba uprawniona musi ocenić pełny zestaw kodeków, bibliotek, źródeł, wymaganych not licencyjnych i dokładny model przed wydaniem.

## VN-07: sieciowy podtest przeglądarki

`scripts/browser-smoke.cjs` aktywuje `Network.enable` w CDP dla strony `file://` i odrzuca każdy zarejestrowany wywołany z niej adres HTTP(S). Dotychczasowy test `performance.getEntriesByType` badał tylko ujawnione zasoby; nowy sprawdza także nieudane próby połączeń podczas testowanej sesji. To **nie** jest analiza wszystkich kanałów systemowych i nie zastępuje ręcznego NVDA, Windows ani przeglądu bezpieczeństwa hosta Wiedora. Prawdziwe Chrome/Edge/Chromium w CI są używane wyłącznie dla izolowanego adaptera KWN.

## CI

Domyślny workflow Linux pełne `unittest discover` oraz Windows jawna lista modułów obejmują teraz także testy: GGUF, mobilny import i poprawki, FFmpeg flag preflight, PL/EN input manifest. Faktyczne wyniki CI należy zweryfikować na ostatnim commicie PR, przed merge.

**Braki odbioru:** naturalne nagrania PL/EN, WER/CER i porównanie realnych silników na docelowym CPU, fizyczny Windows, GGUF z ręcznym zatwierdzeniem twierdzeń, prawa dystrybucji, test NVDA i pełna integracja hosta. Żadna nowa funkcja nie uzyskuje w tym pakiecie fizycznego PASS.
