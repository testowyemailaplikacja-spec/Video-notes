# VN-03 — rzeczywiste szablony konspektów i audyt źródeł (08.11.2026)

Dotychczas `advanced-notes --template` zmieniał głównie tytuł; układ cytatów był niemal identyczny. Teraz cztery szablony tworzą **osobne, tematyczne zestawy dokładnych wypowiedzi z transkrypcji**, przy zachowaniu istniejących rozdziałów, źródłowych czasów i bez zmiany oryginału.

## Co jest dostępne

| Szablon | Kategorie dosłownych cytatów |
|---|---|
| `lecture` — Wykład | Możliwe definicje, przykłady podane przez wykładowcę, fragmenty niepewne |
| `tutorial` — Instruktaż | Wypowiedziane kroki/komendy, wskazówki sprawdzenia wyniku, ostrzeżenia |
| `meeting` — Spotkanie | Wypowiedzi o decyzjach, zadaniach, pytaniach otwartych |
| `study` — Nauka | Pojęcia i definicje, przykłady do powtórzenia, pytania i wątpliwości |

Nazwy kategorii i dobór fragmentów to **prosta klasyfikacja po słowach występujących w transkrypcji**. Program nie stwierdza, że decyzję rzeczywiście podjęto, kroki są poprawne albo definicja prawdziwa. Wszystkie cytaty są dosłowne z uwzględnieniem ręcznych poprawek ASR i mają `segment_id`, `start_ms`, `end_ms`. Cytaty z kategorii mogą się powtarzać w części głównej, bo pomagają znaleźć ten sam fragment według różnych wskazówek.

**Połączenie z istniejącymi funkcjami:** zachowano format `videonotes-source-outline-v1` i sekcje `topics`; nowe pole `template_focus` jest dodatkową funkcją. Użytkownicy wcześniej wygenerowanych notatek mogą zachować swoje JSON/MD/DOCX jako osobną kopię. Nie zmieniono podstawowej notatki `notes-basic` ani poprawionej i surowej transkrypcji.

## Windows — interfejs

Wybierz **„Konspekt źródłowy — rozdziały i cytaty (VN-03)”**. Pojawi się okno z selektorem Wykład / Instruktaż / Spotkanie / Nauka, szczegółowością i liczbą minut w części. Przycisk „Opracuj / odśwież” aktualizuje lokalne MD/JSON, „Eksport DOCX” lub „Eksport PDF” tworzy dokument. PDF wymaga zainstalowanego lokalnie LibreOffice. **Jeśli wcześniejszy konspekt już istnieje, aplikacja pyta o zgodę przed nadpisaniem plików.** Samo otwarcie gotowego konspektu nie regeneruje go.

Przycisk **„Sprawdź źródła”** weryfikuje wszystkie cytaty, etykiety i znaczniki czasu zapisane w JSON względem aktualnej transkrypcji. Nie nadpisuje ani nie poprawia dokumentu.

## Terminal

```powershell
python -m videonotes advanced-notes C:\\Notatki\\wyklad --template tutorial --detail full --section-minutes 10 --docx
python -m videonotes advanced-verify C:\\Notatki\\wyklad
python -m videonotes advanced-notes C:\\Notatki\\spotkanie --template meeting --detail standard --section-minutes 5 --pdf
```

Pliki wynikowe: `exports/notes-advanced.md`, `notes-advanced.json`, opcjonalnie `notes-advanced.docx` i `notes-advanced.pdf`.

Ograniczenia: nie dokonuje semantycznego streszczenia ani weryfikacji faktów, nie wyciąga niezawodnie nazwisk, terminów i obowiązków, nie ocenia WER ASR. Zapisany JSON jest odtwarzany deterministycznie, ale to nie podpis cyfrowy i nie niezależna walidacja plików Word/PDF. Dla prawdziwego odbioru VN-03 wymagane są trzy próbki z naturalną mową (wykład, instruktaż techniczny, spotkanie lub nauka), ocena człowieka i kontrola układu dokumentów na fizycznym Windows.

Testy obejmują klasyfikacje PL/EN, bezpieczeństwo nieufnego HTML/Markdown, integralność źródła i poprawek, przeciwdziałanie dopisaniu fałszywego cytatu, rzeczywiste elementy Tk i Word z poprawnymi identyfikatorami. Dodatkowo job prawdziwego Whisper CPU PL/EN na syntetycznej mowie weryfikuje nowy schemat i powiązania źródłowe. Dany test jest PASS wyłącznie po zielonym przebiegu CI.
