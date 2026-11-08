# VIDEO NOTES — PLAN ROZWOJU SAMODZIELNEGO PROGRAMU

**Wersja planu:** 1.3 · **Data:** 2026-11-06 · **Repo:** `testowyemailaplikacja-spec/Video-notes`  
**Status ogólny:** W TRAKCIE (VN-00–VN-07; VN-08 opcjonalny PLANOWANE), formalnie 0/9 etapów DONE na 08.11.2026. Prawdziwy whisper.cpp i faster-whisper na syntetycznym TTS oraz prywatny instalator Inno Setup mają potwierdzone testy CI, lecz naturalna mowa, odbiór fizycznego Windows i publiczna dystrybucja są otwarte. Dowody i aktualny stan: \`docs/VN_STATUS.json\`.  
**Zakres bieżący:** osobny program Windows. Najpierw OBS → transkrypcja → notatki podstawowe → zaawansowane → mikrofon na żywo → dalsze źródła.  
**Poza bieżącą implementacją:** przebudowa Wiedora / Constant_app, płatne API, usługi w chmurze, aplikacja mobilna.

## Granica projektu: Notatki a Konwerter

Video Notes rozwija funkcjonalność istniejącej aplikacji **`apps/notatki/`** z portalu Wiedora. **Nie jest konwerterem plików.** Aplikacja **`apps/konwerter/`** pozostaje oddzielnym produktem, którego funkcji (PDF/DOC/DOCX, łączenie PDF, przekształcanie obrazów i ogólne konwersje multimediów) nie przenosimy do Video Notes. Dopuszczalne jest tylko techniczne dekodowanie/wyodrębnianie dźwięku z nagrania OBS potrzebne do transkrypcji. Migawka kodu obecnych Notatek służy jako wzór, nie gotowa implementacja aplikacji Windows.

## A. Cel produktu i podstawowe zasady

Video Notes to **samodzielna aplikacja oparta funkcjonalnie na module Notatki Wiedora** zamieniająca nagrania lub dźwięk na edytowalną wiedzę. W wersji startowej użytkownik dodaje plik z OBS Studio, dostaje wierną transkrypcję z oznaczeniami czasu i może ją poprawić. W kolejnych wersjach program przekształca transkrypcję w proste, a następnie zaawansowane notatki. Dopiero później dojdą źródła dźwięku na żywo.

**Nadrzędne wymagania:**

1. Lokalna praca na Windows (priorytet Windows 10/11 64-bit, ostateczna macierz po testach), z możliwością **instalacji i używania bez internetu** przy pełnym pakiecie modeli i środowiska uruchomieniowego.
2. Bez obowiązkowego konta, subskrypcji i połączeń z zewnętrznym API; brak automatycznego wysyłania plików, transkrypcji i metryk.
3. Wersja CPU musi mieć drogę działania; GPU jest opcjonalnym przyspieszeniem. Program powinien komunikować ograniczenia słabszego sprzętu zamiast zawieszać się bez wyjaśnienia.
4. Jedna lokalna baza projektu i otwarty, wersjonowany format wymiany danych. Rozróżniamy surową transkrypcję, poprawioną transkrypcję i opracowaną notatkę; nie nadpisujemy oryginału.
5. Rozdzielenie **silnika**, **interfejsu Windows** oraz **adapterów źródeł i eksportu**, aby możliwa była późniejsza wersja WWW i mobilna bez przepisywania logiki biznesowej.
6. Prywatność i licencje: przed dystrybucją sprawdzamy licencję każdego silnika, modelu, pakietu i sposobu ich redystrybucji; decyzje dokumentujemy.
7. Każdy etap kończy się testami na rzeczywistych nagraniach i dowodami, a nie samym zapisem plików w repozytorium.


### Architektura produktu: samodzielny program i osobny moduł portalu Wiedora

**Zatwierdzone założenie projektowe:** Video Notes rozwijamy w tym repozytorium jako **niezależną, w pełni użytkową aplikację**, a nie jako funkcję budowaną bezpośrednio w kodzie strony Wiedora. **Docelowo gotowy produkt zostanie udostępniony także wewnątrz Wiedora jako odrębny moduł aplikacyjny**, bez utraty samodzielności.

- **Samodzielność:** program Windows ma uruchamiać się, przetwarzać nagrania OBS, zapisywać projekty i eksportować notatki bez strony, konta Wiedora, Supabase, Netlify i połączenia z siecią.
- **Oddzielny rozwój:** Video Notes ma własne repozytorium, wersje, testy, instalator i dokumentację. Zmiany w programie nie mogą automatycznie zmieniać pozostałych aplikacji Wiedora.
- **Integracja WWW:** portal Wiedora ma docelowo udostępniać osobną pozycję „Video Notes” w katalogu aplikacji, punkt wejścia do wersji przeglądarkowej oraz możliwość pobrania programu Windows. Funkcja działająca w przeglądarce ma być rzeczywista, a nie atrapą.
- **Granica techniczna:** pliku `.exe` nie da się uruchomić jako kodu strony WWW. Wersja przeglądarkowa wymaga osobnego adaptera wykonawczego (np. WebAssembly/Web APIs lub opcjonalnego backendu) przy wspólnym **kontrakcie danych i logice możliwej do ponownego wykorzystania**. Nie zakładamy, że identyczne silniki AI i wymagania sprzętowe będą dostępne na Windows i w przeglądarce.
- **Interoperacyjność:** od VN-00 dokumentujemy stabilne, wersjonowane formaty transkrypcji, segmentów, notatek i projektów; adapter Wiedora ma je wykorzystywać, zamiast tworzyć drugi niespójny model danych.
- **Prywatność:** integracja z kontem Wiedora, przesyłanie plików i synchronizacja pozostają opcjonalne i wymagają wyraźnego działania użytkownika. Podstawowe przetwarzanie desktopowe pozostaje lokalne.
- **Warunek wdrożenia:** VN-07 obejmuje oddzielną integrację i testy regresji istniejącej strony. **Nie zmieniać repozytorium `Constant_app` ani jego backendu w fazach VN-00–VN-06.**

**Docelowy układ:** `Video Notes (silnik + samodzielny program Windows)` → `wersjonowany kontrakt i adapter WWW` → `Video Notes jako niezależna aplikacja w katalogu Wiedora`. Obie wersje muszą mieć własne testy i proces wydawania.

### Użytkownik i główny scenariusz

Użytkownik nagrał wykład lub tutorial w OBS, np. do MP4 albo MKV. Wybiera plik, wskazuje język i właściwą ścieżkę audio, uruchamia transkrypcję, kontroluje postęp, poprawia rozpoznane słowa i zapisuje tekst. W kolejnych etapach wybiera „Notatka podstawowa” lub „Notatka zaawansowana”. W przyszłości może rozpocząć sesję mikrofonową bez wcześniejszego nagrywania w OBS.

### Co oznaczają poziomy rezultatu

- **Transkrypcja 1:1:** maksymalnie wierny zapis słów, bez celowego skracania; możliwe pomyłki ASR. Znaczniki czasu prowadzą do nagrania.
- **Notatka podstawowa:** tytuły, główne tematy, akapity/punkty i krótkie streszczenie **wyłącznie na podstawie transkrypcji**; bez dopisywania wiedzy spoza źródła.
- **Notatka zaawansowana:** hierarchia rozdziałów, definicje, przykłady, kluczowe wnioski, odnośniki do fragmentów, wykrywanie niepewnych fragmentów i — po osobnej weryfikacji — odczytywanie slajdów/obrazu.

## B. Fazy i bramki odbioru

### VN-00 — Fundamenty i wybór technologii

**Cel:** udowodnić na prawdziwym pliku OBS, że lokalny proces działa w akceptowalnej jakości, oraz ustalić stabilne granice modułów. **Status: W TRAKCIE, BEZ ODBIORU — 06.11.2026.**

**Zadania:**
- [ ] Zainicjalizować projekt, zasadę pracy na gałęziach, `.gitignore`, wersjonowanie, licencję projektu (decyzja właściciela), standard pull requestów i raportów.
- [ ] Przygotować 3–5 dozwolonych próbek testowych: polska mowa 5–10 min, angielska mowa, OBS MP4, OBS MKV z wieloma ścieżkami, próbka trudna/zaszumiona. Bez commitowania prywatnych wykładów.
- [ ] Porównać co najmniej dwa warianty lokalnego ASR (np. `whisper.cpp` i `faster-whisper`), mierząc jakość, pamięć, prędkość CPU, możliwość pakowania i licencje.
- [ ] Potwierdzić lokalny demux audio przez FFmpeg i obsługę typowych formatów OBS, zwłaszcza wielościeżkowych MKV/MP4.
- [ ] Wybrać docelowy interfejs/packaging (kandydat: Tauri + samodzielny silnik CLI/sidecar); przetestować pakiet bez obowiązkowego Pythona instalowanego przez użytkownika.
- [ ] Ustalić wersjonowany schemat `project.json`, `transcript.json`, `notes.md`, zasady ścieżek, automatycznego zapisu, błędów i wznawiania.
- [ ] Zaplanować budowanie bez zależności sieciowej w czasie uruchamiania oraz rozdzielić „pełny instalator offline” i ewentualny „mały instalator z pobraniem modeli”.
- [ ] Założyć tests/fixtures, automatyczne testy kontraktu, walidację licencji i regułę bezpiecznego logowania (bez treści nagrań).

**Bramka akceptacji:** powtarzalny eksperyment OBS → lokalne audio → transkrypcja na Windows, udokumentowany benchmark i decyzja technologiczna; przechodzi instalacja próbnego środowiska bez sieci na przygotowanym komputerze albo podano konkretną blokadę. Nie jest to jeszcze wydanie użytkowe.

### VN-01 — OBS → podstawowa transkrypcja (MVP, v0.1)

**Cel:** działający program do konwersji nagrań z OBS w transkrypcję, bez mechanizmu generowania notatek. **Status: W TRAKCIE, BEZ ODBIORU — 06.11.2026.**

**Funkcje:**
- [ ] Import przez wybór i przeciągnięcie pliku: MP4, MKV, WebM; później MOV i pozostałe kodeki po badaniu zgodności. Czytelne informacje, gdy kodek jest nieobsługiwany.
- [ ] Wykrycie ścieżek audio i wybór właściwej, również gdy OBS zapisuje mikrofon i komputer osobno; opcjonalne mieszanie po świadomym wyborze użytkownika.
- [ ] Przygotowanie audio strumieniowo/fragmentami; bez wczytywania wielogigabajtowego filmu do RAM.
- [ ] Polski i angielski: automatyczne rozpoznanie języka z możliwością ręcznego wyboru.
- [ ] Transkrypcja 1:1 z czasem segmentów, informacją o modelu i błędach; widoczny postęp, zatrzymanie/anulowanie i bezpieczna obsługa przerwania.
- [ ] Zapis projektu lokalnego i odtwarzanie ostatniego poprawnego punktu (bez powielania tekstu); poprawianie transkrypcji przez użytkownika.
- [ ] Eksport TXT, SRT, VTT, JSON transkrypcji; kopia oryginalnych wyników ASR zachowana po edycji.
- [ ] Minimalny użyteczny interfejs Windows: plik, ścieżka audio, język, model, rozpocznij, postęp, tekst, zapisz, eksport.
- [ ] Obsługa odmowy dostępu, pełnego dysku, uszkodzonego pliku, braku audio, braku modelu i ponownej próby.

**Bramka akceptacji:** użytkownik na Windows, bez sieci, może dodać MP4 i MKV z OBS, wybrać ścieżkę, uzyskać polski tekst, poprawić go i pobrać TXT/SRT. Test wielogodzinnego filmu nie powoduje wczytania całego pliku do RAM; przerwanie i ponowienie nie dubluje segmentów. Jest działający instalator testowy lub jasno wskazana zależność z VN-00.

**Pierwsze publiczne wydanie testowe:** v0.1 (tylko jeśli bramka przejdzie). Nazwa „transkrypcja”, nie „inteligentne notatki”.

### VN-02 — Podstawowe notatki z transkrypcji (v0.2)

**Cel:** zmiana tekstu na krótką, czytelną notatkę bez konieczności ręcznego porządkowania całości. **Status: W TRAKCIE (prototyp ekstrakcyjny; nie jest to pełne semantyczne opracowanie ani odbiór VN-02).**

- [x] Dodać odrębne polecenie „Utwórz notatkę podstawową” po zakończeniu transkrypcji (CLI i GUI; wymaga pełnych checkpointów).
- [x] Lokalny mechanizm ekstrakcyjny jako alternatywa regułowa bez płatnego API; semantyczne streszczenie/model nadal poza obecnym zakresem i nie jest zaliczone.
- [ ] Wygenerować tytuł, nagłówki tematyczne, najważniejsze punkty i krótkie podsumowanie. Nie tworzyć fikcyjnych faktów, nazwisk, cytatów ani źródeł.
- [ ] Zachować odnośniki do fragmentów transkrypcji; umożliwić kliknięcie i korektę przez użytkownika.
- [ ] Osobne widoki „Transkrypcja” i „Notatka”, wycofanie/ponowne wygenerowanie, ręczna edycja.
- [ ] Eksport Markdown i TXT; DOCX/PDF można dodać po ustabilizowaniu reprezentacji.
- [ ] Testy braku treści, błędów w transkrypcji, nazw własnych i liczb; nie ukrywać niskiej pewności.

**Bramka akceptacji:** na rzeczywistych próbkach notatka obejmuje ustalone główne zagadnienia, każdą konkretną informację da się odszukać w transkrypcji, a użytkownik może zmienić tekst i zapisać wynik lokalnie. Ocena jakości przez człowieka wg matrycy testów.

### VN-03 — Zaawansowane notatki i materiały naukowe (v0.3)

**Cel:** wielopoziomowe opracowanie materiałów edukacyjnych z zachowaniem powiązań do źródła. **Status: W TRAKCIE — istnieją konspekt ekstrakcyjny i źródłowy przewodnik do nauki, ale nie pełna synteza semantyczna ani odbiór.**

- [ ] Szablony: wykład akademicki, tutorial techniczny, spotkanie, materiał do nauki; ustawienia długości i szczegółowości.
- [ ] Spis treści, podrozdziały, definicje, przykłady, kroki procedur, pojęcia do sprawdzenia, lista niejasności i cytowane fragmenty z czasem źródła.
- [ ] Długie nagrania: dzielenie na logiczne części, wieloetapowe opracowanie, kontrola duplikatów i utrzymanie kontekstu.
- [ ] Weryfikacja faktów **wobec transkrypcji**, oznaczanie wątpliwości zamiast wymyślania; bez udawania dostępu do zewnętrznych źródeł offline.
- [ ] Dopiero jako osobny podetap **VN-03B**: wybrane klatki/slajdy, OCR lokalny, synchronizacja z wypowiedzią, weryfikacja komend/kodu i ilustracji. Nie obiecywać pełnego rozumienia każdego schematu.
- [ ] Eksport do DOCX i PDF po sprawdzeniu polskich znaków, tabel i dużych dokumentów; równolegle Markdown.
- [ ] Parametry jakości „szybko / dokładnie” według wykrytej pamięci i sprzętu, bez niejawnego obciążenia płatnych usług.

**Bramka akceptacji:** trzy zestawy testowe (wykład, slajdy, tutorial CCNA) mają sprawdzone odwzorowanie tematów, powiązania czasowe i jawne oznaczenia informacji niepewnych; eksport nie gubi treści. Materiały wizualne przechodzą osobną bramkę, nie blokując wersji tekstowej.

### VN-04 — Mikrofon na żywo podczas wykładu (v0.4)

**Cel:** możliwość rejestrowania i rozpoznawania wypowiedzi bez przygotowanego pliku OBS. **Status: W TRAKCIE — Windows DirectShow, GUI Start/Pauza/Wznów/Stop, zamykanie WAV, izolacja nowych ujęć, SHA-256, łączenie i lokalna kontrola RMS/ciszy/clippingu; realny FFmpeg na syntetycznej fali i Tk Windows/Linux CI PASS, fizyczny mikrofon i 2h wciąż nieodebrane.**

- [ ] Wybór mikrofonu, wskaźnik poziomu, zgoda użytkownika, start/pauza/wznów/stop oraz czytelny status nagrywania.
- [x] Zapisywanie nagrania w częściach WAV co 2h i odrębnych katalogach ujęć po pauzie, z SHA-256; testy real FFmpeg i Windows/Linux PASS, fizyczna awaria nadal do odbioru.
- [ ] Transkrypcja na żywo, jeśli sprzęt daje radę; w przeciwnym razie transkrypcja z kolejki po nagraniu. Komunikat o opóźnieniu.
- [x] Oddzielenie tymczasowych `.vn-take-*` od zweryfikowanych WAV przez atomowe dowiązania bez nadpisania; po awarii pozostają czytelne części i katalogi do ręcznej kontroli. Automatyczne odtworzenie z uszkodzonego WAV nadal niezaimplementowane.
- [ ] Wybór jakości źródła, kontrola ciszy, testy odłączenia mikrofonu, zmiany urządzenia, uśpienia i odmowy dostępu.
- [ ] Po stopie nagranie trafia do **tego samego** procesu transkrypcji i notatek co plik OBS.

**Bramka akceptacji:** rzeczywista sesja wykładowa w Windows jest zapisana i odtwarzalna, tekst powstaje bez duplikatów, a po awarii można odzyskać zakończone segmenty. Wykonano test urządzeń fizycznych.

### VN-05 — Inne źródła dźwięku (v0.5)

**Cel:** rozszerzać wejścia bez kopiowania osobnego silnika transkrypcji. **Status: W TRAKCIE (import plików audio, dobrowolne mieszanie dwóch wejść DirectShow i diagnostyka PCM są zaimplementowane, lecz sprzętowe źródła dźwięku i jakość fizycznego miksu nie zostały odebrane).**

- [x] Import plików WAV/MP3/M4A/FLAC/OGG/OPUS przez FFprobe/FFmpeg i wspólną kolejkę ASR; zgodność kodeków zależy od lokalnej instalacji FFmpeg. Syntetyczne testy audio PASS, realne ASR i fizyczny Windows niezweryfikowane.
- [ ] Przechwytywanie dźwięku systemowego/loopback w Windows, w granicach możliwości i uprawnień systemu.
- [ ] Rejestrowanie mikrofonu i dźwięku systemowego jednocześnie, z osobnymi ścieżkami i świadomym mieszaniem.
- [ ] Opcjonalne źródła USB / zewnętrzny mikrofon; w przyszłości karta przeglądarki lub połączenie konferencyjne, bez obchodzenia zabezpieczeń aplikacji.
- [ ] Oznaczenia źródła i zgoda na nagrywanie; bez cichego nagrywania osób trzecich.
- [ ] Test źródeł na różnych urządzeniach, monitorowanie opóźnienia i zrywania strumienia.

**Bramka akceptacji:** każde wejście korzysta z jednego kontraktu sesji i tego samego silnika, a testy przełączania, uprawnień i utraty źródła nie powodują utraty gotowych nagrań.

### VN-06 — Stabilny program, dystrybucja i utrzymanie (v1.0)

**Cel:** przejście od kolejnych prototypów do powtarzalnych wydań Windows. **Status: W TRAKCIE (prywatny instalator Inno Setup z modelem dostarczonym przez właściciela, test rzeczywistej instalacji/deinstalacji na syntetycznym pakiecie oraz backup/restore istnieją; podpisane wydanie publiczne, prawa licencyjne i fizyczny odbiór offline nadal otwarte).**

- [ ] Installer `.exe` lub `.msi`, odinstalowanie, plik wersji, bezpieczne katalogi danych, odzyskiwanie projektów.
- [ ] **Pełny instalator offline:** wszystkie biblioteki, modele i runtime dostarczone w pakiecie; jeśli Tauri, uwzględnić instalację WebView2 bez sieci na systemach, które tego wymagają.
- [ ] Test wyłączonego internetu od instalacji, przez uruchomienie, po analizę i eksport; ponowne otwarcie po restarcie.
- [ ] Matryca kompatybilności, profilowanie RAM i dysku, ostrzeżenia o potrzebnym miejscu, tryby niskiego zużycia zasobów.
- [ ] Kontrola licencji modeli, napisów prawnych, zależności, SBOM, skanowanie dostarczanych plików, kontrola integralności artefaktów.
- [ ] Repozytorium nie przechowuje dużych modeli ani nagrań prywatnych; GitHub Releases lub inny kanał dystrybucji, hashe SHA-256.
- [ ] Rozważyć podpis cyfrowy instalatora i koszty dystrybucji; brak podpisu może wywoływać ostrzeżenia Windows.
- [ ] Stabilny eksport i import projektu, kopia bezpieczeństwa, czytelne błędy i instrukcja użytkownika.

**Bramka akceptacji:** czysta instalacja offline na Windows i pełna ścieżka OBS → tekst → notatka → eksport, testy regresji i odinstalowania; publikacja kompletnej wersji wraz z licencjami i informacją o wymaganiach sprzętowych.

### VN-07 — Integracja jako moduł Wiedora

**Cel:** zintegrować samodzielny Video Notes ze stroną Wiedora jako oddzielny, funkcjonalny moduł w katalogu aplikacji, zachowując niezależne wydania i działanie offline programu Windows. **Status: W TRAKCIE (samodzielny lokalny interfejs WWW testowany na Chrome/Firefox/Edge; portal Wiedora i Constant_app nietknięte).**

- [ ] Ustalić interfejs wejścia/wyjścia (wersjonowany JSON + pliki) i granice odpowiedzialności.
- [ ] Dodać w Wiedora kartę programu, opis i link do sprawdzonego instalatora.
- [ ] Zaimplementować i przetestować faktyczną wersję przeglądarkową jako niezależny moduł Wiedora, korzystający ze wspólnego kontraktu wyników. Nie osadzać binariów desktopowych w stronie ani nie zakładać identycznych modeli AI.
- [ ] Określić zestaw funkcji dostępnych w WWW na podstawie rzeczywistych możliwości przeglądarki; niedostępne funkcje jasno oznaczyć, zapewnić pobranie instalatora dla pełnej obsługi offline.
- [ ] Import/eksport notatek między aplikacjami; opcjonalna synchronizacja konta tylko po świadomym włączeniu.
- [ ] Test izolacji użytkowników, prywatności, regresji portalu, mobilnego UI i bezpieczeństwa uploadów.
- [ ] Prace w repozytorium Constant_app wykonywać w osobnym, jawnie zleconym zadaniu; nie zmieniać obecnej strony przy realizacji VN-00–VN-06.

**Bramka akceptacji:** Video Notes działa jako oddzielny, użyteczny moduł wewnątrz Wiedora (a nie sam odnośnik do pobrania), integracja nie wymaga konta ani internetu do pracy aplikacji Windows, nie psuje istniejących aplikacji, a kontrakt wymiany danych jest przetestowany w obu kierunkach.

### VN-08 — Rozwój opcjonalny: Android/iOS, dodatkowe formy notatek

**Cel:** rozszerzyć produkt dopiero po stabilizacji Windows. **Status: POZA PIERWSZYM WYDANIEM.**

- [ ] Aplikacja mobilna z lokalnymi lekkimi modelami, własną macierzą możliwości sprzętowych, testami baterii, RAM i działania w tle.
- [ ] Utrzymać wspólny format danych; nie zakładać, że ten sam binarny silnik z Windows zadziała na telefonie lub WWW.
- [ ] Integracja z nauką: fiszki, quizy i eksport do kursów — dopiero po zgodzie na zakres.
- [ ] Opcjonalne tłumaczenie, rozdzielanie mówców, wyszukiwanie semantyczne, wsadowe przetwarzanie wielu plików.

## C. Docelowa architektura

```
ŹRÓDŁO
  OBS MP4/MKV/WebM ─┐
  plik audio (VN-05) ├─> adaptery źródeł -> audio PCM/segmenty
  mikrofon (VN-04) ─┤                              |
  audio systemowe ──┘                              v
                                               lokalny ASR
                                                   |
                                    transcript.json + timestampy
                                                   |
                                    lokalny silnik opracowania
                                       /                 \
                              notatka prosta       notatka zaawansowana
                                       \                 /
                                        notatki + odnośniki
                                                 |
                     projekt lokalny / edytor / eksport / interfejs Windows
                                                 |
                                  przyszły adapter WWW Wiedora
