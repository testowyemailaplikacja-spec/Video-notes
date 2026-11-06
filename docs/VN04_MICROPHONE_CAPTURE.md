# VN-04 — lokalne nagrywanie mikrofonu Windows / DirectShow

Data: 2026-11-06. W tym repo, bez zmian w Wiedora/Constant_app i Netlify.

## Pierwsze uruchomienie

Program wymaga FFmpeg z obsługą DirectShow dostępnego lokalnie oraz urządzenia mikrofonowego ze zgodą nadaną w Windows. Najpierw sprawdź nazwę urządzenia w ustawieniach systemu lub narzędziach FFmpeg. Uruchomienie:

    python -m videonotes record-mic --device "Microphone (USB Audio)" --output C:\Users\Public\Music\VideoNotes\lecture-001 --consent

Opcjonalny limit:

    python -m videonotes record-mic --device "Microphone (USB Audio)" --output C:\Users\Public\Music\VideoNotes\lecture-002 --consent --max-minutes 60

Nagrywanie jest świadomie wywoływane komendą z parametrem --consent, a urządzenie trzeba wskazać samodzielnie. Bez takiego parametru proces nie startuje. W trakcie pracy Ctrl+C kończy nagrywanie sygnałem FFmpeg q, bez skasowania nagranego materiału.

Format: mono PCM 16 kHz, 16 bit WAV, pliki part-00000.wav itd., nowy plik co 7200 sekund (2 godziny). Dziennik recording.json nie zawiera nazwy urządzenia, dźwięku ani pełnych ścieżek źródłowych. Pliki pozostają na lokalnym komputerze. Katalog sesji musi być nowy, co chroni przed nadpisaniem.

Kontrola po zakończeniu lub awarii:

    python -m videonotes record-status C:\Users\Public\Music\VideoNotes\lecture-001

Stan needs_review oznacza awarię procesu lub pliku. Nie wolno go bez sprawdzenia traktować jako kompletne nagranie. Istniejące pliki są zachowane. Zarejestrowany WAV można zaimportować dotychczasowym poleceniem transcribe po dostarczeniu lokalnego modelu Whisper i FFmpeg.

## Otwarte bramki

Jest to pierwsza implementacja backendu mikrofonu i dziennika nagrania, nie odebrana obsługa Windows. Konieczne: test prawdziwego mikrofonu z uprawnieniami systemowymi, rozłączaniem urządzeń, 2-godzinnym nagraniem, wyczerpaniem miejsca, wznowieniem po restarcie, UX GUI z wyborem urządzenia i start/stop, podglądem stanu i akceptacją użytkownika. Nie ma jeszcze nagrywania dźwięku systemowego ani miksowania mikrofonu z dźwiękiem komputera. Program FFmpeg oraz model ASR nie są spakowane w instalatorze.

Do automatycznych testów dołączono testy atrap procesu: tests/test_microphone.py. Atrapa NIE potwierdza dostępu do fizycznego urządzenia.
