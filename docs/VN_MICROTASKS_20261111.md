# KWN / Video Notes — mikroplan pozostałych odbiorów (11.11.2026)

**Stan zastany:** `docs/VN_STATUS.json` z 09.11: 0/9 DONE, 8/9 W_TRAKCIE, 1/9 PLANOWANE. Ostatnie pakiety #103–105 obejmowały ręczną weryfikację twierdzeń; 15/15 CI finalnych dla #103–104. Nie powtarzamy już wdrożonych funkcji.

**Źródło szczegółowej kolejki:** [VN_MICROTASKS.json](VN_MICROTASKS.json): 37 nierozliczonych mikrozadań. Weryfikator: `python scripts/check_vn_microtasks.py`. Kolejka nie zastępuje statusu etapów.

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

- **VN-07-01 (P0, DEV)**: Zaprojektować i przetestować izolowany kontrakt adaptera WWW bez naruszania Wiedory. Bramka: `WEB-01`.
- **VN-07-02 (P0, HUMAN_TEST)**: Ręcznie zweryfikować file:// na fizycznym Windows Chrome, Edge i Firefox. Bramka: `WEB-01`; po VN-07-01.
- **VN-07-03 (P0, HUMAN_TEST)**: Przeprowadzić test klawiatury, czytnika ekranu, dużego JSON i prywatności sieciowej. Bramka: `WEB-02`; po VN-07-02.
- **VN-07-04 (P1, DEV)**: Zrealizować rzeczywisty adapter ASR/nagrywania WWW lub jawnie ograniczyć zakres beta. Bramka: `HOST-01`; po VN-07-01.
- **VN-07-05 (P1, PORTAL)**: Po osobnej autoryzacji dodać izolowaną betę Wiedora i wykonać regresję hosta. Bramka: `HOST-01`; po VN-07-03, VN-07-04, VN-06-04.

### VN-08 — 2 mikrozadań

- **VN-08-01 (P2, DECISION)**: Po desktopowych odbiorach ustalić, czy i jaki zakres Android/iOS wchodzi do produktu. Bramka: `MOB-01`; po VN-06-04.
- **VN-08-02 (P2, DEV)**: Po zatwierdzeniu zakresu przygotować specyfikację adaptera mobilnego i testy urządzeń. Bramka: `MOB-01`; po VN-08-01.

## Kolejność pierwszej paczki

Najpierw: kontrola spójności planu i rejestru, walidacja dowodów odbioru bez publikacji prywatnych danych, następnie VN-00-01/02, VN-01-01/02/03, VN-02-01/02 i testy fizyczne VN-04–06. Integracja VN-07 nie zostaje automatycznie odblokowana.

**Zrealizowane wcześniej:** automatyczny tor ASR i checkpointy, źródłowe notatki, lokalny szkic GGUF, okno ręcznej recenzji, OCR i time-align, nagrywanie oraz odzysk WAV, testowy prywatny instalator, adapter przeglądarkowy. Te elementy wymagają realnego odbioru, a nie ponownego kodowania od podstaw.
