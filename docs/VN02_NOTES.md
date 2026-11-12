# VN-02 — podstawowe notatki z transkrypcji (ekstrakcyjne)

**Status 06.11.2026:** zaimplementowana pierwsza, ściśle źródłowa wersja — etap VN-02 nadal W TRAKCIE. To nie jest pełna inteligentna notatka ani LLM; nie ma jeszcze ocenionej jakości na rzeczywistych polskich wykładach.

## Jak to działa

Po całkowitym ukończeniu transkrypcji (komenda resume lub transcribe) użytkownik wybiera w GUI „Notatka podstawowa” albo wykonuje:

    python -m videonotes notes KATALOG_PROJEKTU --window-minutes 5 --points 6
    python -m videonotes notes-edit KATALOG_PROJEKTU --point quote-c0000000-s00000 --text "Mój poprawiony punkt"
    python -m videonotes notes-export KATALOG_PROJEKTU

Notatka jest **ekstrakcyjna**: każda linia pochodzi dosłownie z transkrypcji (lub z jawnej ręcznej poprawki). Zamiast generować niezweryfikowane definicje albo udawać streszczenie, program dzieli materiał według czasu, wybiera reprezentatywne wypowiedzi i zachowuje czas oraz identyfikator segmentu. Pierwszy/ostatni fragment każdego okna jest preferowany; pozostałe są wybierane na podstawie występowania słów i odstępu czasu.

Zależności są wyłącznie lokalne; nie jest potrzebny model językowy ani płatne API. Notatki mogą pominąć ważne kwestie i mogą zawierać błędy oryginalnego ASR, dlatego nie są dokumentem gotowym bez kontroli człowieka. Wybór fragmentów nie jest interpretacją semantyczną.

## Trwałość i brak utraty pracy

- notes.json — wygenerowany raz dokument, lista sekcji, punktów i ich źródeł, SHA-256 aktualnej poprawionej transkrypcji.
- notes-edits.json — osobne poprawki punktów dokonane w CLI/GUI.
- exports/notes-basic.md — czytelny Markdown, fragmenty źródłowe wraz z czasem i ID. Markdown zawiera tekst w wciętych blokach, aby treść z wykładu nie uruchamiała niebezpiecznego HTML.
- Oryginalne transcript.json oraz edits.json pozostają nietknięte.
- Regeneracja notatki nie nadpisuje istniejącego dokumentu. Kiedy użytkownik później zmieni transkrypcję, eksport starej notatki jest blokowany, aby nie udawała aktualnych odwołań do źródła. Potrzebny osobny mechanizm wersjonowania/regeneracji z zachowaniem poprawek.

## Ograniczenia i otwarte wymagania VN-02

Nie wykonano jeszcze oceny pokrycia zagadnień przez człowieka, testu długich rzeczywistych nagrań, podsumowania abstrakcyjnego, wycofania/ponownego wygenerowania z historią wersji, ani eksportu DOCX/PDF. Silnik lokalny AI z porównaniem do reguł to dalszy zakres. Wymagana jest ocena nazwisk, dat i liczb na prawdziwych materiałach.

**Testy automatyczne:** tests/test_notes.py i tests/test_notes_cli.py — poprawne cytaty, czasy, trwałość edycji, stale detection, brak halucynacji w wynikach regułowych, odporność na uszkodzone dane. Wyniki CI należy podawać osobno, bez uznawania całego VN-02 za DONE.

## Lokalny eksport TXT (07.11.2026)

Aby oprócz Markdown pobrać czytelny plik tekstowy, użyj:

```bash
python -m videonotes notes-export KATALOG_PROJEKTU --txt
```

Domyślne `notes-export` nadal zapisuje tylko `exports/notes-basic.md`. Opcja `--txt` zapisuje dodatkowo `exports/notes-basic.txt` z identyfikatorami segmentów, czasami i jawnym oznaczeniem ręcznych poprawek. Oba formaty korzystają z tej samej walidacji zgodności cytatów ze źródłem; zapis TXT nie nadpisuje transkrypcji ani edycji. Nie jest to automatyczne streszczenie semantyczne, ocena jakości rzeczywistych wykładów pozostaje otwarta.

## Wznowienie tworzenia notatki po przerwaniu zapisu (VN-02)

Jeżeli tworzenie notatki zostało przerwane po zapisaniu `notes-edits.json`, lecz przed utworzeniem `notes.json`, ponowne wywołanie `notes` może bezpiecznie dokończyć pierwszą generację **wyłącznie wtedy**, gdy istniejący dziennik ma dokładny schemat `videonotes-note-edits-v1` i pustą listę poprawek. Program nie nadpisuje takiego pliku, ale zapisuje nową notatkę. Jeżeli dziennik zawiera jakiekolwiek dane użytkownika, nieoczekiwane pola lub błędną wersję, generowanie jest blokowane i wymaga ręcznej kontroli. Istniejąca `notes.json` nigdy nie jest automatycznie zastępowana. Jest to testowana obsługa **przerwania pomiędzy dwoma zapisami**, nie dowód odzyskiwania po fizycznej awarii dysku ani zamknięcie całego VN-02.

