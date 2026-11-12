# VN-03B — lokalne OCR slajdów z nagrania OBS (wariant opcjonalny)

Wideo MP4/MKV/WebM/MOV ze sprawdzonego projektu KWN można analizować **wyłącznie na żądanie** narzędziami FFmpeg/FFprobe i Tesseract, instalowanymi lokalnie przez użytkownika. Aplikacja nie pobiera modeli OCR, nie przesyła klatek ani nie ingeruje w surową transkrypcję.

```powershell
python -m videonotes slide-ocr C:\\Notatki\\projekt --output C:\\Notatki\\slajdy-001.json --interval-seconds 60 --max-frames 120 --language pol+eng
python -m videonotes slide-verify C:\\Notatki\\projekt --file C:\\Notatki\\slajdy-001.json
```

Każdą klatkę zapisujemy tymczasowo jako obraz z ograniczonymi wymiarami, wykonujemy Tesseract OCR i usuwamy klatkę. Raport przechowuje tekst rozpoznany z obrazu, żądany czas pobrania klatki, SHA-256 obrazu i wyraźną flagę wymaganej weryfikacji przez człowieka. Nie jest to dowód idealnej zgodności z konkretną chwilą wideo: czas jest żądanym punktem seek, **nie dokładnym PTS przechwyconej klatki**. Domyślna analiza dotyczy maksymalnie 120 klatek, co 60 sekund; wyższy limit wymaga świadomego ustawienia.

`slide-verify` sprawdza strukturę raportu, kompletność interwałów, integralność źródłowego nagrania, ID i znaczniki czasu. **Nie** uruchamia ponownie OCR, nie ocenia poprawności tekstu na slajdzie ani nie tworzy automatycznie faktów w notatkach. Weryfikacja SHA-256 samego raportu nie oznacza podpisu, a SHA zapisanej klatki nie zapewnia możliwości jej odtworzenia po usunięciu. Wyniki OCR mogą zawierać dane poufne; nie commitujemy raportów ani nagrań do GitHub.

Testy syntetyczne sprawdzają wybór klatek, kompletność danych, niezmienność transkrypcji, odmowę nadpisania, uszkodzony film i podmianę czasu. Nie zastępują prawdziwych slajdów CCNA, oceny człowieka i realnego OCR na fizycznym Windows. Etap VN-03 pozostaje W TRAKCIE.

## Kontrola integralności obrazu podczas OCR (12.11.2026)

Silnik OCR liczy SHA-256 obrazu klatki po wyodrębnieniu jej lokalnym FFmpeg, a teraz sprawdza ten sam SHA-256 ponownie po zakończeniu odczytu przez Tesseract. Gdy obraz zostanie zmieniony, zastąpiony symlinkiem lub usunięty w trakcie OCR, aplikacja odrzuca cały raport i nie zapisuje niespójnego powiązania tekstu z klatką. Test syntetyczny zmienia obraz już po pierwszym hashowaniu. Nadal nie oznacza to, że tekst rozpoznany ze slajdu jest poprawny merytorycznie; odbiór na rzeczywistych slajdach i kontrola człowieka pozostają otwarte.
