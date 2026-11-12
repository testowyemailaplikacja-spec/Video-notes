# KWN — odbiór techniczny czterech wdrożeń PR #144–147 (12.11.2026)

Repozytorium źródłowe: `testowyemailaplikacja-spec/Video-notes`. Gałąź docelowa: `develop`. Cztery pakiety kodowe zostały **rzeczywiście scalone**, przetestowane na końcowych commitach gałęzi PR i udokumentowane. To odbiór **konkretnych poprawek**, nie całych etapów VN.

| Zakres | Scalone PR / commit squash | Faktyczny rezultat | GitHub Actions (final head) |
|---|---|---|---|
| VN-03, indeks OCR–mowa | [PR #144](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/144), `43f5beb475503bac632784553934724a65e19a5d` | Eksport powiązań slajdu do Markdown sprawdza hash rzeczywiście odczytanego indeksu i przed zapisem ponownie weryfikuje pełny indeks, OCR oraz transkrypcję. Testy symulują podmianę JSON na dysku i podmianę w pamięci. | **7/7 PASS**, [źródło testów](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43227197200) |
| VN-01, eksport transkrypcji | [PR #145](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/145), `c73fc9525dbe647ea03862e2da7e5a16720306bc` | TXT/SRT/VTT/JSON tworzone pod wspólną blokadą ręcznych poprawek; dodatkowy drugi odczyt i porównanie wszystkich formatów przed nadpisaniem plików. Test kolizji zachowuje stare eksporty. | **7/7 PASS**, [źródło testów](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43227638670) |
| VN-02, odsłuch źródła | [PR #146](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/146), `fdbe0540fac6a085b293689e4ae838ef56bfc5e5` | Po ekstrakcji WAV sprawdzenie aktualności projektu i segmentów/kodów czasu przed FFplay; testy odrzucają równoległą podmianę transkrypcji i ustawień. | **7/7 PASS**, [źródło testów](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43228315099) |
| VN-02/VN-03, PDF i konspekt | [PR #147](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/147), `c9796312956b8c63525492e4cd4a68e99f216cd7` | Notatka podstawowa i zaawansowany konspekt są ponownie walidowane po konwersji LibreOffice, zanim nadpiszą starsze PDF, Markdown, JSON i DOCX. Testy wymuszają ręczne edycje podczas konwersji. | **11/11 PASS**, w tym [rzeczywisty LibreOffice na Linux](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43228786806) |

**Suma: 32/32 końcowych zadań CI PASS na finalnych commitach czterech PR.** To sumowanie zadań GitHub Actions, **nie** formalnych kryteriów KWN. Hostowane testy obejmują Python Linux/Windows, Firefox/Chromium/Chrome/Edge file://, GUI, wybrane rzeczywiste FFmpeg i LibreOffice oraz w odpowiednich workflow syntetyczne długie nagrania i whisper.cpp na syntetycznym PL/EN TTS. Nie oznacza to fizycznego odbioru na komputerze właściciela.

## Diagnostyka awarii CI

Pierwsze uruchomienie Chromium w PR #144 zgłosiło `Chromium CDP port unavailable` i błędy DBus na hostowanym runnerze **przed wykonaniem testu aplikacji**. Nie zaliczono tego przebiegu jako sukcesu. Uruchomiono ponownie konkretny failed job; ponowiona próba zakończyła się PASS, dzięki czemu końcowa ocena PR #144 wynosi 7/7 PASS. Brak zmian w module Chromium w ramach tego PR.

## Czego nie odebrano

Status zapisany w `docs/VN_STATUS.json` pozostaje **0/9 VN etapów DONE**, 8 W_TRAKCIE, 1 PLANOWANE. `docs/VN_MICROTASKS.json`: 2/37 DONE, 1 IN_PROGRESS, 34 TODO. Nie przenosić historycznych 189 kryteriów platformy do licznika 37.

Do pełnych bramek wciąż potrzebne: legalne naturalne nagrania PL/EN z ręcznym wzorcem WER/CER, pomiary dwóch silników/modeli na docelowym Windows, fizyczny mikrofon/loopback i nagranie 2 h+, sprawdzenie offline/instalatora/AV/licencji, rzeczywisty GGUF i ludzka kontrola faktów, finalny odbiór beta Wiedora oraz test czytnika ekranu. Powtórna walidacja źródeł **ogranicza** wyścigi, lecz nie jest transakcją obejmującą dowolne niekooperujące procesy zewnętrzne. Publikacja kilku plików nadal nie jest pojedynczą operacją atomową w razie przerwania dysku po rozpoczęciu zapisu.

Nie zmieniono `testowyemailaplikacja-spec/Constant_app`, Netlify, Supabase, produkcyjnego `main`, statusu BETA ani granic testowania innych zespołów. Nie przesyłano ani nie publikowano prywatnych nagrań, modeli ani sekretów.
