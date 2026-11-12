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

## Transkrypcja sesji podzielonej na kilka części (VN-04, 08.11.2026)

Dłuższe nagranie jest zapisywane jako `part-00000.wav`, `part-00001.wav` itd. **Pierwszy plik nie jest całym wykładem.** Aby po ukończeniu sesji uzyskać jeden plik nadający się do istniejącej kolejki transkrypcji, użyj:

```powershell
python -m videonotes record-status C:\\Nagrania\\wyklad-001
python -m videonotes record-join C:\\Nagrania\\wyklad-001 --output C:\\Nagrania\\wyklad-001\\recording-full.wav
python -m videonotes inspect C:\\Nagrania\\wyklad-001\\recording-full.wav
```

W GUI dodano osobny przycisk **„Połącz części ukończonego nagrania WAV do transkrypcji”**. Po wskazaniu katalogu i potwierdzeniu program tworzy w tle plik `recording-full.wav`, który można wybrać do transkrypcji. Gdy nagranie ma więcej niż jedną część, GUI nie wybiera już automatycznie samej pierwszej jako pełnego źródła.

Łączenie nie wymaga FFmpeg ani sieci. Kopiuje mono PCM 16 kHz/16 bit bez zmiany próbek, w blokach do 65 536 ramek. Przed zapisem sprawdza integralność źródłowych części, ciągłość numeracji i zgodność dziennika, weryfikuje dostępne miejsce, limit standardowego WAV 4 GB oraz nie nadpisuje istniejącego celu nawet w razie jednoczesnego utworzenia go przez inny proces. Wynik powstaje w pliku tymczasowym i jest udostępniany atomowo dopiero po walidacji. Części źródłowe i `recording.json` pozostają bez zmian. Sesja w stanie `needs_review` nie może być automatycznie łączona, dopóki nie zostanie odrębnie sprawdzona.

**Ograniczenia:** złączenie wymaga dodatkowego miejsca w przybliżeniu równego wielkości audio, trwa proporcjonalnie do jego długości i nie usuwa oryginalnych części. Powyżej 4 GB standardowego WAV potrzebna będzie osobna ścieżka przetwarzania. Testy automatyczne korzystają z prawdziwych syntetycznych plików PCM zapisanych przez bibliotekę `wave`, nie z fizycznego mikrofonu Windows. Nie oznaczają zakończenia VN-04.

## Sumy SHA-256 ukończonych nagrań (08.11.2026)

Dla **nowych** sesji program zapisuje w lokalnym `recording.json` pole `hash_policy: sha256-v1` oraz osobną sumę SHA-256 każdego pliku `part-XXXXX.wav`, obliczaną po poprawnym zamknięciu FFmpeg. `record-status` sprawdza te sumy podczas odbioru sesji `finished`. Pozwala to wykryć również niezamierzoną zmianę próbek PCM, która nie uszkodziła nagłówka WAV, liczby ramek ani długości. Status zawiera pole `sha256_verified`, bez udostępniania samego dźwięku, transkrypcji ani sum przez sieć.

Sesja z nową polityką, lecz brakującym lub niezgodnym wykazem SHA-256, **nie przechodzi kontroli**, a pliki pozostają nienaruszone. Dzienniki sprzed tej aktualizacji (bez `hash_policy`) pozostają czytelne dla zgodności i otrzymują `sha256_verified=false`; nie należy uznawać ich za sprawdzone kryptograficznie. Przerwane sesje nadal zachowują status `needs_review` i nie są automatycznie domykane.

To mechanizm wykrywania przypadkowego uszkodzenia po zapisie, nie podpis cyfrowy, ochrona przed celową zmianą pliku i dziennika jednocześnie, kopia zapasowa ani odbiór fizycznego dysku Windows. Pełne testy sprzętowe pozostają wymagane.

## Pauza i wznowienie bez utraty wcześniejszych części (08.11.2026)

