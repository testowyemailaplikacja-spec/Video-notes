# VN-01/VN-06 — lokalna przenośna kopia projektu (.vnproj)

**Status 06.11.2026:** kod i testy automatyczne przygotowane, nie jest to jeszcze pełny backup nagrań ani przetestowany instalator Windows.

## Użycie

Zapisz kopię **lokalnie**, wskazując nowe miejsce:

    python -m videonotes backup moje-notatki --output archiwum_20261106.vnproj

Aby przywrócić, wskaż nowy, nieistniejący katalog:

    python -m videonotes restore archiwum_20261106.vnproj --project moje-notatki-odzyskane

Aby wznowić ASR po przeniesieniu danych, wskaż **oryginalne** nagranie i identyczny model (z tym samym SHA-256):

    python -m videonotes relink moje-notatki-odzyskane --source wyklad.mkv --model ggml-base.bin --whisper-cli whisper-cli

Potem można użyć `resume`. Bez ponownego podłączenia źródła i modelu archiwum pozwala przeglądać transkrypcję/notatki i je eksportować, ale nie pozwala kontynuować rozpoznawania mowy.

## Co zawiera plik

Archiwum ZIP ma sztywną, zamkniętą listę wpisów: `project.json`, `transcript.json`, `edits.json`, opcjonalne `notes.json` i `notes-edits.json`, opcjonalną historię `notes-history/<identyfikator>.json` oraz `archive-manifest.json` z hashami SHA-256 i rozmiarami. Metadane komputera w `project.json` (bezwzględna ścieżka nagrania, modelu i programu) są redagowane. Zapis jest atomowy, nie nadpisuje poprzedniej kopii.

Ważne: **w kopii znajdują się teksty transkrypcji i notatek**, które mogą zawierać dane osobowe. Traktuj ją jak prywatny plik, najlepiej przechowuj na zaszyfrowanym dysku. Program nie wysyła kopii do chmury.

**Nie ma w kopii:** plików audio/wideo, binariów modeli ASR, aplikacji ani bibliotek Windows. Oryginalne media i modele trzeba zabezpieczyć oddzielnie. Bez nich nie można wznowić rozpoznawania.

## Kontrole bezpieczeństwa

- Odczyt tylko znanych nazw plików. Wpisy `../`, nieznane podkatalogi, pliki obce, duplikaty i symlinki są niedozwolone. Wyjątkiem są wyłącznie snapshoty `notes-history/[32 znaki hex].json`, sprawdzane dodatkowo względem sum i schematów wersji.
- Limit 64 MiB na wpis ZIP, 128 MiB sumarycznie i jawna weryfikacja SHA-256 każdej zawartości po dekompresji.
- Schemat `project.json` i `transcript.json` jest walidowany, a cytaty notatek są weryfikowane względem źródła. Uszkodzone archiwum nie tworzy częściowo ukończonego katalogu.
- Przywracanie wymaga nieistniejącego katalogu i zapisuje cały projekt atomowo. Nie nadpisuje istniejących projektów, eksportów ani cudzych danych.
- Relink oblicza SHA-256 i sprawdza czas/indeks ścieżki FFprobe, nie podmienia nagrania na inne o tej samej nazwie.

## Granice odbioru

Do zamknięcia etapów nadal wymagane są: testy uszkodzenia dysku/zasilania, eksport pełnego pakietu z mediami na życzenie, migracje wersji i zgodność z GUI/instalatorem Windows, test kilkugodzinnego nagrania i bezpieczeństwa zewnętrznych nośników. Oznaczenie tej funkcji jako użytecznej nie zamyka całego VN-01 ani VN-06.

## Uzupełnienie bezpieczeństwa 07.11.2026

Gotowa kopia jest publikowana atomowo z unikalnego pliku tymczasowego przy użyciu lokalnego dowiązania twardego, które **nie może nadpisać** pliku utworzonego równocześnie przez inny proces. Na systemie plików bez obsługi tej operacji program odmawia utworzenia archiwum, usuwa plik tymczasowy i prosi o inny dysk; nie zastępuje tego nieatomową kopią. Dodano regresję symulującą wyścig zapisu i brak obsługi systemu plików. Nie oznacza to przetestowania awarii zasilania ani fizycznych zewnętrznych nośników.

## Historia cofania zmian (07.11.2026)

Przenośna kopia obejmuje również do 1000 istniejących snapshotów notatek z `notes-history/`. Każdy wpis przechodzi walidację nazwy, sum SHA-256 własnej migawki, identyfikatora projektu i manifestu ZIP. Weryfikacja wykonywana jest ponownie przed zakończeniem odtwarzania. Archiwa utworzone wcześniej bez historii nadal są obsługiwane.

Po przywróceniu można sprawdzić zachowane wersje i cofać je tylko wtedy, gdy ich odnośniki źródłowe pozostają zgodne z aktualną transkrypcją. Wersje historyczne mogą zawierać prywatne teksty, więc zaszyfrowane miejsce przechowywania jest nadal zalecane. Realny test uszkodzenia nośnika i odłączenia zasilania pozostaje NOT_RUN.


## Bezpieczny wyścig podczas przywracania kopii (12.11.2026)

Podczas publikacji odtworzonego katalogu projektowego usunięto \`os.replace(staging, destination)\`, ponieważ na systemach POSIX mogło ono **zastąpić pusty katalog** utworzony przez drugi proces dopiero po wcześniejszym sprawdzeniu, że miejsce docelowe nie istnieje. Teraz wykorzystujemy tę samą, atomową operację bez nadpisywania co w prywatnym pakiecie instalacyjnym: Windows \`os.rename\` (odmawia, gdy folder istnieje), Linux \`renameat2(RENAME_NOREPLACE)\`; nieobsługiwane systemy odmawiają publikacji zamiast zgadywać. Test regresji wstawia pusty folder dokładnie między przygotowaniem pełnej kopii a atomową publikacją, następnie sprawdza zachowanie folderu oraz posprzątanie katalogu tymczasowego. Nie dotyka to archiwum ani istniejących danych użytkownika. Odbiór na fizycznym Windows nadal pozostaje osobną bramką.

## Spójność migawki w trakcie tworzenia kopii — 12.11.2026

Przed publikacją archiwum VN odczytuje ponownie i porównuje aktualny projekt, transkrypcję, poprawki transkrypcji, parę notatka/poprawki oraz pełny zestaw i zawartość plików historii. Jeżeli podczas kopiowania inna operacja zmieniła transkrypcję, ręczne poprawki albo usunęła/dodała wersję notatki, zapis kopii zostaje przerwany, a oryginały pozostają nietknięte. Nie powstaje ZIP mieszający kilka stanów projektu. Kontrole są prowadzone lokalnie, bez przesyłania danych do sieci; są oparte na ponownym odczycie, więc nie stanowią atomowej migawki systemu plików wobec niekooperującego zewnętrznego procesu, który może nadal pisać po kontroli. Testy symulują zmiany w trakcie kopiowania, a potem możliwość udanej ponownej próby. Formalny odbiór pełnego odzyskiwania po przerwaniu pracy na fizycznym Windows pozostaje otwarty.
