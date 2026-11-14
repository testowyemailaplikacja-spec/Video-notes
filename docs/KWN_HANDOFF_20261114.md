# KWN — przekazanie rzeczywistych bramek odbiorowych po PR #196–#198

Data: 14.11.2026. Dotyczy wyłącznie `testowyemailaplikacja-spec/Video-notes` / `develop`.
Ten dokument **nie stanowi dowodu wykonania** opisanych testów. Nie zmienia statusów zadań.

## Potwierdzony zakres programowy

- PR [#196](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/196): `62f6e4ebbffb4762fd0260f36c4e0a8e3ace7341`, 7/7 końcowych kontroli CI PASS — plikowy import poprawek, ograniczony odczyt i dwukrotny SHA-256.
- PR [#197](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/197): `0dd732f3546f32a07b29152c0311a41d4e7652e1`, 9/9 końcowych kontroli CI PASS — GGUF header/path race preflight.
- PR [#198](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/198): `ffbb42aece76ba854562eec9485206184eaab70c`, 9/9 końcowych kontroli CI PASS — lokalny eksport poprawek bez nadpisania i roundtrip.
- Żaden z tych wyników nie jest realną inferencją na modelu, testem fizycznego Windows/Android/iOS, oceną faktów ani zgodą prawną na dystrybucję.

## Przygotowanie do odbioru

Na komputerze odbiorowym użyć aktualnego SHA `develop`, zachować prywatne dane poza repozytorium i utworzyć lokalny rejestr przez `scripts/vn_acceptance_evidence.py` zgodnie z [VN_MANUAL_EVIDENCE.md](VN_MANUAL_EVIDENCE.md). Pełna macierz warunków PASS / NOT_RUN: [VN_HARDWARE_ACCEPTANCE_20261107.md](VN_HARDWARE_ACCEPTANCE_20261107.md). Nie publikować modeli, wykładów, referencji, surowych zrzutów ekranu ani danych urządzeń.

| Pakiet | Kto i co wykona | Oczekiwany wynik | Prywatne dowody i warunek PASS |
| --- | --- | --- | --- |
| VN-00-01–03; VN-01-01–04 | Uprawniony tester dostarcza dwie legalne naturalne próbki PL/EN i ręczne TXT; uruchamia `scripts/asr_samples_preflight.py` i lokalne `benchmark-real` wg [REAL_ASR_LAB.md](REAL_ASR_LAB.md), na jednym PCM, z dwoma zgodnymi silnikami | WER/CER obu silników, czas i szczyt RAM, identyczny materiał wejściowy i zapisana decyzja technologiczna | SHA próbek/modeli, wersje silników, liczbowe metryki, potwierdzenie referencji przez człowieka; bez tego ASR-01/03/04 NOT_RUN |
| VN-02-01/02 | Tester z legalnym GGUF/llama-cli i naturalnym transkryptem uruchamia lokalnie `scripts/semantic_gguf_acceptance.py` wg [VN02_VN08_ACCEPTANCE_PREP_20261114.md](VN02_VN08_ACCEPTANCE_PREP_20261114.md), a następnie osoba uprawniona odsłuchuje oryginał i ocenia wszystkie twierdzenia | Cytowania odpowiadają ID/czasowi; każda teza jest zaakceptowana/odrzucona z uzasadnieniem, bez domyślnego zatwierdzania | Lokalny raport z rzeczywistej inferencji, model SHA, CPU/RAM/czas, prywatne decyzje; NOTE-01 nie jest PASS na podstawie samego nagłówka GGUF |
| VN-01-05; VN-02-03/04; VN-03-01/04 | Tester fizycznego Windows wykonuje awarie wejścia, undo/backups, OCR realnego CCNA, klikalne źródła i otwiera DOCX/PDF w Word/LibreOffice | Zachowane poprawki, jawne konflikty i źródła, poprawne rendering i brak utraty danych | Wersje programów, wyniki powtórzeń, prywatne zrzuty lub anonimizowane raporty; NOTE-02/03 i OCR odbierane tylko z rzeczywistego materiału |
| VN-04-02/03; VN-05-03 | Tester Windows nagrywa mikrofon fizyczny, sprawdza 2h+, pauzę, odłączenie, pełny dysk, przerwany WAV; osobno brak Stereo Mix i odmowę zgody | Czytelne uratowane segmenty, oryginał nietknięty; mikrofonowy fallback działa bez cichego przechwytywania | Log prób z prawdziwego urządzenia i kontrola oryginałów; MIC-01/02/MIX-02 dopiero po rzeczywistym teście |
| VN-06-01–05 | Tester Windows instalacja/upgrade/uninstall/offline; osoba uprawniona analizuje rzeczywisty SBOM, FFmpeg flags, dokładne binaria/model/licencje i dystrybucję | Działający prywatny instalator offline, integralność manifestu i decyzja licencyjna/SmartScreen przed publicznym wydaniem | Instalator SHA, wersje Windows, bezsieciowe logi, osobna decyzja prawna; PKG-01/02 nie przechodzi po syntetycznym Inno CI |
| VN-07-02/03/05 | Work może sprawdzić **dostępne** ekrany izolowanej bety i UI stagingu; fizyczny tester Windows sprawdza klawiaturę, Chrome/Edge/Firefox oraz NVDA; zespół Wiedora wykonuje oddzielną pełną regresję hosta na autoryzowanym środowisku | Dostępny fokus/etykiety, zgodność importu/eksportu, prywatność; inne moduły Wiedory bez regresji | Zanonimizowany test WCAG/NVDA, host build SHA, przebieg regresji i potwierdzenie osoby odbierającej; bez ingerencji w `Constant_app` z tego repo |
| VN-08-01/02 | Właściciel wybiera czytnik+poprawki (A), +mikrofon (B) albo +lokalne ASR (C), wersje systemów i limity; uprawniony tester Android/iOS sprawdza lokalny import-edycję-eksport | Roundtrip JSON/UTF-8/Unicode/SHA i konflikty na prawdziwych urządzeniach; brak chmury i automatycznej zmiany surowego ASR | Prywatne wyniki urządzeń, wersja OS, obsługa błędów/odmowy dostępu, formalne zatwierdzenie zakresu; MOB-01 pozostaje NOT_RUN bez wyboru MVP |

## Kolejne uruchomienie zwykłego ChatGPT

1. Pobierz aktualny SHA `develop`, zadania, PR-y, Actions oraz [rejestr](VN_MICROTASKS.json); sprawdź cudzą równoległą pracę.
2. Nie wykonuj ponownie PR #194–198 ani już zaliczonych CI, jeśli nowy kod tego nie wymaga.
3. Działaj na konkretnych usterkach ujawnionych przez rzeczywiste testy/raporty lub nowo wykrytej luce kodowej; nigdy nie zamykaj zadania przez samą aktualizację dokumentacji.
4. Zadania wymagające uprawnionego człowieka, prawa/licencji, decyzji produktu, prywatnych nagrań lub fizycznego urządzenia pozostaw jako precyzyjne bramki NOT_RUN i kontynuuj inne możliwe prace.

**Rozdział obowiązków:** Work jest przydatny do zdalnego GUI/stagingu, ale bez dostępu do prawdziwego lokalnego sprzętu nie może zastąpić operatora mikrofonu, Windows, Android/iOS. Nie zastępuje również właściciela, recenzenta merytorycznego ani oceny prawnej.
