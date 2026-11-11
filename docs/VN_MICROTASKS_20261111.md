# KWN / Video Notes — mikroplan pozostałych odbiorów (11.11.2026)

> **Aktualizacja 11.11.2026:** 2/37 mikrozadań DONE (VN-07-01, VN-07-04: izolowany kontrakt i jawna granica beta); VN-07-05 IN_PROGRESS po scaleniu PR [Constant_app #189](https://github.com/testowyemailaplikacja-spec/Constant_app/pull/189) do develop i Netlify. Pozostałe 34 TODO; **0/9 pełnych etapów DONE**. Odbiory fizyczne/human/legal wciąż niezaliczone. Szczegóły [VN07_WIEDORA_BRIDGE_20261111.md](VN07_WIEDORA_BRIDGE_20261111.md).

**Stan zastany (historyczny punkt odniesienia):** `docs/VN_STATUS.json` z 09.11: 0/9 DONE, 8/9 W_TRAKCIE, 1/9 PLANOWANE. Ostatnie pakiety #103–105 obejmowały ręczną weryfikację twierdzeń; 15/15 CI finalnych dla #103–104. Nie powtarzamy już wdrożonych funkcji.

**Źródło szczegółowej kolejki:** [VN_MICROTASKS.json](VN_MICROTASKS.json): 37 mikrozadań (11.11: 2 DONE, 1 IN_PROGRESS, 34 TODO). Weryfikator: `python scripts/check_vn_microtasks.py`. Kolejka nie zastępuje statusu etapów.

## Zasady

1. P0 przed P1/P2; zależności `depends_on` determinują kolejność.
2. Zadania `DEV` realizować na odrębnych gałęziach Video-notes → PR → CI → `develop`. Nie modyfikować `main`, Wiedora, Supabase ani Netlify.
3. `HUMAN_TEST`, `REVIEW` i `LEGAL` wymagają dowodu spoza syntetycznego CI. Bez sprzętu/modelu/licencji `NOT_RUN`, nie `PASS`.
4. Nagrania, transkrypcje, dane osoby i lokalne modele zostają poza publicznym GitHub. Metryki i anonimowe hashe można przekazać bez treści źródłowej.
5. Stosować istniejącą [macierz HW/ASR/NOTE/MIC/MIX/WEB/PKG/HOST](VN_HARDWARE_ACCEPTANCE_20261107.md) i [issue #95](https://github.com/testowyemailaplikacja-spec/Video-notes/issues/95). `acceptance_id` wskazuje kryterium wymagające odbioru, nie deklaruje jego zaliczenia.
6. Wynik mikroplanu nie może automatycznie zmienić statusu 9 etapów. Akceptacja i decyzje wydawnicze wymagają weryfikowalnych dowodów.

## Kolejka według etapów

### VN-00 — 4 mikrozadań

- **VN-00-01 (P0, HUMAN_TEST)**: Przygotować legalne próbki naturalnej mowy PL/EN i ręczne transkrypcje referencyjne. Bramka: `ASR-01`.
- **VN-00-02 (P0, HUMAN_TEST)**: Uruchomić benchmark whisper.cpp vs faster-whisper na identycznym PCM; zebrać WER/CER, CPU, czas, peak RAM. Bramka: `ASR-04`; po VN-00-01.
- **VN-00-03 (P0, LEGAL)**: Zweryfikować pochodzenie/licencje modeli i binariów; podjąć udokumentowaną decyzję technologiczną. Bramka: `PKG-02`; po VN-00-02.
- **VN-00-04 (P0, HUMAN_TEST)**: Sprawdzić start offline na fizycznym Windows ze zweryfikowanym zestawem. Bramka: `HW-01`; po VN-00-03.

### VN-01 — 5 mikrozadań

- **VN-01-01 (P0, HUMAN_TEST)**: Wykonać pełną transkrypcję rzeczywistego OBS MP4 PL i eksport TXT/SRT. Bramka: `ASR-01`; po VN-00-01.
- **VN-01-02 (P0, HUMAN_TEST)**: Sprawdzić OBS MKV z dwiema prawdziwymi ścieżkami audio oraz jawny wybór ścieżki. Bramka: `ASR-02`; po VN-00-01.
- **VN-01-03 (P0, HUMAN_TEST)**: Sprawdzić anglojęzyczny tutorial na prawdziwym lokalnym modelu i zbadać duplikaty. Bramka: `ASR-03`; po VN-00-01.
- **VN-01-04 (P0, HUMAN_TEST)**: Uruchomić 2h+ ASR na docelowym CPU, przerwać, wznowić, porównać checkpointy, RAM i dysk. Bramka: `ASR-05`; po VN-00-04.
- **VN-01-05 (P1, HUMAN_TEST)**: Przetestować uszkodzone nagranie, brak audio, brak modelu, brak miejsca i ochronę istniejącego projektu. Bramka: `ASR-06`; po VN-00-04.

### VN-02 — 4 mikrozadań

- **VN-02-01 (P0, DEV)**: Uruchomić istniejące semantic-draft + review na prawdziwym, lokalnym zgodnym GGUF; zebrać bezpieczne wskaźniki. Bramka: `NOTE-01`; po VN-01-01.
- **VN-02-02 (P0, REVIEW)**: Porównać każde twierdzenie AI i cytat z oryginalnym nagraniem; zatwierdzić/odrzucić z uzasadnieniem. Bramka: `NOTE-01`; po VN-02-01.
- **VN-02-03 (P1, HUMAN_TEST)**: Odebrać regenerację notatek, korekty, undo, backup/restore i odporność na przerwanie. Bramka: `NOTE-03`; po VN-01-01.
- **VN-02-04 (P1, HUMAN_TEST)**: Otworzyć i ręcznie ocenić DOCX/PDF na rzeczywistym Windows Word lub LibreOffice. Bramka: `NOTE-02`; po VN-02-02.

### VN-03 — 4 mikrozadań

- **VN-03-01 (P0, HUMAN_TEST)**: Sprawdzić OCR slajdów rzeczywistego kursu CCNA, jakość PL/EN i indeksowanie obrazów. Bramka: `NOTE-02`; po VN-01-02.
- **VN-03-02 (P0, REVIEW)**: Ręcznie sprawdzić powiązanie slajd–wypowiedź, prawidłowość liczb, nazw i faktów. Bramka: `NOTE-01`; po VN-03-01.
- **VN-03-03 (P1, REVIEW)**: Odebrać szablony lecture/tutorial/meeting/study na realnym materiale i kontrolę powtórzeń. Bramka: `NOTE-01`; po VN-02-02.
- **VN-03-04 (P1, HUMAN_TEST)**: Sprawdzić konspekt, Word i PDF oraz klikalne źródła dla rzeczywistego wykładu. Bramka: `NOTE-02`; po VN-03-03.

### VN-04 — 4 mikrozadań

- **VN-04-01 (P0, HUMAN_TEST)**: Zbadać fizyczne urządzenie USB DirectShow, wybór, zgody, start i stop. Bramka: `MIC-01`; po VN-00-04.
- **VN-04-02 (P0, HUMAN_TEST)**: Zarejestrować 2h+ i sprawdzić pause/resume, odłączenie, uśpienie, pełen dysk i crash WAV. Bramka: `MIC-02`; po VN-04-01.
- **VN-04-03 (P0, HUMAN_TEST)**: Sprawdzić salvage/recovery niepełnego WAV bez nadpisania oryginałów. Bramka: `MIC-02`; po VN-04-02.
- **VN-04-04 (P1, HUMAN_TEST)**: Wykonać record-to-ASR w GUI na realnym nagraniu oraz ocenić diagnostykę poziomu sygnału. Bramka: `MIC-01`; po VN-04-01.

### VN-05 — 4 mikrozadań

- **VN-05-01 (P0, HUMAN_TEST)**: Przetestować fizyczny mikrofon+system audio z dwiema jawnymi zgodami. Bramka: `MIX-01`; po VN-04-01.
- **VN-05-02 (P0, HUMAN_TEST)**: Zmierzyć synchronizację i jakość miksu w długim nagraniu. Bramka: `MIX-01`; po VN-05-01.
- **VN-05-03 (P1, HUMAN_TEST)**: Przetestować brak Stereo Mix, odmowę uprawnienia i bezpieczny fallback do mikrofonu. Bramka: `MIX-02`; po VN-05-01.
- **VN-05-04 (P1, DECISION)**: Zdecydować o alternatywnym backendzie na komputerach bez loopback, z zakresem i testami. Bramka: `MIX-02`; po VN-05-03.

### VN-06 — 5 mikrozadań

- **VN-06-01 (P0, LEGAL)**: Wykonać legal review zależności, FFmpeg build, Whisper, GGUF i SPDX SBOM. Bramka: `PKG-02`; po VN-00-03.
- **VN-06-02 (P0, HUMAN_TEST)**: Przetestować prywatny Inno setup z rzeczywistymi licencjonowanymi modelami przy wyłączonej sieci. Bramka: `PKG-01`; po VN-06-01.
- **VN-06-03 (P0, HUMAN_TEST)**: Sprawdzić instalację, aktualizację, odinstalowanie i ślad na czystym Windows. Bramka: `PKG-02`; po VN-06-02.
- **VN-06-04 (P0, LEGAL)**: Udokumentować decyzję podpis/AV/SmartScreen i prawa do dystrybucji przed wydaniem 1.0. Bramka: `PKG-02`; po VN-06-03.
- **VN-06-05 (P1, HUMAN_TEST)**: Sprawdzić odzyskiwanie po awarii i długie sesje na docelowym komputerze. Bramka: `PKG-01`; po VN-01-04, VN-04-03.

### VN-07 — 5 mikrozadań

- **VN-07-01 (P0, DEV, DONE 11.11)**: Zaprojektować i przetestować izolowany kontrakt adaptera WWW bez naruszania Wiedory. Bramka: `WEB-01`.
- **VN-07-02 (P0, HUMAN_TEST)**: Ręcznie zweryfikować file:// na fizycznym Windows Chrome, Edge i Firefox. Bramka: `WEB-01`; po VN-07-01.
- **VN-07-03 (P0, HUMAN_TEST)**: Przeprowadzić test klawiatury, czytnika ekranu, dużego JSON i prywatności sieciowej. Bramka: `WEB-02`; po VN-07-02.
- **VN-07-04 (P1, DEV, DONE 11.11)**: Zrealizować rzeczywisty adapter ASR/nagrywania WWW lub jawnie ograniczyć zakres beta. Bramka: `HOST-01`; po VN-07-01.
- **VN-07-05 (P1, PORTAL, IN_PROGRESS, formal gate blocked)**: Po osobnej autoryzacji dodać izolowaną betę Wiedora i wykonać regresję hosta. Bramka: `HOST-01`; po VN-07-03, VN-07-04, VN-06-04.

### VN-08 — 2 mikrozadań

- **VN-08-01 (P2, DECISION)**: Po desktopowych odbiorach ustalić, czy i jaki zakres Android/iOS wchodzi do produktu. Bramka: `MOB-01`; po VN-06-04.
- **VN-08-02 (P2, DEV)**: Po zatwierdzeniu zakresu przygotować specyfikację adaptera mobilnego i testy urządzeń. Bramka: `MOB-01`; po VN-08-01.

## Kolejność pierwszej paczki

Najpierw: kontrola spójności planu i rejestru, walidacja dowodów odbioru bez publikacji prywatnych danych, następnie VN-00-01/02, VN-01-01/02/03, VN-02-01/02 i testy fizyczne VN-04–06. Integracja VN-07 nie zostaje automatycznie odblokowana.

**Zrealizowane wcześniej:** automatyczny tor ASR i checkpointy, źródłowe notatki, lokalny szkic GGUF, okno ręcznej recenzji, OCR i time-align, nagrywanie oraz odzysk WAV, testowy prywatny instalator, adapter przeglądarkowy. Te elementy wymagają realnego odbioru, a nie ponownego kodowania od podstaw.

## Regresja techniczna po wdrożeniu PR #109–110 (11.11.2026)

KWN/Video-notes PR [#109](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/109) i [#110](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/110) są scalone na develop. Wprowadzono limity plików, bezpieczne dowody i rzeczywisty test zapisanych pięciu plików. Przeglądarki Chromium Linux, Firefox Linux, Chrome i Edge Windows oraz testy kontraktów Windows PASS. **Praca Python + FFmpeg na Ubuntu FAIL na etapie instalacji FFmpeg**, zanim uruchomiła testy: runner nie rozwiązywał DNS `azure.archive.ubuntu.com`, próba `apt` zakończyła się timeoutem 124. Dowody: [Actions #43054655548](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43054655548) i [#43055496463](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43055496463). To **blokada infrastrukturalna**, nie wynik FAIL testów merytorycznych, ale pełnej regresji nadal nie wolno nazywać PASS. W nowym workflow dodano samodzielne źródłowe testy Linux bez FFmpeg oraz krótszą, jawnie oznaczoną bramkę FFmpeg; wynik nowego workflow trzeba zweryfikować osobno. Pozostałe mikrozadania i 9 etapów nie zmieniają statusów z tego powodu.

## Techniczne zamknięcia poprawek bez fałszywego odbioru (11.11.2026)

Po PR #109–114: limity eksportu tekstu (64 MiB) i poprawek desktop (20 MiB), rygorystyczny lokalny re-import poprawionej transkrypcji, 100-krokowe cofanie i ponawianie, opcjonalny odsłuch wybranego nagrania z ręcznym skokiem do czasu segmentu. #113 i #114 przeszły po **6/6 hosted CI PASS** łącznie z realnymi przeglądarkami i osobnym Linux FFmpeg. Ich kod trafił przez [host PR #197](https://github.com/testowyemailaplikacja-spec/Constant_app/pull/197) do Wiedora `develop` `796d9d4a6ec27d72f0075cae325c7e1baa050f52`, Netlify `6af4e6e672a8c6c58132e24d` READY. Źródło i pełny opis bramek: [VN07_WIEDORA_BRIDGE_20261111.md](VN07_WIEDORA_BRIDGE_20261111.md).

**Pozostałe zadania nie są sztucznie zamykane:** 2/37 DONE, 1/37 IN_PROGRESS, 34/37 TODO i 0/9 pełnych etapów DONE. `VN-07-05` potrzebuje host `verify:full`, rzeczywistych urządzeń/QA i bramek legal; `WEB-01/02` i `HOST-01` nie przeszły fizycznej akceptacji. `VN_STATUS.json` oraz rejestr mikrozadań pozostają źródłem prawdy. Automatyczne testy z poprzedniego PR nie mogą oznaczyć sprawdzenia nagrania naturalnego, WER/CER lub NVDA.
