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

## Automatyczna próba 121-minutowego nagrania (08.11.2026)

`scripts/real_2h_media_smoke.py` generuje prawdziwe 121-minutowe OGG/Opus bez prywatnych danych, faktycznie dekoduje dźwięk FFmpeg w 61 fragmentach, przerywa przetwarzanie po 12 zapisanych checkpointach i następnie bez powtórzeń wznawia pozostałe. Dodatkowo przechodzi całą ścieżkę `ukończona transkrypcja → przewodnik do nauki → MD/JSON/DOCX`, sprawdzając zgodność każdej wypowiedzi i znacznika czasu, kompletność 61 ID, brak duplikatów i nienaruszony plik źródłowy.

**Ważne:** wejście audio jest syntetycznym tonem 440 Hz, a zwracane „rozpoznania” pochodzą z jawnej atrapy, więc test ten **nie mierzy jakości ani szybkości prawdziwego modelu ASR**. Status będzie odnotowany jako PASS wyłącznie po rzeczywistym zielonym przebiegu GitHub Actions. Nie zastępuje oceny wykładu przez człowieka ani testu sprzętowego Windows.

## Niezależna kontrola cytatów (08.11.2026)

Po zapisaniu `exports/notes-study.json` można sprawdzić zgodność **całego JSON, wszystkich cytatów, czasów, pojęć, etykiet i numerów sekcji z aktualną lokalną transkrypcją**:

```powershell
python -m videonotes study-verify C:\\Notatki\\wyklad-001
python -m videonotes study-verify C:\\Notatki\\wyklad-001 --file C:\\Kopie\\notes-study.json
```

W oknie przewodnika jest też przycisk **„Sprawdź źródła”**. Weryfikacja na nowo, deterministycznie buduje oczekiwaną reprezentację z poprawionej transkrypcji i porównuje ją z zachowanym plikiem. Przy odmiennej treści, zmyślonym fragmencie, zmienionym czasie, innej klasyfikacji, brakującym cytacie, uszkodzeniu struktury lub nieaktualnej transkrypcji odmówi potwierdzenia. Nie usuwa, nie naprawia i nie nadpisuje dokumentu. Odrzuca także dowiązania symboliczne zamiast podążać za cudzym plikiem.

Wynik pozytywny zawiera jedynie `verified`, liczbę części/cytatów, `source_sha256` i `document_sha256` — **nie zawiera słów z nagrania**. Służy do lokalnej kontroli, bez udziału sieci. Potwierdza dokładne pochodzenie JSON z aktualnej transkrypcji, **nie to, że ASR usłyszał prawdziwe słowa albo że są one faktograficznie poprawne**. Weryfikator nie podpisuje kryptograficznie dokumentu i nie sprawdza niezależnie plików MD/DOCX/PDF: ich bezpieczeństwo zależy od wcześniejszego generowania z zaufanego JSON oraz kontroli eksportu.