Interfejs sesji mikrofonowej otrzymał osobne przyciski **Pauza**, **Wznów nagrywanie** i **Zatrzymaj**. Wybór i zgoda na urządzenie nadal wymagają działania użytkownika. „Pauza” *nie zawiesza* procesu FFmpeg wraz z niezapisanym buforem; zamiast tego wysyła mu polecenie `q`, czeka na zamknięcie pliku WAV, sprawdza wszystkie zapisane części i zapisuje w lokalnym `recording.json` status `paused`, liczbę części oraz ich sumy SHA-256. Można wtedy bezpiecznie wybrać „Wznów”, uruchamiając nowy proces FFmpeg na **tym samym urządzeniu**, z następnym numerem `part-XXXXX.wav`. Dotychczasowe pliki nie są ponownie otwierane do zapisu ani nadpisywane.

**Stop podczas pauzy** zamyka sesję bez tworzenia pustego fragmentu. Łączny czas audio nie obejmuje przerw, dlatego po sklejeniu uzyskujemy ciągłe nagranie tylko z chwil aktywnego rejestrowania. W zapisie pozostaje `pause_count`, ale ze względów prywatności nazwa urządzenia nie jest utrwalana. Zatrzymanie lub wznowienie nie oznacza automatycznego uruchomienia transkrypcji.

Awaria podczas pauzy lub po restarcie pozostawia dziennik `paused` lub `needs_review`; polecenie `record-status` pokazuje czytelne części, ale **nie** oznacza sesji automatycznie jako ukończonej. Uruchomienie po awarii do tego samego katalogu jest celowo zabronione, aby nie nadpisać danych. Ponowne wznowienie istniejącej zakończonej sesji po zamknięciu aplikacji nie jest jeszcze dostępne.

Testy automatyczne symulują proces FFmpeg, jego prawidłowe zamykanie, dwie oddzielne części o różnych próbkach PCM, pauzę, wznowienie, stop w pauzie, wyścigi i błąd drugiego ujęcia. Sprawdzają SHA, dziennik, numery części, treść po bezstratnym sklejeniu oraz rzeczywiste przyciski Tk na Linux/Windows CI. **Nie potwierdzają testu fizycznego mikrofonu ani zachowania urządzenia DirectShow po 2 godzinach**. Wymagany pozostaje test na prawdziwym komputerze, urządzeniu USB, przy odłączeniu i uśpieniu systemu.

### Izolacja nowych ujęć przed opublikowaniem (zabezpieczenie FFmpeg)

Weryfikacja z **rzeczywistym FFmpeg na Linux CI** wykazała, że segmentowy muxer potrafi **ignorować globalną opcję `-n`** i zapisać plik pod istniejącą nazwą bez zgłoszenia błędu. Dlatego samo podawanie numeru kolejnego fragmentu nie zapewniało wystarczającej ochrony.

Każde nowe ujęcie (przed pauzą i po wznowieniu) zapisuje się teraz w odrębnym losowym katalogu `.vn-take-*`. Program sprawdza format i numery jego WAV, a następnie publikuje wszystkie fragmenty do katalogu sesji przez **atomowe dowiązania twarde bez możliwości zastąpienia istniejącego pliku**. Dopiero po pełnej publikacji usuwa zapasowe nazwy z katalogu roboczego. Istniejące części są chronione również w scenariuszu, gdy inny proces utworzy oczekiwany plik w ostatniej chwili.

Po niepowodzeniu nagrania, uszkodzeniu fragmentu lub konflikcie zapisu ukryty katalog `.vn-take-*` **pozostaje na dysku** wraz z niezapisanymi jeszcze do sesji próbkami, zamiast być automatycznie kasowany. `record-status` zwraca nazwy tych katalogów w `pending_takes`; stan `needs_review` wymaga ręcznej kontroli. Nie przenoś, nie usuwaj ani nie uruchamiaj ponownie nagrywania w tym samym folderze, dopóki nie wykonasz bezpiecznej kopii. Nie jest to jeszcze automatyczne przywracanie przerwanego nagrania z bufora FFmpeg.

## Lokalna diagnostyka głośności, ciszy i przesterowania (08.11.2026)

