# VN-02 / VN-03 — źródłowy przewodnik do nauki

**Data:** 08.11.2026. Repozytorium KWN: `testowyemailaplikacja-spec/Video-notes`.

## Praktyczne użycie

Po zakończeniu lokalnej transkrypcji nagrania OBS otwórz aplikację i wybierz **„Przewodnik do nauki — cytaty, pojęcia i pytania (VN-02/03)”**. Możesz wybrać długość części (5/10/15/30 min) i szczegółowość (brief/standard/full). Podgląd pokazuje spis treści oraz fragmenty słów rzeczywiście rozpoznanych w nagraniu. Przyciski oferują bezpośredni eksport do DOCX i opcjonalny PDF za pomocą *już zainstalowanego lokalnie* LibreOffice.

W terminalu:

```powershell
python -m videonotes study-guide C:\\Notatki\\wyklad-001 --section-minutes 10 --detail full --docx
python -m videonotes study-guide C:\\Notatki\\wyklad-001 --section-minutes 5 --detail standard --pdf --office "C:\\Program Files\\LibreOffice\\program\\soffice.exe"
```

Wyniki: `exports/notes-study.md`, `notes-study.json`, opcjonalnie `notes-study.docx` i `notes-study.pdf`. Nie nadpisują oryginalnej transkrypcji, ręcznych poprawek `edits.json`, notatki podstawowej ani historii jej wersji.

## Zawartość

* **Spis treści:** części czasowe z bezpiecznymi podpowiedziami powtarzających się słów, bez wymyślonych nazw rozdziałów.
* **Krótki skrót źródłowy:** pojedyncza cytowana wypowiedź, a nie wygenerowany opis. Każdy fragment zawiera stabilny ID oraz czas początku i końca.
* **Pojęcia pojawiające się wielokrotnie:** maksymalnie 4 dosłowne słowa z transkrypcji, występujące w co najmniej 2 różnych wypowiedziach; z licznością i ID pierwszego źródła.
* **Wybrane cytaty:** wybór chronologicznie rozproszonych wypowiedzi z oryginalnymi źródłami, nie dodaje nowych informacji.
* **Przykłady, możliwe definicje, pytania / niepewności:** klasyfikacja według prostych wyrażeń w cytowanych zdaniach. To podpowiedzi dla użytkownika, nie gwarancja poprawności rozpoznania ASR.

Kontrakt `videonotes-study-guide-v1` jest odrębny od `videonotes-basic-notes-v1`. Przewodnik można wygenerować ponownie w dowolnym momencie; zapisywane pliki pochodzą zawsze z **bieżących ręcznych poprawek transkrypcji** i przenoszą `source_sha256` do sprawdzenia wersji. Nie jest to edytor ręcznych zmian przewodnika; do poprawek używaj transkrypcji lub istniejącego edytora notatek podstawowych.

Wykonanie bez płatnego API, konta, serwera i bez automatycznej wysyłki danych. W przypadku niekompletnej transkrypcji lub błędu renderowania opcjonalnego DOCX/PDF eksport jest przerywany przed nadpisaniem poprzednich dokumentów. **Wiele plików wynikowych nie jest jedną atomową transakcją** i system plików może odmówić zapisu późniejszego formatu; nadal wymagane jest regularne tworzenie kopii projektu.

## Granice odbioru

Nowy przewodnik to istotny krok ku VN-02/VN-03, ale **nie jest semantycznym streszczeniem AI, rozpoznaniem znaczenia definicji, weryfikacją źródeł ani transkrypcją 1:1 bez błędów**. Udany test z syntetyczną mową TTS nie oznacza oceny przez człowieka prawdziwego wykładu. Testy fizycznego Windows, długich sesji i instalatora pozostają niezależnymi bramkami odbioru.
