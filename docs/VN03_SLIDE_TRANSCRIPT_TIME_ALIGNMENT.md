# VN-03B — indeks slajdów i transkrypcji według czasu

Wersja desktopowa umie utworzyć lokalny indeks łączący **żądane znaczniki czasu OCR** z **najbliższymi w czasie segmentami poprawionej transkrypcji**. Nie jest to rozumienie treści, automatyczne sprawdzanie faktów ani dowód, że prowadzący omawiał w tym czasie dokładnie ten slajd. Klatka nie ma zweryfikowanego rzeczywistego PTS obrazu.

Po utworzeniu raportu OCR `slide-ocr` użyj:

```powershell
python -m videonotes slide-align C:\Notatki\projekt --ocr C:\Notatki\slajdy.json --output C:\Notatki\indeks-slajdow.json --max-gap-seconds 45
python -m videonotes slide-align-verify C:\Notatki\projekt --ocr C:\Notatki\slajdy.json --file C:\Notatki\indeks-slajdow.json
python -m videonotes slide-align-md C:\Notatki\projekt --ocr C:\Notatki\slajdy.json --file C:\Notatki\indeks-slajdow.json --output C:\Notatki\indeks-slajdow.md
```

W GUI wybierz **„OCR slajdów i lokalne szkice AI”**, następnie **„Powiąż OCR z wypowiedziami według czasu”**. Wynik jest oddzielnym plikiem bez nadpisywania notatek. Każda klatka zawiera SHA obrazu, tekst OCR i segment mowy (jeśli najbliższy występuje w dopuszczonym przedziale czasowym), odległość w milisekundach, identyfikator i dokładny cytat segmentu. Przy braku wypowiedzi w zadanym limicie program jawnie zapisuje `null`, a nie dopisuje hipotetyczny komentarz.

`slide-align-verify` odtwarza deterministyczny indeks na podstawie aktualnych oryginalnych danych. Wykrywa zmieniony plik OCR, zmienione poprawki transkrypcji i fałszywe źródła. **Nie może potwierdzić poprawności rozpoznanych napisów ani zgodności ich znaczenia z mową**. Żadnych skanów, notatek i nagrań nie wysyła na zewnątrz; eksport Markdown traktuje nieufne teksty jako zwykłe dosłowne bloki, nie aktywny HTML.


## Wiele nakładających się wypowiedzi — korekta indeksowania 12.11.2026

Poprzedni algorytm oglądał tylko dwa sąsiadujące według **początku** segmenty. Dla długiej wypowiedzi 00:00–00:20 i późniejszych krótkich wypowiedzi potrafił przypisać klatkę z 00:15 do odległego krótkiego fragmentu, a nie do wypowiedzi obejmującej tę chwilę. To ważne zwłaszcza przy wielu mówcach i nakładających się zapisach.

Teraz indeks przedziałów zawiera maksimum końca w prefiksie. Wyszukiwanie binarne wybiera najwcześniejszy czasowo segment, który **naprawdę obejmuje** czas klatki; jeżeli żaden go nie obejmuje, sprawdza najbliższą zakończoną i przyszłą wypowiedź. Koszt budowy indeksu O(n), pojedyncze wyszukanie O(log n). Weryfikator ponownie buduje taki sam wynik, więc poprzednie błędne indeksy są odrzucane jako niezgodne i trzeba je utworzyć na nowo. Odbiór semantycznej zgodności slajdu i treści nadal wymaga człowieka.
