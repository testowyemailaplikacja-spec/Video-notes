# VN-03 — konspekt źródłowy (częściowa implementacja)

Data: 2026-11-06. Pierwszy moduł konspektu wielopoziomowego w repo Video-notes. Bez zmian w Constant_app, Supabase i Netlify.

## Uruchomienie

    python -m videonotes advanced-notes KATALOG_PROJEKTU --template lecture --detail standard --section-minutes 10

Dostępne szablony: lecture, tutorial, meeting, study. Szczegółowość: brief, standard, full. Wyniki: exports/notes-advanced.md oraz exports/notes-advanced.json. Wypowiedzi są cytowane z aktualnie poprawionej transkrypcji razem z identyfikatorem segmentu i czasem. Pole source_sha256 wiąże wynik z treścią transkrypcji. Interfejs Tkinter udostępnia podgląd tylko do odczytu.

## Opcjonalny DOCX bez chmury

Możesz dodać `--docx` do polecenia `advanced-notes`, np.:

    python -m videonotes advanced-notes KATALOG_PROJEKTU --template lecture --detail full --docx

Program utworzy dodatkowo `exports/notes-advanced.docx`. To plik Word/LibreOffice z tytułami sekcji, cytatami, identyfikatorami segmentów i znacznikami czasu. Wykorzystuje wyłącznie standardową bibliotekę Pythona; nie uruchamia makr, nie osadza zewnętrznych linków ani nie wysyła transkrypcji do serwera. Surowa transkrypcja i ręczne poprawki pozostają nietknięte. Flaga jest opcjonalna: bez niej pozostają dotychczasowe pliki Markdown i JSON.

**Nie jest to eksport PDF** ani semantycznie opracowana notatka. Przed upublicznieniem potrzebne pozostają także ręczne testy zgodności DOCX z Word/LibreOffice oraz ocena jakości notatek na prawdziwych wykładach.

## Granice funkcjonalne

To deterministyczny konspekt ekstrakcyjny dzielony według czasu, a NIE semantyczny model językowy, streszczenie, analiza slajdów ani weryfikacja faktów. Etykiety możliwej definicji, przykładu i pytania są tylko podpowiedziami heurystycznymi. Nie są dowodem pewności ASR. Nie dodajemy faktów, definicji ani wyjaśnień spoza źródła. Wybrane cytaty nie obejmują każdej wypowiedzi w dłuższym nagraniu.

Prywatność: pełna praca offline, brak płatnych API, kont, telemetrii i nowych zależności. Eksport jest przebudowywany z aktualnych korekt; oryginalne project.json, transcript.json, edits.json, notes.json oraz ręczne poprawki pozostają nietknięte. Cytaty w Markdown są blokami kodu, żeby nie interpretuwać HTML i linków z transkrypcji.

## Odbiór

Testy kodu: tests/test_advanced_notes.py, kompletna regresja Linux i podzbiór Windows w CI. Nadal potrzebne: rzeczywiste wykłady, poprawna segmentacja semantyczna, definicje i przykłady ocenione przez człowieka, spójność wielogodzinnych opracowań, testy rozdziałów materiałów CCNA, oddzielny OCR, DOCX/PDF i weryfikacja działania na fizycznym Windows. VN-03 pozostaje W_TRAKCIE, nie DONE.

## Bezpieczny eksport wielu formatów (07.11.2026)

Przy opcji `--docx` program **najpierw generuje w pamięci** Markdown, JSON i DOCX, a dopiero po pomyślnym przygotowaniu całego zestawu zastępuje pliki na dysku. Błąd kodowania DOCX nie usuwa już istniejących, zatwierdzonych eksportów Markdown/JSON ani nie pozostawia nowych, niekompletnych plików. Regresje obejmują oba przypadki.

Każdy zapis pliku korzysta z atomowej wymiany, ale **zestaw trzech plików nadal nie jest jedną transakcją systemu plików**: awaria dysku lub brak miejsca podczas późniejszego zapisu może pozostawić różne wersje plików. Nie traktować tego testu jako pełnego odbioru bezpieczeństwa zapisu lub Windows. VN-03 pozostaje W TRAKCIE.

## Nagłówki oparte na słowach ze źródła (07.11.2026)

Dotychczasowe ogólne nagłówki „Zagadnienie 1”, „Zagadnienie 2” uzupełniono o krótkie wskazówki tematyczne: program wybiera słowa **dosłownie występujące w cytowanych fragmentach**, preferując te powtarzające się w kilku różnych wypowiedziach. W razie braku powtarzalnych słów stosuje początek cytatu z pominięciem słów funkcyjnych. Nagłówki nie mogą zawierać znaczników Markdown/HTML, a oryginalne cytaty nadal zachowują pełną treść i odnośniki do czasu.

To heurystyka porządkująca, **nie semantyczny model AI**: nie weryfikuje poprawności ASR, nie rozumie znaczenia wypowiedzi i może wskazać słowo niebędące faktycznym tematem. Wymagana jest nadal ocena człowieka na rzeczywistych wykładach/CCNA. Format JSON i Markdown nadal używa dotychczasowego schematu `videonotes-source-outline-v1`.

## Test DOCX w prawdziwym silniku LibreOffice (automatyczny Ubuntu)

W osobnym workflow `vn-docx-libreoffice.yml` generowany jest lokalny DOCX zaawansowanego konspektu z syntetycznej transkrypcji. LibreOffice Writer w trybie headless konwertuje go do PDF, Poppler sprawdza tekst źródłowy i polskie znaki, a render pierwszej strony do PNG potwierdza możliwość interpretacji strony przez renderer. Ten sam test obejmuje podstawowy DOCX z ręczną poprawką i niezinterpretowanym znacznikiem HTML.

To test kompatybilności pliku z prawdziwym silnikiem LibreOffice, nie ocena typografii ani weryfikacja otwierania w Microsoft Word na fizycznym Windows. Powstały PDF i PNG służą wyłącznie w CI, nie są wysyłane do chmury przez aplikację i nie stanowią dostępnego eksportu PDF. VN-03 pozostaje W_TRAKCIE.

### Wykryta i naprawiona niezgodność pakietu OOXML

Rzeczywisty LibreOffice 24.2 na Ubuntu odmówił wczytania DOCX, mimo że testy ZIP i parser XML zgłaszały poprawny format. Przyczyną było serializowanie znaczników głównych OPC `[Content_Types].xml` oraz `_rels/.rels` z prefiksem `ns0:` zamiast kanonicznej domyślnej przestrzeni nazw. Generator zapisuje teraz oba korzenie w formacie `<Types xmlns="...">` i `<Relationships xmlns="...">`, z ochroną przed równoczesnym przełączaniem przestrzeni nazw w wielu wątkach.

Testy strukturalne sprawdzają tę reprezentację bajtową, a osobny workflow próbuje otworzyć DOCX w realnym LibreOffice i wyrenderować dokument do PDF/PNG. To realna poprawka kompatybilności, ale odbiór ręczny w Word/LibreOffice na sprzęcie Windows pozostaje osobnym wymaganiem.