## Opcjonalny eksport Word DOCX (07.11.2026)

Notatkę podstawową można dodatkowo zapisać jako lokalny dokument Microsoft Word / LibreOffice:

    python -m videonotes notes-export KATALOG_PROJEKTU --docx

W oknie „Notatka podstawowa” dostępny jest przycisk **Eksportuj DOCX (offline)**. Przed eksportem należy zapisać zmianę aktualnie wpisywaną w edytorze. Domyślne `notes-export` pozostaje zgodne z wcześniejszą wersją i tworzy jedynie Markdown; `--txt` nadal jest niezależne.

Program tworzy `exports/notes-basic.docx` z tytułem, sekcjami, cytatami, identyfikatorami i czasami źródłowymi oraz widocznym oznaczeniem ręcznej poprawki. Każdy eksport przechodzi `read_basic_notes`: jeżeli transkrypcja zmieniła się od stworzenia notatki, operacja zostaje odmówiona bez nadpisania wcześniejszego DOCX. Oryginalne `transcript.json`, `notes.json` i poprawki pozostają nietknięte.

Dokument jest składany wyłącznie przez standardową bibliotekę Python; tekst użytkownika jest zapisany jako zwykły tekst OOXML, bez zewnętrznych relacji, makr i pobierania zasobów. Testy automatyczne weryfikują struktury ZIP/XML, niebezpieczny tekst literalny, Unicode, ręczne zmiany i ochronę przed nieaktualnym źródłem. Nie wykonano jeszcze **ręcznego testu otwierania/drukowania w Word i LibreOffice na fizycznym komputerze**. Nie jest to PDF ani semantyczne streszczenie; VN-02 nadal W TRAKCIE.

## Wydajność wyboru fragmentów przy długich transkrypcjach (07.11.2026)

Optymalizacja wyboru cytatów nie zmienia punktacji ani kolejności pierwszego/ostatniego cytatu. Słowa każdego segmentu oraz jego waga są analizowane raz, a najkrótsza odległość czasowa od już wybranych fragmentów aktualizowana po kolejnym wyborze. Eliminujemy ponowne rozbijanie każdego tekstu i przeliczanie wszystkich wybranych odległości w każdej iteracji.

Złożoność etapu wyboru po przygotowaniu tokenów spada z podejścia wielokrotnie skanującego wybrane fragmenty do O(n × liczba_punktów) i O(n) pamięci pomocniczej. `tests/test_note_selection.py` porównuje wyniki bezpośrednio z poprzednim algorytmem dla wielu losowo wygenerowanych okien, polskich/angielskich słów, powtarzających się czasów i remisów oraz uruchamia syntetyczną próbę **50 000 segmentów, 20 punktów**. To test wydajności algorytmu, nie próba rzeczywistego 2-godzinnego nagrania lub realnego ASR. Status etapu VN-02 nadal W_TRAKCIE.

## Test rzeczywistego otwierania DOCX w LibreOffice (automatyczny Linux)

Do CI dodano oddzielny test integracyjny `tests/test_office_docx.py`, który generuje **syntetyczne** notatki podstawowe i zaawansowane, otwiera oba pliki DOCX w rzeczywistym LibreOffice Writer (tryb headless), konwertuje je tymczasowo do PDF, sprawdza odczyt polskich znaków, cytatów, literalnego tekstu HTML oraz renderuje pierwszą stronę do obrazu PNG. Żaden przykład nie zawiera prywatnego nagrania. Tymczasowe pliki PDF/PNG są elementem testu, **nie nowym eksportem PDF w aplikacji**.

Test ma własny workflow `.github/workflows/vn-docx-libreoffice.yml` i wymaga widocznego wyniku PASS. Nie zastępuje ręcznej kontroli układu w LibreOffice GUI ani Wordzie na fizycznym Windows, druku, długiego dokumentu czy decyzji wydawniczej. VN-02 pozostaje W_TRAKCIE.

## Opcjonalny eksport PDF (08.11.2026)

Jeżeli na komputerze jest **lokalnie zainstalowany LibreOffice Writer**, podstawowe notatki można wyeksportować do PDF bez usług w chmurze:

    python -m videonotes notes-export KATALOG_PROJEKTU --pdf

Na Windows, gdy `soffice.exe` nie jest dostępny w PATH, wskaż jego plik przez `--office "C:\\Program Files\\LibreOffice\\program\\soffice.exe"`. GUI udostępnia osobny przycisk „Eksportuj PDF (LibreOffice)” i wymaga wcześniej zapisania ręcznych poprawek. LibreOffice **nie jest częścią obecnego rozwojowego EXE**; bez zainstalowanego LibreOffice eksport PDF zostaje odmówiony z komunikatem, a dotychczasowe pliki pozostają nienaruszone.

