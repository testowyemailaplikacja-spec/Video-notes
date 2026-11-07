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

## Przywracanie po awarii także w GUI oraz test prawdziwych widżetów Tk (08.11.2026)

Jeśli panel „Notatka podstawowa” wykryje dziennik przerwanej aktualizacji, wyświetli osobne okno potwierdzenia odzyskania. Ostrzega przed równoczesną pracą na katalogu i sugeruje zachowanie kopii. Odmowa nic nie zmienia. Po świadomym potwierdzeniu uruchamia bezpieczne `recover_interrupted_note_update(confirm=True)`, pokazuje wynik i otwiera notatkę ponownie; jeśli cytaty są nieaktualne, pozostaje dotychczasowa niezależna zgoda na regenerację ze źródła.

Do CI dodano osobny test interfejsu w **rzeczywistych widżetach Tkinter** uruchamianych na wirtualnym ekranie Xvfb (`scripts/gui_headless_test.py`, workflow `vn-tk-headless.yml`). Scenariusze testowe: otwieranie i przywrócenie wersji przez przyciski, odmowa i zgoda na odzyskanie przerwanego zapisu, ochrona szkicu przy wyborze innego punktu. Dialogi potwierdzające są zastąpione kontrolowanymi odpowiedziami testowymi; reszta elementów Tk działa w rzeczywistym interpreterze i ekranie wirtualnym.

Nie jest to weryfikacja fizycznego Windows, obsługi czytnika ekranowego ani pełny test ergonomii człowieka. VN-02 pozostaje W_TRAKCIE.

## Bezpieczne zdjęcie osieroconej blokady notatek (08.11.2026)

Wcześniejsze wersje programu tworzyły pusty `.notes.lock`, więc po awarii nie można było niezależnie ustalić właściciela. Nowe blokady edycji, regeneracji, przywracania i odzyskiwania przechowują PID bieżącego procesu w postaci `pid=12345` i są utrwalane. Obecność blokady nie oznacza automatycznie awarii: może chronić aktywne zapisy.

Najpierw zamknij wszystkie kopie programu korzystające z projektu i sprawdź status:

    python -m videonotes notes-lock-status KATALOG_PROJEKTU

Tylko gdy status jest `stale` (zweryfikowano martwy PID), można świadomie usunąć *sam plik blokady*:

    python -m videonotes notes-lock-recover KATALOG_PROJEKTU --confirm

Program ponownie sprawdza PID, zawartość i tożsamość pliku przed usunięciem. Nie usuwa blokad `active`, `unknown`, `invalid`, dowiązań symbolicznych ani dawnych pustych blokad bez informacji o procesie; nie używa destrukcyjnego sygnału Windows. Jeśli istnieje `.notes-transaction.json`, osobnym krokiem jest `notes-recover KATALOG_PROJEKTU --confirm` po sprawdzeniu danych. Nie usuwać ręcznie blokady aktywnego procesu. Wszystkie decyzje odbywają się lokalnie; to nadal nie jest fizyczny test awarii zasilania.
