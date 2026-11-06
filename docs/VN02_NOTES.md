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
