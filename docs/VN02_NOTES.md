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
