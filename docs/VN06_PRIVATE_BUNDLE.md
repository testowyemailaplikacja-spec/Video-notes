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

## Uruchomienie i test

Na fizycznym komputerze Windows, po skopiowaniu katalogu i odcięciu sieci, uruchom START-VIDEO-NOTES.cmd. Skrypt ustawia PATH na lokalny katalog bin i wskazuje domyślny model, więc użytkownik nie musi instalować osobnego Pythona ani szukać modelu ręcznie. Następnie trzeba wykonać rzeczywisty test transkrypcji MP4/MKV, eksportu i mikrofonu; samo uruchomienie GUI NIE potwierdza, że cały pakiet działa.

## Ograniczenia bezpieczeństwa i odbioru

To testowa, NIEPODPISANA paczka lokalna, a nie instalator .exe/.msi ani wydanie użytkowe. Kod sprawdza SHA-256 skopiowanych danych, ale nie poświadcza zgodności wersji bibliotek, integralności pochodzenia plików zewnętrznych ani licencji. Z tego powodu manifest jawnie oznacza license_verified=false, signature_verified=false, hardware_tested=false. Nie wolno rozpowszechniać bez dalszej kontroli i praw do redystrybucji.

Automatyczne tests/test_bundle.py korzystają z syntetycznych plików i nie testują rzeczywistego modelu Whisper. Dalsze bramki: prawdziwe ASR PL/EN, instalacja bez sieci na czystym Windows, logi AV/SmartScreen, ocena prawna/licencji, odtwarzanie po błędzie, testy długich nagrań oraz podpisywanie wydania.
