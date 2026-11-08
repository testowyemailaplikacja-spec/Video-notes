# VN-04 — lokalne nagrywanie mikrofonu Windows / DirectShow

Data: 2026-11-06. W tym repo, bez zmian w Wiedora/Constant_app i Netlify.

## Interfejs programu i wykrywanie urządzeń

W GUI wybierz przycisk „Nagraj mikrofon — nowa sesja WAV (Windows)”, kliknij „Wykryj”, wskaż urządzenie i katalog bazowy, a następnie potwierdź rozpoczęcie. Program tworzy unikalny podkatalog i nagrywa poza głównym wątkiem GUI. „Zatrzymaj” zamyka plik WAV; panel pokazuje status i liczbę części. Po zakończeniu pierwszy WAV jest gotowy do wyboru jako źródło transkrypcji. UI nie wystartuje równolegle z przetwarzaniem innego projektu.

W trybie CLI lista urządzeń jest dostępna bez rozpoczęcia nagrywania:

    python -m videonotes record-devices

Lista jest odczytywana lokalnie z FFmpeg/DirectShow; przed udostępnieniem urządzeń Windows musi pozwalać na dostęp do mikrofonu. Nazwa urządzenia może się zmienić po aktualizacji sterownika lub odłączeniu. Automatyczne testy korzystają z atrap danych, a nie z realnych urządzeń.

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

Jest to pierwsza implementacja backendu mikrofonu i dziennika nagrania, nie odebrana obsługa Windows. Konieczne: test prawdziwego mikrofonu z uprawnieniami systemowymi, rozłączaniem urządzeń, 2-godzinnym nagraniem, wyczerpaniem miejsca, wznowieniem po restarcie, fizyczny odbiór interfejsu Windows, prawdziwy wybór urządzenia i stabilność GUI przy długich nagraniach. Nie ma jeszcze nagrywania dźwięku systemowego ani miksowania mikrofonu z dźwiękiem komputera. Program FFmpeg oraz model ASR nie są spakowane w instalatorze.

Do automatycznych testów dołączono testy atrap procesu: tests/test_microphone.py. Atrapa NIE potwierdza dostępu do fizycznego urządzenia.

## Raport czytelnych części po przerwanym nagrywaniu (07.11.2026)

Jeżeli po awarii nagrywania dziennik ma stan `needs_review` lub `recording`, polecenie `record-status` **nie zatrzymuje całego podglądu na pierwszym uszkodzonym pliku WAV**. Zwraca osobno listę poprawnie odczytanych części w `segments` i nazwy plików wymagających ręcznej kontroli w `unreadable_parts`. Pole `requires_manual_review=true` przypomina, że sesja nie została odebrana i może wciąż być aktywna.

Dokument i nagrania pozostają bez zmian: kontrola nie naprawia, nie usuwa, nie odtwarza brakujących danych, nie zmienia `recording.json` ani nie otwiera dowiązań symbolicznych do plików spoza katalogu. Tylko sesja z dziennikiem `finished` przechodzi nadal **ścisłą walidację wszystkich plików**; uszkodzenie dowolnej części powoduje błąd.

Przykład: przy kompletnym `part-00000.wav` i urwanym `part-00001.wav` stan po awarii pokazuje pierwszy jako możliwy do późniejszego odzysku, a drugi jako wymagający kontroli. Nie dowodzi to możliwości przywrócenia urwanej części ani ukończenia testu awarii fizycznego urządzenia Windows.

## Kontrola integralności WAV po awarii i brakujących fragmentach (08.11.2026)

Sam nagłówek RIFF/WAV nie dowodzi, że zapisano wszystkie próbki. Po awarii może pozostać plik, w którym zadeklarowana długość PCM jest większa od faktycznej. Kontrola `record-status` sprawdza teraz **całe zadeklarowane audio**, czytając dane sekwencyjnie w blokach do 65 536 próbek (bez ładowania długiego wykładu do pamięci). Nie odtwarza i nie poprawia uszkodzonych danych.

Dla sesji `finished` wymagane są także ciągłe nazwy `part-00000.wav`, `part-00001.wav` itd., zgodność liczby części i sumy czasu z zapisanym dziennikiem `recording.json`. Brak części, ucięta końcówka PCM albo niespójny dziennik oznaczają błąd zamiast fałszywego potwierdzenia kompletności. Dla sesji `recording` lub `needs_review` nieczytelne pliki trafiają do `unreadable_parts`, a nie do listy zdrowych części. Materiały i dziennik pozostają nienaruszone.

Automatyczne regresje obejmują celowe ucięcie danych przy zachowaniu poprawnego nagłówka, usunięcie/przesunięcie części oraz nieprawidłowe metadane zakończenia. **Nie jest to test fizycznej awarii dysku, 2-godzinnego nagrywania ani rzeczywistego mikrofonu Windows.** Odbiór VN-04 wymaga nadal testów urządzeń i pełnego instalatora.
