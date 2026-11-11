# VN-07 — pakiet integracji Wiedora beta i odbiór kontraktu 11.11.2026

**Status:** KWN/Video-notes źródło `develop`, Wiedora `develop` commit [88b01188639213ce8a959f857f796fd690635198](https://github.com/testowyemailaplikacja-spec/Constant_app/commit/88b01188639213ce8a959f857f796fd690635198) (PR [#189](https://github.com/testowyemailaplikacja-spec/Constant_app/pull/189)); Netlify `develop` deploy `6af48486b6e205574befb7a5` READY (11.11). Produkcyjny `main` i legacy `/apps/notatki/` nietknięte.

## Faktycznie wykonana integracja

- Jeden wydzielony adres `/apps/notatki-web/video-notes/` z linkiem w osobnej `/apps/notatki-web/` i powrotem do KWN. Odrębny SW / cache, CSP `connect-src 'none'`, noindex, brak telemetrii w samym adapterze.
- Źródła z przypiętego commita Video-notes `818a29e79642013ebd137e445222fb8c1ef9a552`, cztery zasoby statyczne. Brak importu desktopowego Python/ASR/FFmpeg/Windows do WWW.
- Źródłowy kontrakt `videonotes-export-v1` oraz `videonotes-web-corrections-v1`; brak modyfikacji oryginalnego pliku. Wrażliwe notatki nie trafiały do testów.
- 11/11 izolowanych asercji V8 nad pobranymi skryptami; live Chromium Preview: import, edycja, blokada niezapisanych zmian, wyszukiwarka, przywrócenie, odmowa uszkodzonego JSON bez utraty bieżącej sesji; 50 000 syntetycznych segmentów / 5,3 MB z wyszukaniem końcowego segmentu PASS.
- Live Chromium na właściwym `develop`: build-info SHA = `88b01188639213ce8a959f857f796fd690635198`, import+edycja PASS, SW cache v19 i przejście strony offline po instalacji SW PASS; `main` nowa ścieżka 404, legacy 200. Trzy ekrany 360/768/1280 bez horizontal overflow, `X-Robots-Tag` noindex.

## Co wolno uznać i czego nie wolno

`VN-07-01 DONE`: statyczny kontrakt i izolacja opracowane i przetestowane w V8 i prawdziwym Chromium hosta; nie stanowi końcowej certyfikacji całego etapu WEB-01.

`VN-07-04 DONE`: wybrano dopuszczoną przez zadanie alternatywę — **jawnie ograniczony zakres beta** zamiast nieukończonego ASR i nagrywania w WWW. Ograniczenie opisują banner, UI i dokumentacja; nie twierdzić, że interfejs WWW transkrybuje nagrania.

`VN-07-05 IN_PROGRESS`: część host/Netlify wdrożona, lecz wymagane zależności i pełna regresja nieukończone. GitHub Actions PR #189 wystartowały, lecz oba joby kończyły się natychmiast bez wykonanych kroków (runner 0). Fizyczny zapis pobranych plików w Cloud Browser był zablokowany, więc nie oznaczaj download E2E PASS; test w V8 dowodzi poprawnych wygenerowanych treści, nie zachowanego pliku. Nie sprawdzono ręcznie Chrome/Edge/Firefox na fizycznym Windows, NVDA, legal/licencji, modeli/ASR, 2h audio, zwolnienia ograniczenia „Tylko KWN”. Stąd etap VN-07 pozostaje W_TRAKCIE.

## Następne kroki

1. Przywrócić działający runner i wykonać `npm run verify`, `npm run verify:full`, KWN Node/TS i browser w dedykowanym CI.
2. Rzeczywisty fizyczny Windows: file:// Chrome/Edge/Firefox; klawiatura, NVDA, pobranie wszystkich formatów i import poprawek do desktop `--apply`; test negatywny w przeglądarce.
3. Formalne odbiory VN-00–06 i legal/licencje; po nich HOST-01 i ewentualne odblokowanie testów platformy tylko za zgodą właściciela.

Repo robocze Video-notes pozostaje właścicielem przyszłych zmian produktu. Integracje do Wiedory mają być rzadkimi, przypiętymi do SHA pakietami.

## Paczka export-hardening 11.11.2026

Po źródłowych PR Video-notes #109 i #110 wdrożono osobną synchronizację [Constant_app #193](https://github.com/testowyemailaplikacja-spec/Constant_app/pull/193) do `develop`, commit `ce7a96ff97ed4faf16f13729029fa1d9a7f661ed`; Netlify deploy `6af494c6928af7c9f72d3786` READY. Dostarczono limity TXT/SRT/VTT/JSON ≤64 MiB, JSON poprawek ≤20 MiB i SW cache v20, przy zachowaniu legacy i main. Pinned źródło: Video-notes develop `18edfba82303dae8c6ccd2d5987eb76117bca3c0`. Netlify preview READY, źródło 10/10 kontroli V8 PASS. **Nie** wykonano pełnego `verify:full` hosta: GitHub Jobs kończą się przed krokami. Na źródle testy Windows i przeglądarek PASS, Ubuntu FFmpeg nie mógł zainstalować się przez DNS i timeout, więc pełna regresja NOT_RUN/FAIL infrastrukturalny. Fizyczna Windows/human/LEGAL nadal NOT_RUN.
