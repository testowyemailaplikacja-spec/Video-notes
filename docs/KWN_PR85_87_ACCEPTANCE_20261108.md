# KWN — zweryfikowany stan po PR #85–87 (08.11.2026)

Repo: `testowyemailaplikacja-spec/Video-notes`, gałąź wdrożeniowa `develop`. **NIE** zmieniano `main`, `Constant_app`, Netlify ani Supabase.

| PR | Funkcja w `develop` | Dowód automatyczny | Pozostała bramka |
| --- | --- | --- | --- |
| [#85](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/85) | Bezpieczne poprawki WWW → desktop, podgląd i `--apply`, ochrona ASR | 42496562215 / 42496562164 / 42496562085 — 7/7 jobs PASS | Nie jest pełną integracją Wiedora ani transkrypcją w WWW |
| [#86](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/86) | Inwentarz SPDX 2.3 prywatnego bundle, SHA-256 i NOASSERTION | 42496858013 / 42496858049 / 42496858068 — 7/7 jobs PASS | Bez oceny licencji, antywirusa, podpisu i publicznej dystrybucji |
| [#87](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/87) | Offline `doctor`: FFmpeg/FFprobe, hash modelu, ścieżki audio i dysk | 42497172591 / 42497172589 / 42497172532 — 7/7 jobs PASS | Bez próby ASR na naturalnej mowie lub fizycznego Windows |

Suma: **3 PR scalone, 21/21 zarejestrowanych prac CI PASS** (różne pakiety testów mogą nakładać się zakresowo; to nie jest liczba unikalnych testów). 0/9 formalnych etapów odebranych. Testy runnerów Windows nie stanowią fizycznego testu urządzeń USB ani próby offline na komputerze docelowym.

## Weryfikacja przed odbiorem pozostałych etapów

| Etap | Niezbędny dowód, którego nadal brak |
| --- | --- |
| VN-00 | Legalne nagrania mowy PL/EN, ręczna referencja, WER/CER, RAM i czas na modelu docelowym, zatwierdzone licencje |
| VN-01 | Pełny MP4/MKV z OBS i rzeczywisty model ASR; rzeczywiste 2h, przerwanie, restart i pamięć na Windows offline |
| VN-02 | Ocena przez człowieka semantycznych notatek dla realnych wykładów, kontrola faktów i wersji |
| VN-03 | Sprawdzone materiały CCNA i slajdy, lokalna synteza semantyczna, OCR jako odrębna bramka, ręczny odbiór DOCX/PDF |
| VN-04 | Fizyczny mikrofon Windows, 2h, pauza/wznowienie, odłączenie, awaria i odzysk |
| VN-05 | Faktyczne DirectShow loopback i mikrofon, zgody, synchronizacja i błędy urządzeń |
| VN-06 | Kompletna instalacja offline na czystym Windows z prawnie dopuszczonym modelem/FFmpeg, AV, SBOM po audycie, podpis lub jawna polityka braku podpisu |
| VN-07 | Oddzielnie autoryzowana integracja jako moduł beta Wiedora, izolacja, regresja hosta i rzeczywisty odbiór Chrome/Edge/Firefox z dostępnością |
| VN-08 | Opcjonalne prace mobilne dopiero po stabilizacji Windows |

**Zasada zamknięcia:** kryterium DONE tylko po wykazaniu wykonania i kompletnego, możliwego do niezależnego sprawdzenia dowodu. Brak sprzętu/modelu/nagrań należy raportować NOT_RUN, a nie PASS. Produkcyjna publikacja i dane użytkowników są poza obecnym zleceniem.
