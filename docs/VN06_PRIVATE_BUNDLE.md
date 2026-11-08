# VN-06 — prywatny pakiet testowy Windows (NIE oficjalny instalator)

Data: 2026-11-06. Pakowanie wyłącznie z plików lokalnych, bez pobierania modeli i binariów z sieci, bez zmian w repozytorium Wiedora.

## Wymagania na komputerze budującym

- Testowy VideoNotes-DEV.exe z poprawnego przebiegu workflow GitHub Actions.
- Własne binaria Windows: ffmpeg.exe, ffprobe.exe, whisper-cli.exe.
- Model GGML dla whisper.cpp zgodny z wybranym whisper-cli, jako plik lokalny .bin.
- Oddzielna ocena licencji silnika, modelu oraz danej kompilacji FFmpeg PRZED jakąkolwiek dystrybucją.

Żadnego z tych zewnętrznych plików nie commitujemy do publicznego repo. Narzędzie nie pobiera i nie kupuje modelu.

## Złożenie lokalnego pakietu testowego

    python -m videonotes bundle-dev --app C:\staging\VideoNotes-DEV.exe --ffmpeg C:\tools\ffmpeg.exe --ffprobe C:\tools\ffprobe.exe --whisper C:\tools\whisper-cli.exe --model C:\models\ggml-base.bin --output C:\staging\VideoNotes-LOCAL-TEST --internal-only

Uwaga: to przykład. Ścieżki muszą odpowiadać rzeczywistym lokalnym plikom, a katalog wyjściowy musi nie istnieć.

Tworzone pliki: VideoNotes-DEV.exe, bin/ffmpeg.exe, bin/ffprobe.exe, bin/whisper-cli.exe, bin/model.bin, START-VIDEO-NOTES.cmd, INTERNAL-ONLY.txt oraz bundle-manifest.json. Manifest zawiera wyłącznie względne nazwy, rozmiary i SHA-256. Brak ścieżek źródłowych, nagrań i prywatnych danych.

## Kontrola integralności przed uruchomieniem

Po utworzeniu katalogu wykonaj lokalnie:

    python -m videonotes bundle-verify C:\staging\VideoNotes-LOCAL-TEST

W prywatnej paczce można również uruchomić:

    C:\staging\VideoNotes-LOCAL-TEST\VideoNotes-DEV.exe bundle-verify C:\staging\VideoNotes-LOCAL-TEST

Polecenie weryfikuje stały zestaw pięciu składników, SHA-256 i rozmiary z manifestu, brak dodatkowych plików i symlinków, format manifestu (włącznie z powielonymi kluczami) oraz niezmienione pliki startowe. `START-VIDEO-NOTES.cmd` uruchamia ten test automatycznie **przed** włączeniem GUI i odmawia startu po wykryciu różnicy. Testy działają lokalnie bez internetu.

**Uwaga:** sumy SHA-256 chronią przed przypadkowym uszkodzeniem, ale manifest i plik EXE nie są podpisane. Osoba mająca możliwość zamiany całego pakietu może podmienić jednocześnie manifest i program. `verified: true` oznacza jedynie spójność lokalną, **nie** zatwierdzenie licencji, pochodzenia, bezpieczeństwa lub gotowości dystrybucyjnej. Takie bramki pozostają otwarte.

## Uruchomienie i test

Na fizycznym komputerze Windows, po skopiowaniu katalogu i odcięciu sieci, uruchom START-VIDEO-NOTES.cmd. Skrypt ustawia PATH na lokalny katalog bin i wskazuje domyślny model, więc użytkownik nie musi instalować osobnego Pythona ani szukać modelu ręcznie. Następnie trzeba wykonać rzeczywisty test transkrypcji MP4/MKV, eksportu i mikrofonu; samo uruchomienie GUI NIE potwierdza, że cały pakiet działa.

## Ograniczenia bezpieczeństwa i odbioru

To testowa, NIEPODPISANA paczka lokalna, a nie instalator .exe/.msi ani wydanie użytkowe. Kod sprawdza SHA-256 skopiowanych danych i ponownie je weryfikuje przed startem, ale nie poświadcza zgodności wersji bibliotek, integralności pochodzenia plików zewnętrznych ani licencji. Z tego powodu manifest jawnie oznacza license_verified=false, signature_verified=false, hardware_tested=false. Nie wolno rozpowszechniać bez dalszej kontroli i praw do redystrybucji.

Automatyczne tests/test_bundle.py korzystają z syntetycznych plików i nie testują rzeczywistego modelu Whisper. Dalsze bramki: prawdziwe ASR PL/EN, instalacja bez sieci na czystym Windows, logi AV/SmartScreen, ocena prawna/licencji, odtwarzanie po błędzie, testy długich nagrań oraz podpisywanie wydania.

## Atomowe opublikowanie kompletnego katalogu bez nadpisania (07.11.2026)

Pakiet jest przygotowywany i weryfikowany w osobnym katalogu tymczasowym. Na Windows jego katalog wynikowy jest publikowany przez systemowe `rename`, które odmawia zastąpienia istniejącego katalogu. Na Linux używane jest `renameat2(RENAME_NOREPLACE)` zamiast zwykłego `os.rename`: to zapobiega przejęciu **pustego katalogu utworzonego przez drugi proces w ostatniej chwili**, już po wcześniejszym sprawdzeniu `exists()`. Gdy wymagany mechanizm nie jest dostępny, operacja kończy się odmową i sprzątnięciem katalogu tymczasowego; na innych platformach składanie pakietu z pełną gwarancją no-clobber nie jest obecnie udostępnione.

Regresja celowo symuluje równoległe utworzenie pustego katalogu docelowego tuż przed publikacją i sprawdza, że pozostaje pusty oraz żaden plik źródłowy nie został naruszony. Jest to ochrona przed kolizją zapisów, **nie** test rzeczywistego instalatora, podpisu ani kompatybilności/licencji FFmpeg i modelu.

## Spis składników SBOM do prywatnego pakietu (08.11.2026)

Dostępne jest polecenie `bundle-sbom`, które tworzy poza katalogiem pakietu dokument SPDX 2.3 z weryfikowanymi SHA-256 pięciu składników. Nie wymaga sieci ani dodatkowych bibliotek. Każda licencja ma status `NOASSERTION`, więc powstanie SBOM **nie** oznacza zatwierdzenia redystrybucji ani gotowości wydania. Instrukcja: [VN06_SBOM.md](VN06_SBOM.md).