Po zakończeniu nagrania wybierz w GUI **„Sprawdź jakość nagrania WAV — cisza i przesterowanie”** i wskaż katalog z `recording.json`. Program odczytuje strumieniowo wszystkie ukończone części WAV w oknach po 2 sekundy. Wyświetla liczbowy raport: średni poziom RMS w dBFS, szczyt (peak) w dBFS, udział próbek bliskich maksimum zakresu PCM (clipping), udział ciszy/bardzo cichych okien, najdłuższy cichy fragment, ostrzeżenia i parametry poszczególnych części. Nie zapisuje zawartości nagrania w raporcie, nie tworzy transkrypcji i nie korzysta z sieci ani z modelu AI.

Polecenie terminalowe:

```powershell
python -m videonotes record-status C:\\Nagrania\\wyklad-001
python -m videonotes record-analyze C:\\Nagrania\\wyklad-001
```

Wymagany jest stan `finished` oraz prawidłowe części PCM mono 16 kHz/16 bit. Dla nowych sesji sprawdzane są także sumy SHA-256; stare dzienniki bez hashy są wyraźnie oznaczane jako `sha256_verified=false`. Przerwane i wstrzymane sesje nie są automatycznie uznawane za kompletne. Weryfikacja czyta pliki bez ich edycji, w ograniczonych blokach i bez wczytywania całego wykładu do RAM.

**Interpretacja:** RMS poniżej –38 dBFS może oznaczać zbyt niski poziom; szczyt bliski 0 dBFS lub ponad 0,5% próbek bliskich maksimum może wskazywać na przesterowanie; cisza jest szacowana z 2-sekundowych okien o RMS poniżej –45 dBFS. Są to jedynie wskazówki, a nie miernik jakości mowy. Brak ostrzeżeń nie gwarantuje prawidłowej treści, braku szumu, poprawności diarizacji ani transkrypcji ASR. Weryfikacja **nie zastępuje odsłuchu ani testu prawdziwego urządzenia Windows**.

Testy automatyczne obejmują rzeczywiste oryginalne PCM: sinusoidalną mowopodobną falę, ciszę, przesterowanie, uszkodzenie WAV, sesje `paused` / `needs_review`, starsze dzienniki bez SHA, CLI i rzeczywisty podgląd Tk na Linux/Windows CI. Nie wykorzystują prywatnych nagrań użytkownika.

## Rzeczywisty proces FFmpeg — próba pełnego cyklu Pauza/Wznów (08.11.2026)

Po testach jednostkowych z atrapą uruchamiana jest również osobna bramka CI `.github/workflows/vn-real-mic-pause.yml`. Korzysta z faktycznego procesu **FFmpeg** na Linux i lokalnego generatora `lavfi sine` zamiast mikrofonu. Program przeprowadza **dwa faktyczne ujęcia**, celowo pauzuje przez polecenie `q` (FFmpeg finalizuje WAV), wznowienie wykonuje do kolejnego prywatnego katalogu, a po stopie kontroluje status `finished`, SHA-256, dwie różne próbki, niezmienność wcześniejszej części, brak pozostałych tymczasowych katalogów, bezstratne sklejenie i analizę poziomu dźwięku.

Nie jest to atrapa procesu nagrywającego — przetwarzanie WAV, sterowanie stdin, segmentowy muxer i dekodowanie PCM są wykonywane rzeczywiście. **Źródłem jest sztuczna fala sinusoidalna; test nie otwiera mikrofonu Windows, nie sprawdza DirectShow, uprawnień, loopback ani zachowania po wielu godzinach.** Dopiero po zielonej akcji CI można oznaczyć podtest jako PASS. Nie oznacza to ukończenia VN-04.

## Bezpieczne odzyskanie czytelnej części po awarii (08.11.2026)

Dotychczas aplikacja zachowywała `part-XXXXX.wav` i `.vn-take-*` po awarii FFmpeg, lecz wymagała ręcznej obsługi plików. Dodano **podgląd odzysku i eksport częściowo uratowanego nagrania**. System nie uznaje automatycznie uszkodzonej sesji za ukończoną.

Najpierw upewnij się, że **proces nagrywania już nie działa**. W terminalu uruchom:

```powershell
python -m videonotes record-recovery-status C:\\Nagrania\\wyklad-001
python -m videonotes record-salvage C:\\Nagrania\\wyklad-001 --output C:\\Nagrania\\wyklad-001\\recording-salvaged-INCOMPLETE.wav --confirm-stopped
```