```

**Warstwy:** `core` (kontrakty i przepływ), `sources` (pliki/urządzenia), `media` (FFmpeg), `asr` (silnik wymienny), `notes` (opracowanie wymienne), `storage`, `exporters`, `desktop-ui`, `tests`. Logika nie powinna zależeć od interfejsu użytkownika. Projekt zapisuje wybrany model, jego wersję, tryb, język, znacznik źródła i parametry; wyniki są deterministycznie rozpoznawalne po ID fragmentu, aby wznowienie nie tworzyło duplikatów.

**Wstępni kandydaci (niezatwierdzeni):** FFmpeg do demux, `whisper.cpp`/`faster-whisper` do ASR, Tauri do desktopu, lokalny mały model uruchamiany np. przez `llama.cpp` do notatek, Tesseract OCR dopiero w VN-03B. Decyzję podejmujemy na podstawie testów, wymagań sprzętowych i licencji, nie samej popularności.

**Kontrakt wymiany:** wersjonowane `project.json` (schemat, pliki i ustawienia), `transcript.json` (segmenty: id, start_ms, end_ms, text, source_track, status), `notes.md`/`notes.json` (sekcje i powiązania do segmentów) oraz katalog `exports/`. Nazwy, finalny schemat i migracje zatwierdzić w VN-00. Przechowywanie nie może zależeć od serwera, Supabase ani Netlify.

## D. Testy, które muszą przejść przed wersją 1.0

**Próbki kontrolne:**
- 5–10 min wyraźnego wykładu po polsku (nazwiska, liczby, interpunkcja).
- 5–10 min angielskiego tutorialu technicznego (komendy, skróty, liczby).
- OBS MP4 z jedną ścieżką, MKV z dwiema ścieżkami (mikrofon + komputer), wideo 2+ h.
- Materiał ze slajdami i materiał ze zmieniającym się ekranem (dopiero VN-03B).
- Plik bez audio, uszkodzony, nieobsługiwany kodek, pusty, dysk z małą ilością miejsca.
- Rzeczywista sesja mikrofonowa 30 min i dłuższy test (VN-04), w tym odłączenie urządzenia.

**Miary:** błędy rozpoznawania na małej transkrypcji referencyjnej (WER), poprawność znaczników czasu, kompletność segmentów, wykryte pominięcia, zużycie RAM/CPU/dysku, czas na minutę nagrania, liczba odzyskanych segmentów, zgodność eksportu. Przed ustaleniem progów ilościowych wykonać benchmark VN-00 i zatwierdzić minimalną klasę sprzętu. Nie obiecywać z góry identycznej jakości na 4 GB RAM i mocnym PC.

**Jakość notatek:** każda stwierdzona informacja konkretna (zwłaszcza liczba, komenda, definicja, data) musi mieć ślad w transkrypcji albo później zweryfikowanym obrazie; niepoparte treści to błąd. Ręczna ocena przez zestaw kontrolnych oczekiwanych zagadnień, jawne oznaczenie niepewności i pominięć.

**Offline:** odłączone Wi-Fi/Ethernet jeszcze przed instalacją pełnego pakietu; instalacja, restart, przetwarzanie MP4/MKV, wygenerowanie notatki i eksport muszą zadziałać bez wywołań do zdalnego API. Sprawdzić brak prób połączeń w logach sieciowych.

**Regresja:** po każdym etapie testy własnej funkcji, zachowania poprzednich etapów, ponownego otwarcia istniejących projektów, anulowania i wznowienia, eksportu, zarządzania modelami i próby pracy bez internetu. Testy sprzętowe nie są zastępowane testami jednostkowymi.

## E. Zarządzanie zadaniami i Definition of Done

Statusy: `PLANOWANE`, `W TRAKCIE`, `WDROŻONE BEZ TESTU ZEWNĘTRZNEGO`, `WDROŻONE I PRZETESTOWANE`, `ZABLOKOWANE`. Nie oznaczamy fazy jako ukończonej na podstawie samego commita.

Każde zadanie musi posiadać: zakres, zależności, listę kryteriów akceptacji, wskazanie zmienionych plików, sposób uruchomienia testów, wyniki PASS/FAIL/NOT_RUN, ryzyka, numer wersji/commit oraz kolejny krok. Obowiązuje zasada „nie psujemy już działających funkcji”.

**Brama wejścia do następnej fazy:** główna ścieżka aktualnej wersji działa, wymagane testy są potwierdzone na rzeczywistym sprzęcie i nie istnieje krytyczny błąd danych. Jeżeli coś jest zablokowane, status pozostaje jawny, a wyjątek wymaga osobnej decyzji.

**Organizacja pracy:** `main` jako stabilna gałąź; rozwój na krótkich gałęziach/PR albo `develop` po utworzeniu i uzgodnieniu procesu. Modeli, nagrań prywatnych, haseł i tokenów nie commitujemy. Dokumentacja stanu programu jest aktualizowana przy każdej zmianie zachowania. Publiczne issue nie może zawierać prywatnego nagrania ani transkrypcji użytkownika.

## F. Ryzyka i decyzje do walidacji

| Ryzyko | Jak je ograniczamy |
| --- | --- |
| Duży plik OBS i wielościeżkowy MKV | Strumieniowy demux, świadomy wybór ścieżki i testy plików 2+ h |
| Wolne CPU i niewystarczający RAM | Benchmark kilku modeli, tryby jakości, mierzone wymagania, przyjazne ostrzeżenia |
| Błędne nazwiska i komendy ASR | Edytor, znaczniki czasu, testy polskiego i angielskiego, oddzielenie tekstu surowego od poprawionego |
| Halucynacje w notatkach | Powiązanie z segmentami, kontrola źródeł, testy liczb i komend, oznaczanie niepewności |
| Awarie i utrata danych | Zapis atomowy, checkpointy, test restartu i uszkodzenia pliku |
| Ukryta zależność od sieci | Instalacja offline z wszystkimi modelami i runtime, test wyłączonej sieci |
| Licencje redystrybucyjne modeli i zależności | Rejestr licencji, kontrola przed publikacją każdego modelu i instalatora |
| Zbyt rozbudowany zakres MVP | VN-01 obejmuje tylko transkrypcję; notatki, mikrofon i inne źródła są osobnymi fazami |
| Ryzyko naruszenia prywatności przy mikrofonie/system audio | Wymagana widoczna zgoda i wskaźnik nagrywania, żadnych ukrytych nagrań |
| Kolidowanie z Wiedora | Pełna niezależność repo do VN-06; osobna zgoda, test i wydanie integracji w VN-07 |

## Postęp implementacji 06.11.2026

W tym repo przygotowano źródłowy prototyp: kontrakty i lokalny zapis atomowy, wykrywanie ścieżek przez FFprobe, dzielenie nagrania FFmpeg, adapter lokalnego `whisper-cli`, CLI i wstępny interfejs Tkinter, eksporty TXT/SRT/VTT/JSON oraz poprawki bez modyfikowania surowego wyniku. Test lokalny Linux/Python/FFmpeg na syntetycznych WAV/MKV: **19/19 PASS**. Silnik rozpoznawania mowy był w teście atrapą, nie rzeczywistym modelem. Żaden z etapów VN-00/VN-01 nie jest formalnie zamknięty; potrzeba pomiaru prawdziwego ASR, benchmarku dwóch silników i pełnego Windows offline. VN-02…VN-08 bez zmian; repo Wiedora bez zmian.

Dowody i ograniczenia: `docs/VN00_IMPLEMENTATION.md`; schemat: `docs/CONTRACT_V1.md`.

## Postęp implementacji VN-02 — 06.11.2026

Dodano generowanie lokalnej notatki ekstrakcyjnej (dobór cytatów na podstawie czasu i powtarzających się słów), niezależną edycję punktów, znaczniki czasu i identyfikatory segmentów, eksport Markdown oraz widok i edytor GUI. Notatka zostaje odrzucona, jeśli źródłowa poprawiona transkrypcja uległa zmianie. **To etap W TRAKCIE**, bez inteligentnego streszczenia, oceny jakości na prawdziwych wykładach, eksportu DOCX/PDF i wersjonowanej regeneracji. Szczegóły: `docs/VN02_NOTES.md`.

Dodatkowo wykonano narzędzie porównania WER/CER na dwóch gotowych TXT, ale bez wykonania prawdziwego ASR, pomiaru czasu i RAM — **VN-00 pozostaje W TRAKCIE** (`docs/ASR_QUALITY_BENCHMARK.md`).

## Stan repozytorium po PR #3 i #4 — 06.11.2026

**Jedynym repo roboczym KWN jest `Video-notes`.** PR #3 (`develop`: `064ebf7625b7895e88fe2e34f59471bab7fa88dc`) dodał lokalne notatki ekstrakcyjne z cytatami/edycją i porównanie WER/CER gotowych TXT. GitHub Actions #42247184304: 37/37 Linux PASS i 27/27 Windows PASS. PR #4 (`develop`: `1d9022450f0792631161090f22ecb95835c88f84`) dodał przenośną kopię bez mediów, SHA-256, bezpieczne odtworzenie i relink; Actions #42248878505: **46/46 Linux PASS i 36/36 Windows PASS**. Weryfikacja Windows obejmuje testy kontraktów i backupu, **nie** realne działanie pełnego ASR, FFmpeg i instalatora na fizycznym urządzeniu.

**Etapy formalne:** VN-00, VN-01, VN-02, VN-05, VN-06 = W TRAKCIE; VN-03, VN-04, VN-07, VN-08 = PLANOWANE. Żaden etap nie otrzymał DONE, ponieważ nie przeszedł wszystkich bramek odbiorowych. Historyczny rejestr KWN (189 kryteriów i 22 etapy) w `Constant_app` nie jest automatycznie równoważny dziewięciu etapom VN. Szczegółowy stan i bramki: `docs/VN_STATUS.json`, `docs/VN_LOCAL_BACKUP.md`, `docs/VN02_NOTES.md`, `docs/ASR_QUALITY_BENCHMARK.md`.

**Dalsze zadania krytyczne:** legalne próbki PL/EN OBS i modele do realnego ASR, rzetelny benchmark whisper.cpp vs faster-whisper wraz z WER/RAM/czasem i licencjami, wersjonowane poprawki notatek z możliwością regeneracji, wygodny instalator Windows offline z potrzebnymi bibliotekami i modelem, testy urządzeń, test pliku 2h, a dopiero potem zbiorcza aktualizacja portalu Wiedora. Główna gałąź `main` Video-notes i host `Constant_app` pozostają bez zmian.

## Postęp 06.11.2026 — PR #6, #7, #8

PR #6: historia regeneracji notatek (Linux 56/56, Windows 46/46 PASS). PR #7: realny runner dwóch lokalnych silników ASR z opcjonalnym pomiarem RAM, ale testowany automatycznie **tylko atrapami** (Linux 63/63, Windows 53/53 PASS). PR #8: import dodatkowych formatów audio i testy rzeczywistego dekodowania FFmpeg oraz symulowanego ASR (Linux 66/66, Windows 53/53 PASS). Ostrzeżenia o końcowym, niedekodowalnym paddingu MP3 są zapisywane jawnie. Mimo tego żaden etap nie przeszedł wszystkich kryteriów odbioru; liczniki: 5 W TRAKCIE, 4 PLANOWANE, 0 DONE. Do formalnego zamknięcia VN-00/VN-01/VN-02/VN-05/VN-06 nadal potrzebny prawdziwy model PL/EN, testy użytkownika i rzeczywisty Windows offline. Bieżący rejestr: `docs/VN_STATUS.json`.

## G. Pierwsze pięć zadań do wykonania

1. Przygotować fixtures nagrań OBS (legalne/testowe, bez publikowania danych prywatnych).
2. Wykonać spike **FFmpeg → właściwa ścieżka audio → lokalny ASR → TXT/SRT** na Windows.
3. Porównać `whisper.cpp` i `faster-whisper` na tej samej próbce; zapisać benchmark i wybór silnika.
4. Zatwierdzić schemat projektu i interfejs silnika bez zależności od GUI.
5. Utworzyć minimalny ekran importu/transkrypcji i realizować VN-01 do pierwszej instalowalnej wersji.

## H. Rejestr decyzji

| ID | Decyzja | Status |
| --- | --- | --- |
| D-001 | Aplikacja jest samodzielnym produktem, niezależnym od Constant_app | ZATWIERDZONY KIERUNEK |
| D-002 | Windows offline-first, bez obowiązkowych płatnych API | ZATWIERDZONY KIERUNEK |
| D-003 | Kolejność: OBS → transkrypcja → notatki proste → zaawansowane → mikrofon → inne źródła | ZATWIERDZONA KOLEJNOŚĆ |
| D-004 | Język interfejsu pierwszej wersji: polski, kod przygotowany pod i18n | PROPOZYCJA |
| D-005 | Wybór silnika ASR, modeli, GUI i pakietowania | OTWARTE — VN-00 |
| D-006 | Konkretny minimalny sprzęt, wielkość pakietu i progi benchmarków | OTWARTE — VN-00 |
| D-007 | Licencja własnego projektu i zasady publicznej dystrybucji | OTWARTE — VN-00 |
| D-008 | Docelowy samodzielny, funkcjonalny moduł Video Notes wewnątrz Wiedora, bez zależności programu Windows od portalu; szczegóły adaptera WWW do ustalenia | KIERUNEK ZATWIERDZONY; TECHNOLOGIA OTWARTA — VN-07 |
| D-009 | Wzorzec to `apps/notatki/`; `apps/konwerter/` pozostaje osobnym produktem | ZATWIERDZONE |

---

**Zasada aktualizacji:** w tym planie przy każdej fazie wpisujemy datę, link do issue/PR, ostatni zweryfikowany commit, wynik testów i faktyczny status. Bez takich danych etap pozostaje PLANOWANE. Ten dokument jest planem, nie raportem wykonanych funkcji.

## E. Aktualizacja dużych wdrożeń (08.11.2026)

**PR #72 – VN-02/VN-03:** odrębny offline `study-guide` i GUI: spis treści, źródłowe cytaty, podpowiedzi terminów, heurystyczne definicje i przykłady oraz lista niepewności; eksport MD/JSON/DOCX/PDF. Prawdziwy whisper.cpp PL/EN na syntetycznej mowie, realne Tk Windows i Linux, LibreOffice; **10/10 automatycznych kontroli PASS**. Nie jest to semantyczne podsumowanie AI.

**PR #73 – VN-06:** w pełni skompilowany wewnętrzny instalator Inno Setup Windows EXE z lokalnie dostarczonym modelem i narzędziami, wymagający jawnej zgody `--internal-only`. Testowane rzeczywiste pakowanie, cicha instalacja, SHA-256 i deinstalacja **syntetycznych nieuruchamialnych plików** na GitHub-hosted Windows; **7/7 PASS**. Nie stanowi podpisanego wydania 1.0.

**PR #74 – VN-01/VN-03:** realne dekodowanie 121-minutowego OGG/Opus przez FFmpeg, zatrzymanie po 12. fragmencie, idempotentne wznowienie, eksport, 61/61 oznaczonych źródłem cytatów przewodnika i DOCX. **6/6 PASS**, ale rozpoznawanie mowy jest w tym scenariuszu jawnie atrapą.

**PR #75 – VN-03:** `study-verify` + „Sprawdź źródła” w GUI pozwalają bez zmian danych odrzucić nieaktualny lub zmodyfikowany JSON przewodnika. Poświadcza pochodzenie słów i znaczniki czasu, a nie poprawność ASR lub faktów. Prawdziwy whisper.cpp na PL/EN TTS oraz wszystkie regresje **11/11 PASS**.

Te zmiany **nie upoważniają do oznaczenia całego etapu jako DONE**, bo wymagania odbioru obejmują m.in. prawdziwe próbki mowy, WER/CER z oceną człowieka, testy mikrofonu/dźwięku systemowego na Windows, instalację z siecią odłączoną przy prawdziwym legalnym modelu, decyzje licencyjne, dostępność i podpisanie wydania. Jedyną wiążącą ewidencją pozostaje `docs/VN_STATUS.json`. Rozwój odbywa się wyłącznie w `Video-notes`, bez zmian hosta Wiedora/Netlify.

## G. Duży pakiet nagrywania i diagnostyki — 08.11.2026

**PR #77 (VN-04)** — pełna implementacja **Pauza/Wznów**: zamknięcie FFmpeg poleceniem `q`, atomowe potwierdzanie kolejnych WAV w jednorazowych folderach `.vn-take-*`, kontrola SHA-256, dziennik `recording/paused/finished/needs_review`, bez nadpisywania wcześniejszych ujęć, rzeczywiste przyciski Tk. Odkryto i obejście potwierdzono realnym FFmpeg: muxer segmentowy potrafi ignorować globalne `-n`. **8/8 CI PASS** — [standard Linux/Windows](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479432972), [real Tk Windows/Linux](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479432973), [DEV EXE](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479432971).

**PR #78 (VN-04/VN-05)** — offline analiza gotowych WAV w CLI i GUI: średnie RMS, peak dBFS, udział próbek bliskich przesterowaniu, czas ciszy i ostrzeżenia. Działa bez modelu, w blokach po 2 sekundy, z kontrolą stanu i SHA-256; nie publikuje prywatnego dźwięku. **9/9 CI PASS** — [standard Linux/Windows](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479769485), [real Tk Windows/Linux](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479769582), [Inno setup syntetyczny](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479769460), [DEV EXE](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42479769480).

**PR #79 (VN-04)** — pełny przebieg **realnego procesu FFmpeg** z syntetyczną falą sinusoidalną (nie atrapą procesu): 2 rzeczywiste ujęcia, zamknięcie `q`, pauza/wznowienie, różne PCM, SHA, bezstratne łączenie i numeryczna analiza. **6/6 CI PASS** — [dedykowany real FFmpeg smoke](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42480072624), [standard Linux/Windows](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42480072912).

**Pozostaje warunkiem pełnego odbioru VN-04/VN-05:** fizyczny Windows 10/11 z prawdziwym mikrofonem, niezależnie podanym wejściem systemowym, aktywną zgodą użytkownika, przerwą i wznowieniem po dłuższej sesji, testem USB unplug/uśpienia/dysku pełnego i dwugodzinnym testem w praktyce. Nie było rzeczywistego odsłuchu ani pomiaru jakości mowy. Formalne liczniki: **0/9 DONE, 8/9 W_TRAKCIE, 1/9 PLANOWANE**.
