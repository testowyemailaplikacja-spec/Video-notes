# VN-02 — odtwarzanie wersji notatek i zachowanie ręcznej pracy

**Data:** 2026-11-06. **Status:** kod w PR, etap VN-02 nadal W TRAKCIE.

Dotychczas po poprawieniu transkrypcji notatka stawała się nieaktualna i jej eksport był blokowany. Teraz można ją ponownie zbudować bez ręcznego kopiowania wcześniej wpisanych uwag.

## Polecenia

```bash
python -m videonotes notes-regenerate KATALOG_PROJEKTU --window-minutes 5 --points 6
python -m videonotes notes-history KATALOG_PROJEKTU
python -m videonotes notes-restore KATALOG_PROJEKTU --revision IDENTYFIKATOR
```

Funkcja jest także widoczna w GUI „Notatka podstawowa”. Po zmianie transkrypcji użytkownik dostaje propozycję odbudowy, a w otwartym panelu jest przycisk „Odbuduj notatkę z historią”.

## Gwarancje

Przy regeneracji program tworzy najpierw lokalny snapshot `notes-history/<uuid>.json` zawierający poprzednie `notes.json` oraz `notes-edits.json`, chronione ich SHA-256. Ręczne poprawki przypisane do segmentów, które nadal występują w transkrypcji, przechodzą do nowej notatki. Segmenty z poprawkami pozostają widoczne nawet wtedy, gdy nowa selekcja punktów inaczej dobrałaby cytaty. Jeśli segment został usunięty, jego poprawka pozostaje tylko w historii, a wynik jawnie podaje liczbę takich nieprzeniesionych uwag.

Przywrócenie starej wersji wymaga, by jej transkrypcja źródłowa nadal odpowiadała aktualnej. Nie można przywrócić nieaktualnych cytatów jako obowiązujących. Poprzednia aktywna wersja również jest archiwizowana przed restore. Blokada `.notes.lock` chroni regenerację przed równoległą regeneracją, ale pełne transakcyjne zabezpieczenie każdej edycji oraz wszystkich przypadków awarii zasilania nadal wymaga prac.

Całość jest lokalna, bez modeli językowych, chmury, konta i nagrań w repozytorium. Żadne etapy nie uzyskują statusu DONE wyłącznie na podstawie tych testów.

## Otwarte

Brak pełnego semantycznego streszczania, testów na prawdziwych wykładach, kontroli jakości przez człowieka oraz instalatora Windows. Historię należy objąć docelową polityką retencji i ograniczeniem rozmiaru (obecnie 1000 wersji).

## Historia i przywracanie przez okno programu (07.11.2026)

W oknie „Notatka podstawowa” przycisk **Historia i przywracanie wersji** pokazuje lokalne snapshoty od najnowszego, z datą UTC, liczbą ręcznych poprawek i pełnym identyfikatorem. Użytkownik wybiera konkretną wersję i oddzielnie potwierdza przywrócenie. Program korzysta z istniejącej, sprawdzającej zgodność cytatów funkcji restore; przed przywróceniem aktualna notatka oraz jej poprawki są kopiowane do historii. Nie można przywrócić notatki ze źródła, które od czasu zapisania wersji zostało zmienione.

Edytor chroni również **niezapisany tekst**: przejście do innego punktu pyta o świadome odrzucenie szkicu (odmowa zachowuje tekst i poprzedni wybór), a przywracanie, regeneracja, eksport DOCX i zamknięcie okna nie porzucają szkicu bez zgody. Nowy backend historii wykrywa nieprawidłowe daty snapshotów i dowiązania symboliczne katalogu historii. Walidacja odwołania cytatu wymaga teraz identyfikatora `quote-<segment_id>` i całkowitego znacznika czasu, nie wartości logicznej.

Testy automatyczne obejmują kolejność i datę snapshotów, ich manipulację i dowiązania, zgodność ID cytatów oraz wcześniejsze scenariusze restore/undo. **Pełny test interakcji z oknem na fizycznym Windows nadal jest potrzebny**; sam build Windows EXE i testy backendu nie dowodzą działania klikania ani odporności na zaniki zasilania w trakcie przywracania. VN-02 pozostaje W_TRAKCIE.

## Dziennik przerwanej aktualizacji dwóch plików (08.11.2026)

Regeneracja i przywracanie wersji zmieniają parę `notes.json` oraz `notes-edits.json`. Pojedynczy zapis pliku jest atomowy, ale oba pliki nie tworzą jednej transakcji dyskowej. Przed modyfikacją program najpierw zapisuje pełną poprzednią wersję w `notes-history`, a następnie lokalny dziennik `.notes-transaction.json` zawierający identyfikator snapshotu oraz odciski SHA-256 starej i nowej pary. Dziennik nie zawiera tekstu wykładu, lecz pozostaje w katalogu projektu. Po zapisaniu obu plików jest usuwany.

Jeżeli program zostanie przerwany w połowie, kolejne edycje, eksport notatek, backup i regeneracja są blokowane do rozstrzygnięcia stanu. Na komputerze, na którym nie działa już żaden proces edytujący projekt, wykonaj:

    python -m videonotes notes-recover KATALOG_PROJEKTU --confirm

Polecenie porównuje *obie aktualne wersje plików* ze znanymi hashami. Jeśli oba odpowiadają nowej parze, pozostawia ukończony wynik. Jeśli oba odpowiadają starej parze, nie przepisuje niczego. Jeśli para jest częściowa, przywraca dokładnie starą parę ze sprawdzonego snapshotu. Jeżeli po awarii ktoś zapisał nową ręczną poprawkę albo dziennik lub historia są zmodyfikowane, program **odmawia nadpisania danych** i zachowuje stan do ręcznej kontroli. Odzyskanie jest jawne, nie automatyczne.

Ręczne `notes-edit` również wykorzystuje wspólną blokadę `.notes.lock`, co chroni przed zapisaniem poprawki pomiędzy dwoma plikami regeneracji. Jeśli po fizycznej awarii systemu pozostała `.notes.lock`, funkcja odzyskiwania nie usuwa jej automatycznie. Należy upewnić się, że żaden proces nie zapisuje notatek, zachować kopię plików i dopiero ręcznie sprawdzić/usunąć osieroconą blokadę. Program nie potrafi samodzielnie zweryfikować żywego Windows procesu na podstawie starego pustego pliku blokady.

To testowane w automatycznych regresjach przerwanie kolejności zapisów, a **nie gwarancja pełnej odporności na utratę zasilania lub awarię dysku**. Końcowy odbiór wymaga prób sprzętowych, kontroli odczytu i rozpatrzenia trwałości metadanych katalogu po `fsync`. VN-02 pozostaje W_TRAKCIE.