Program najpierw weryfikuje zgodność notatek z transkrypcją, tworzy DOCX w pamięci, uruchamia lokalny LibreOffice bez powłoki z odseparowanym profilem w katalogu tymczasowym, sprawdza wynik PDF i dopiero potem atomowo zapisuje `exports/notes-basic.pdf`. Dokument wejściowy i profil tymczasowy są usuwane; nie ma automatycznego pobierania dodatkowego oprogramowania. Narzędzie nie gwarantuje braku własnych mechanizmów sieciowych zewnętrznej instalacji LibreOffice.

Regresje obejmują odmowę uszkodzonego PDF, zachowanie poprzednich eksportów i faktyczny odczyt polskich cytatów z wyjściowego PDF w LibreOffice/Poppler na Ubuntu. To lokalny opcjonalny eksport, nie uniwersalny niezależny od środowiska generator PDF ani fizyczny odbiór Windows. VN-02 pozostaje W_TRAKCIE.

## Nagłówki z powtarzających się słów źródłowych (08.11.2026)

Notatka podstawowa zachowuje podział czasowy (np. `Fragment 0–1 min`), a gdy w **co najmniej dwóch wybranych cytatach** powtarzają się te same słowa, dopisuje maksymalnie trzy takie słowa do nagłówka (np. `Fragment 0–1 min · DHCP adres`). Nazwy są wyłącznie słowami widocznymi w wypowiedziach, z usuniętą interpunkcją i znacznikami; żaden model językowy nie tworzy nowych twierdzeń. Jeśli brak powtarzających się terminów, nagłówek pozostaje czasowy.

Podczas regeneracji po ręcznej korekcie transkrypcji nagłówki są obliczane ponownie według tej samej reguły, w oparciu o aktualne cytaty. Poprzednia wersja notatki i ręczne poprawki zachowują dotychczasową ochronę. Weryfikację zapewniają testy zgodności wersji, źródłowych czasów, słów powtarzanych oraz tekstu potencjalnie niebezpiecznego dla Markdown.

**To heurystyczne słowa kluczowe, a nie semantyczny tytuł czy podsumowanie**; nie stanowią dowodu poprawności rozpoznania mowy ani ręcznej oceny jakości wykładu. VN-02 pozostaje W_TRAKCIE.


## Jedna operacja tworzenia notatki naraz (12.11.2026)

Pierwsze tworzenie \`notes.json\` i \`notes-edits.json\` korzysta teraz z **tej samej lokalnej blokady \`.notes.lock\`**, z której korzystają ręczne poprawki i operacje historii. Zapobiega to sytuacji, w której dwa równoległe generowania przejdą weryfikację „notatka jeszcze nie istnieje” i nadpiszą swoje pliki. Druga próba jest odrzucana bez modyfikowania danych. Błąd zapisu zwalnia blokadę i zachowuje dotychczasowe dane; po przerwanym pierwszym zapisie zachowano świadome odzyskiwanie wyłącznie pustego dziennika poprawek. Zamknięcie procesu przez system może pozostawić blokadę na dysku: użyć istniejących \`notes-lock-status\` / \`notes-lock-recover --confirm\` dopiero po sprawdzeniu nieaktywności procesu, a nie usuwać blokady automatycznie. Potwierdzenie syntetycznymi testami współbieżności nie jest fizycznym odbiorem Windows.

## Ochrona właściciela blokady notatek (12.11.2026)

Wszystkie operacje notatek, które korzystają z `.notes.lock` (utworzenie, edycja ręczna, regeneracja, przywracanie wersji i jawny odzysk przerwanej transakcji), zapamiętują tożsamość utworzonego pliku blokady. Przy zakończeniu usuwają go tylko wtedy, gdy ścieżka nadal wskazuje na ten sam plik na tym samym urządzeniu. Jeśli inny proces lub administrator usunął blokadę i podmienił ją na nową, operacja nie usuwa cudzego pliku blokady. W tej sytuacji należy ręcznie zbadać stan projektu; test techniczny symuluje taką podmianę. To ochrona przy zwalnianiu, a nie pełna obrona przed zewnętrznym procesem nieprzestrzegającym protokołu blokowania.

## Zgodność decyzji przy eksporcie notatek AI — 12.11.2026

Podczas eksportowania zatwierdzonych twierdzeń szkicu aplikacja ponownie sprawdza **pełny zestaw decyzji** (każdą zgodę/odrzucenie, notatkę recenzenta, manifest oraz źródłowy szkic), zamiast porównywać wyłącznie liczbę twierdzeń zatwierdzonych i odrzuconych. Wcześniej podmiana dwóch decyzji między odczytami mogła pozostawić te same liczniki, a wynik zawierałby twierdzenia zatwierdzone w nieaktualnej wersji rejestru. Obecnie taki eksport jest wstrzymywany bez zapisywania pliku. Testy symulują podmianę dwóch decyzji oraz zmianę notatki recenzenta po pierwszym odczycie. Nie jest to dowód prawdziwości twierdzeń ani tożsamości człowieka; decyzje są deklaracjami użytkownika, a niekooperujący proces zewnętrzny nadal może wykonać zmianę po ostatniej weryfikacji.
