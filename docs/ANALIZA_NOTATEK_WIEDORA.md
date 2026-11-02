# Analiza aplikacji „Notatki” Wiedora

Źródło: `testowyemailaplikacja-spec/Constant_app`, gałąź `develop`, commit `dae698a2a08a29345f4bbda607af49d81b54e03d`. Kontrola kodu i dokumentacji: 2026-11-02. **Analiza nie oznacza testów rzeczywistej aplikacji Windows.**

**Zakres:** moduł `apps/notatki/`, a nie `apps/konwerter/`. Konwerter pozostaje oddzielnym produktem.

## Co już istnieje w aplikacji Notatki

- Transkrypcja mowy 1:1 za pomocą Whisper tiny/base w Web Worker, lokalnie w przeglądarce; model i biblioteki są pobierane z CDN/Hugging Face przy pierwszym użyciu.
- Import nagrań audio/wideo oraz ścieżka strumieniowa dla długich plików; dokładna lista kodeków zależy od środowiska przeglądarki.
- Nagrywanie mikrofonu i dźwięku systemowego/karty przy zgodzie użytkownika. Krótkie fragmenty służą do późniejszej transkrypcji.
- Kolejka, postęp, anulowanie i wznowienie, lokalne nagrania w IndexedDB, edycja transkrypcji i eksport tekstu.
- Opracowywanie podstawowych i zaawansowanych notatek **jeszcze nie działa** — jest osobnym celem Video Notes.
- Logowanie, retencja gotowych TXT i synchronizacja konta w Wiedora są odrębną integracją serwerową; nie należy uzależniać od nich programu desktopowego.

## Elementy referencyjne

| Plik | Wartość dla Video Notes | Co wymaga zmiany |
| --- | --- | --- |
| `transcript-core.js` | reguły łączenia segmentów | niezależne testy i kontrakt czasu |
| `streamed-media.js` | podejście odcinkowe do długich nagrań | natywne dekodowanie plików OBS na Windows |
| `local-transcription.js` | kolejka, postęp, obsługa przerwań | oddzielić logikę od DOM/Workera |
| `whisper-worker.js` | lokalne ASR i fallback | w pełni lokalny model i runtime, bez CDN |
| `recording-session.js` | fragmenty nagrywania i ochrona przed utratą materiału | API urządzeń i plików desktopowych |
| `recording-store.js` | trwałość i usuwanie nagrań | zapis na dysk zamiast IndexedDB |
| `index.html`, `notatki.js`, `notatki.css` | układ UI i obsługa użytkownika | usunięcie zależności portalowych, UX Windows |

## Szacowana trudność realizacji

**Średnia:** pierwszy import pliku OBS, audio przez lokalny FFmpeg, transkrypcja i eksport TXT/SRT. Przetwarzanie wielogodzinne i obsługa wznowień podnoszą trudność.

**Średnia–wysoka:** notatki podstawowe generowane lokalnym modelem — potrzebna kontrola zgodności ze źródłem, edycja i praca bez halucynacji.

**Wysoka:** notatki zaawansowane z podziałem na zagadnienia, czasami, terminologią i ewentualnym OCR slajdów — wymagają osobnych testów jakości i pamięci sprzętowej.

**Średnia–wysoka:** mikrofon i inne źródła na żywo — uprawnienia systemu, sterowniki, przechwytywanie/łączenie ścieżek, niezawodny zapis.

**Wysoka integracyjnie:** stabilna dystrybucja Windows offline (modele, instalator, licencje, aktualizacje, zabezpieczenia); osobna wersja WWW do wpięcia w Wiedora.

## Rekomendacja architektoniczna

Najpierw wykonać VN-00 i VN-01: długi materiał OBS → plik audio/odcinki → rozpoznanie słów ze znacznikami czasu → edycja → eksport. Dopiero potem generować notatki. Nie przenosić kodu istniejącej przeglądarkowej aplikacji wprost do gotowego Windows; dzielić i adaptować sprawdzone mechanizmy.

**Konwerter** ma nadal własny zakres: konwersje dokumentów, obrazów, PDF i multimedia. Video Notes wykonuje jedynie techniczne operacje przygotowania dźwięku pod transkrypcję.
