# KWN — odbiór techniczny #100–101: poprawki i diagnostyka

Data: **09.11.2026**, repo `testowyemailaplikacja-spec/Video-notes`. PR-y zostały scalone wyłącznie do `develop`. Weryfikacja code build/test na końcowych commitach PR. Nie zmieniano `main`, `Constant_app`, Netlify, Supabase ani materiałów prywatnych.

## Wykonane prace

| PR | Rzeczywisty zakres | Wyniki CI |
| --- | --- | --- |
| [#100](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/100) | `.transcript-edits.lock` chroni współbieżną edycję segmentu w desktop GUI/CLI oraz `import-web-edits --apply`. Walidacja i zapis są pod wspólną blokadą. Pozostaje domyślny read-only podgląd. Dodano `edit-lock-status` i kontrolowane `edit-lock-recover --confirm` po potwierdzonym martwym procesie. Test rzeczywistego drugiego procesu Python nie może nadpisać danych. | [42601392194](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42601392194) 5/5 Python Linux/Windows + prawdziwe przeglądarki; [42601392182](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42601392182) Windows DEV EXE 1/1; [42601392249](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42601392249) prywatny syntetyczny Inno 1/1. **7/7 PASS**. |
| [#101](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/101) | `doctor`: dodatkowe lokalne FFplay, Tesseract i języki OCR, obecność llama-cli, kontrola nagłówka GGUF i SHA-256 lokalnego pliku modelu. Flagi `capability_candidates_not_acceptance` oznaczają wyłącznie wstępne warunki korzystania z narzędzi, nie działającą inferencję ani potwierdzone prawa. | [42602054884](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42602054884) 5/5 source/browser, [42602055432](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42602055432) Windows DEV EXE 1/1, [42602055238](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42602055238) prywatny syntetyczny Inno 1/1. **7/7 PASS**. |

Łącznie **14/14 finalnych prac GitHub Actions PASS** (zadania CI, nie liczba formalnie ukończonych etapów).

## Test manualny lokalny bez publikowania danych

1. Otwórz istniejący lokalny projekt KWN, wykonaj `python -m videonotes edit-lock-status KATALOG`: brak blokady to `missing`. Dwa programy próbujące pisać jednocześnie muszą dostać komunikat konfliktu. Nie usuwaj aktywnej blokady. Jeżeli proces nie działa i status jest `stale`, po świadomej weryfikacji użyj `edit-lock-recover KATALOG --confirm`. Po poprawkach źródłowe `transcript.json` nie może się zmienić.
2. Wybierz wcześniej przygotowane własne i legalne binaria. Uruchom `doctor --ffplay ... --tesseract ... --ocr-language pol+eng --llama-cli ... --gguf-model ...`. Sprawdź, czy w raporcie nie ma ścieżek prywatnych, czy pakiet `pol` jest zainstalowany oraz czy nie występuje `release_ready=true`. Wynik `header_fingerprinted` GGUF **nie potwierdza** modelu działającego z `llama-cli`.

## Formalny status

**0/9 DONE, 8/9 W_TRAKCIE, 1/9 PLANOWANE**, zgodnie z `docs/VN_STATUS.json`. Brak fizycznego Windows z 2-godzinnym mikrofonem i pętlą system audio, legalnych nagrań do WER/CER, ręcznej oceny jakości modeli GGUF, licencji i podpisanego instalatora oraz zatwierdzonej integracji z Wiedorą.

**Limity nowych rozwiązań:** blokada poprawek jest kooperacyjna i nie chroni pliku przed zewnętrznym edytorem, który ignoruje blokadę. Diagnostyka FFplay, Tesseract i GGUF nie testuje jakości wideo/audio, merytoryki OCR, działania całej aplikacji w trybie offline po odłączeniu sieci ani praw do redystrybucji.

Powiązane materiały: [KWN_EDIT_LOCK.md](KWN_EDIT_LOCK.md), [VN_OFFLINE_DIAGNOSTICS.md](VN_OFFLINE_DIAGNOSTICS.md), [VN_HARDWARE_ACCEPTANCE_20261107.md](VN_HARDWARE_ACCEPTANCE_20261107.md), [issue #95](https://github.com/testowyemailaplikacja-spec/Video-notes/issues/95).