Podgląd czyta i sprawdza wszystkie rozpoznane WAV w katalogu sesji i jej podkatalogach roboczych `.vn-take-<UUID>`; weryfikuje format PCM mono 16 kHz/16 bit, liczbę próbek, obecne sumy SHA-256, nazwę i ciągłość numeracji. Zwraca listę poprawnych części tworzących **nieprzerwany prefiks** od `part-00000.wav` i nazwy problemów. Jeśli wykryje brak `part-00001.wav`, uszkodzenie, konflikt dwóch różnych poprawnych plików o tej samej nazwie albo symlink, **nie przeskakuje** do dalszych fragmentów. Niczego nie naprawia ani nie usuwa.

Dopiero osobne `--confirm-stopped` pozwala utworzyć nowy plik WAV. W programie Windows jest przycisk **„Odzyskaj czytelne WAV po awarii (może być niekompletne)”**. Użytkownik potwierdza zatrzymanie FFmpeg i otrzymuje silne ostrzeżenie o niekompletnym wykładzie. Po odzyskaniu program wskazuje nowy WAV jako źródło do transkrypcji, lecz nie zmienia oryginalnego dziennika ani plików. Dla wynikowego WAV używane są ograniczone bufory, sprawdzenie wolnego miejsca, walidacja danych i atomowe opublikowanie bez nadpisania istniejącego celu. Źródła można nadal analizować ręcznie albo z kopii.

**Ważna granica:** funkcja nie odzyskuje niezapisanych próbek z pamięci urządzenia, utraconej końcówki WAV ani dźwięku po pierwszej luce. Nie rekonstruuje brakujących fragmentów i nie poprawia automatycznie uszkodzonego nagłówka. Zwraca `not_a_complete_lecture=true` i `requires_user_review=true`. Eksport działa wyłącznie dla sesji oznaczonej `needs_review` po zatrzymaniu procesu. Dla `recording`, `paused` i `finished` odmówi utworzenia kopii, aby nie podszyć się pod kompletny wykład. Nadal wymagany pozostaje fizyczny test awarii mikrofonu i kontroli materiału Windows.


## Kontrola źródła podczas łączenia długich WAV — 12.11.2026

Łączenie ukończonych części WAV ma dodatkową ochronę przed równoległą zmianą danych. Po sprawdzeniu, że sesja jest kompletna, narzędzie zapisuje SHA-256 każdej części **przed odczytem**, łączy w strumieniu i weryfikuje SHA-256 części oraz kompletny dziennik sesji **ponownie przed opublikowaniem** nowego WAV. Jeśli inny proces zmieni choćby pojedynczy bajt PCM, zastąpi część lub zmieni stan sesji, operacja odmawia opublikowania wyniku i usuwa jedynie nieukończony plik tymczasowy. Oryginalnych nagrań, nawet zmienionych, nie cofa ani nie usuwa. Utrzymano atomową publikację bez nadpisywania. Dodatkowe hashowanie zajmuje czas I/O proporcjonalny do długości nagrania, ale nie wczytuje 2 h materiału do RAM. Testy syntetyczne wywołują zmianę źródła/dziennika podczas łączenia; fizyczne 2 h i awaria Windows są nadal NOT_RUN.

## Sprawdzenie odzyskiwania po awarii przed publikacją (12.11.2026)

Funkcja `record-salvage` po skopiowaniu czytelnego początku sesji do tymczasowego WAV **ponownie odczytuje i weryfikuje listę wszystkich części, ich hashe, stan dziennika i foldery robocze** przed udostępnieniem wyniku. Wcześniej część, która została już skopiowana, mogła ulec zmianie podczas kopiowania kolejnej części, a odzysk nadal publikował plik oparty na mieszanym stanie. Obecnie zmiana WAV albo dziennika w trakcie kopiowania przerywa zapis wyniku, a oryginalne nagrania pozostają nietknięte przez narzędzie. Testy wymuszają zmianę bajtu WAV i statusu sesji dokładnie przed publikacją, z kontrolą braku pliku wynikowego. Nie jest to odtwarzanie utraconych próbek; fizyczny test awarii i urządzenia Windows nadal wymagany.
