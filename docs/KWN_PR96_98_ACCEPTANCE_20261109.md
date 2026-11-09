# KWN — odbiór techniczny PR #96–98

Data: **09.11.2026** (Europa/Warszawa). Repo robocze: `testowyemailaplikacja-spec/Video-notes`, gałąź `develop`. Weryfikacja ostatniego poprawnego kodu: po scaleniu PR #98, commit `860e3210d9bf22c08a65a116eae8484759a9384b`. `main` nadal `4da53b3bff580e07a16218e5f7017cecf8ff7aed`. Nie zmieniano `Constant_app`, Netlify ani Supabase.

## Wykonanie

| Zmiana | PR i wynik | Automatyczne kontrole | Ograniczenia |
| --- | --- | --- | --- |
| Odsłuch źródłowy dla segmentu KWN | [#96](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/96) — merged | [42595929720](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42595929720) 5/5 (Python+przeglądarki), [42595929705](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42595929705) 2/2 (genuine Tk Win/Linux), [42595929769](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42595929769) 1/1 (Inno synthetic), [42595929879](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42595929879) 1/1 (Win DEV) | Sprawdzony rzeczywisty FFmpeg dla sztucznego lokalnego WAV; odtwarzacz FFplay podstawiony w testach. Fizyczny Windows/audio i użytkownik NOT_RUN; FFplay nie jest składnikiem prywatnego bundle |
| Powiązanie slajdów i wypowiedzi w czasie | [#97](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/97) — merged | [42596514806](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42596514806) 5/5, [42596515028](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42596515028) 2/2 Tk, [42596514808](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42596514808) 1/1 Inno, [42596514770](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42596514770) 1/1 Win DEV | Tylko najbliższa **czasowo** wypowiedź. OCR uruchamiany osobno; rzeczywisty PTS obrazu, merytoryczny związek slajdu i tekstu, prywatne nagrania CCNA i test użytkownika NOT_RUN |
| Strażnik liczb i identyfikatorów w szkicu AI | [#98](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/98) — merged | [42597232583](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42597232583) 5/5 source/browser, [42597232588](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42597232588) 1/1 Win DEV | Wykrywa niepoparte dosłowne liczby, adresy IP i akronimy. **Nie** sprawdza semantycznej prawdziwości tez; model GGUF zastępowano atrapą w testach |

**24/24 zarejestrowanych zadań CI PASS** dla *końcowych commitów* PR #96–98. Są to prace CI, nie 24 odrębne funkcje ani 24 zamknięte kryteria odbiorowe.

## Co nowego jest użyteczne

W GUI kliknięcie źródła z notatki prowadzi do segmentu, który można teraz świadomie odsłuchać z oryginalnej ścieżki audio OBS. Program wybiera zapisany strumień, weryfikuje rozmiar i SHA-256, wycina krótki WAV i usuwa go po odsłuchu. Działa w wątku bez blokowania edytora i bez nadpisania poprawek.

Indeks slajdów wykorzystuje tylko istniejący raport `slide-ocr` i poprawioną transkrypcję. Nie zgaduje, co mówił prowadzący: gdy brak pobliskiej wypowiedzi, zapisuje `null`. Zmiana OCR, edycji lub oryginalnego źródła unieważnia weryfikację indeksu; eksport Markdown traktuje nieufne teksty jako cytaty.

Generator lokalnych szkiców AI odrzuca nowe dosłowne liczby, adresy IP i wielkoliterowe skróty, których nie ma w przypisanych fragmentach. Obejmuje tworzenie i weryfikację po edycji. Nie zmienia to niezweryfikowanego statusu generowanych twierdzeń i może odrzucić poprawne, ale niepoparte wprost przekształcenia.

## Status etapów

**0/9 DONE, 8/9 W TRAKCIE, 1/9 PLANOWANE.** Brak prawdziwego, urządzeniowego odbioru Windows, naturalnych wykładów PL/EN z WER/CER, rzeczywistego modelu GGUF i ręcznej oceny merytorycznej, długiego mikrofonu, synchronizacji loopback, legalnie rozdystrybuowanego i podpisanego instalatora, przeglądarek z czytnikiem ekranu oraz końcowej integracji z Wiedorą.

Cała macierz sprzętowych i ludzkich bramek: [VN_HARDWARE_ACCEPTANCE_20261107.md](VN_HARDWARE_ACCEPTANCE_20261107.md), issue [#95](https://github.com/testowyemailaplikacja-spec/Video-notes/issues/95). Dalsze możliwe prace kodowe nie zastępują tych dowodów.

`develop` jest robocze; nie publikować jako wydania 1.0, nie oznaczać żadnego etapu DONE bez pełnej akceptacji i nie włączać do stabilnej Wiedory bez oddzielnej zgody i regresji hosta.
