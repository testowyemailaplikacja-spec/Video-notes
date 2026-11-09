# Video Notes

**Samodzielna aplikacja do transkrypcji i tworzenia notatek z nagrań oraz dźwięku na żywo.**

Video Notes powstaje na bazie doświadczeń modułu **[Notatki](https://github.com/testowyemailaplikacja-spec/Constant_app/tree/develop/apps/notatki)** z platformy Wiedora (Constant App). **Konwerter plików jest osobnym projektem i nie wchodzi w zakres Video Notes.**

## Aktualne moduły KWN / Video Notes (06.11.2026)

Wszystkie funkcje są rozwijane wyłącznie w tym repozytorium; gałąź `develop` zawiera przetestowane integracje, `main` pozostaje stabilnym punktem odniesienia. Obecny rejestr: **0/9 etapów DONE, 8/9 W TRAKCIE, 1/9 PLANOWANY**. To osobny stan od historycznych 189 kryteriów KWN w Wiedora.

- **VN-03:** Konspekt źródłowy z cytatami, czasami, rozdziałami i szablonami: `python -m videonotes advanced-notes moje-notatki --template lecture --detail standard`. Edytowalne notatki podstawowe pozostają odrębne; nie ma automatycznego semantycznego streszczenia. [Dokumentacja](docs/VN03_OUTLINES.md).
- **VN-04:** Lokalny mikrofon na Windows przez DirectShow/FFmpeg: `python -m videonotes record-devices` oraz `python -m videonotes record-mic --device "Microphone (USB)" --output NOWY_KATALOG --consent`. Dostępne także dialog w GUI, kontrola Start/Stop i zapis WAV co 2 godziny. Potrzebny fizyczny test sprzętowy. [Dokumentacja](docs/VN04_MICROPHONE_CAPTURE.md).
- **VN-05:** Opcjonalne miksowanie mikrofonu i osobno zatwierdzonego urządzenia system audio (np. Stereo Mix): `record-mic --device ... --system-device ... --consent --consent-system`; dostępne także w GUI. Wymaga realnego wejścia DirectShow. [Instrukcja](docs/VN05_DUAL_DEVICE_CAPTURE.md).
- **VN-06:** `python -m videonotes bundle-dev ... --internal-only` składa z *własnych*, lokalnych plików prywatny pakiet testowy z DEV EXE, FFmpeg/FFprobe, Whisper CLI i modelem. To **nie jest publiczny instalator** ani potwierdzony sprzętowo produkt offline. [Instrukcja i ograniczenia](docs/VN06_PRIVATE_BUNDLE.md).

CI sprawdza kod źródłowy na Linux i Windows oraz plik Windows DEV EXE. **Nie potwierdza rzeczywistej jakości polskiej transkrypcji ani działania pełnego zestawu na fizycznym Windows bez internetu.** Wymagane są rzeczywiste modele, sprawdzenie licencji, próbki użytkownika dostępne legalnie i urządzenia do odbioru.

## Wersja przeglądarkowa offline — prototyp VN-07

Otwórz lokalnie `web/index.html` i wybierz plik `exports/transcript.json` utworzony przez program Windows/Python (`python -m videonotes export KATALOG_PROJEKTU`). Możesz bez serwera i internetu przeszukiwać wypowiedzi, nanosić poprawki i pobierać TXT/SRT/VTT/JSON. **Nie ma jeszcze transkrypcji ASR w przeglądarce ani integracji z Wiedorą.** [Instrukcja i ograniczenia](docs/VN07_WEB_ADAPTER.md).

**Eksport DOCX dla konspektu (VN-03):** dodaj opcję `--docx` do polecenia `advanced-notes`, aby otrzymać `exports/notes-advanced.docx` z cytatami i znacznikami czasu, bez API lub instalacji pakietów. Nie jest to podsumowanie semantyczne ani PDF. Etap VN-03 nadal W TRAKCIE.

## Kolejność rozwoju

1. **VN-00** — fundamenty programu, analiza istniejących Notatek i wybór lokalnego silnika transkrypcji.
2. **VN-01** — import nagrań OBS (MP4/MKV/WebM), wyodrębnienie mowy i transkrypcja 1:1 ze znacznikami czasu, eksport TXT/SRT.
3. **VN-02** — podstawowe notatki z transkrypcji: tytuły, punkty, streszczenie i możliwość edycji.
4. **VN-03** — zaawansowane notatki: konspekty, rozdziały, terminologia, cytaty źródłowe, opcjonalna analiza slajdów.
5. **VN-04** — nagrywanie wykładu mikrofonem na żywo i późniejsza transkrypcja.
6. **VN-05** — dodatkowe źródła dźwięku, np. audio systemowe, z kontrolą zgód i urządzeń.
7. **VN-06** — dopracowanie aplikacji Windows, instalacja, wydania offline i testy.
8. **VN-07** — zintegrowanie jako **oddzielnego modułu Wiedora** bez uzależniania działania samodzielnego programu od portalu.
9. **VN-08** — opcjonalne warianty mobilne.

## Założenia

- Pierwsza wersja dla Windows, bez obowiązkowego konta, płatnego API i przesyłania nagrań do chmury.
- Użytkownik zachowuje nagrania, transkrypcje i notatki lokalnie.
- Transkrypcja 1:1 nie oznacza gwarancji bezbłędnego rozpoznawania słów.
- Pracujemy etapami. **Kopia istniejącego kodu Notatek stanowi materiał referencyjny, nie potwierdzenie ukończenia programu Windows.**
- **Nie implementujemy w tym repozytorium konwersji PDF/DOC/DOCX/obrazów/MP3 itp. jako osobnego konwertera.** Przetwarzanie audio potrzebne do transkrypcji (np. odczyt ścieżki z filmu OBS) należy do Video Notes.

Dokument główny projektu: [Plan rozwoju Video Notes](docs/PLAN_ROZWOJU_VIDEO_NOTES.md). Analiza źródła: [Notatki w Constant App](docs/ANALIZA_NOTATEK_WIEDORA.md).

## Pierwszy historyczny prototyp

- **Pierwszy etap 06.11.2026: VN-00 i VN-01 W TRAKCIE.** Dodano lokalny prototyp źródłowy Python z FFmpeg/FFprobe, opcjonalnym whisper.cpp, CLI, GUI Tkinter, checkpointami i eksportem.
- **19/19 testów PASS** lokalnie na Linux z syntetycznymi próbkami. Realny silnik ASR i instalator Windows nie były jeszcze testowane; żaden etap nie jest DONE.
- `Constant_app` pozostaje bez zmian; prace prowadzone są wyłącznie tutaj.
- Repozytorium źródłowe Wiedora pozostaje bez zmian.

## Uruchomienie kodu rozwojowego VN-00 / VN-01 / VN-02

Wymagania: Python 3.10+, FFmpeg/FFprobe, lokalny program `whisper-cli` i legalnie pozyskany model `.bin`. Brak automatycznego pobierania modeli, kont i usług w chmurze. To nie jest jeszcze samodzielny instalator Windows.

```bash
python -m videonotes inspect nagranie.mkv
python -m videonotes transcribe nagranie.mkv --project moje-notatki --model ggml-base.bin --whisper-cli whisper-cli --language pl --stream 1
python -m videonotes resume moje-notatki
python -m videonotes export moje-notatki
python -m videonotes gui
python -m unittest discover -s tests -v
```

Indeks `--stream` należy odczytać poleceniem `inspect`. Przy wielu ścieżkach dźwiękowych trzeba go wybrać jawnie. Program zachowuje surowe segmenty w `transcript.json`, poprawki w `edits.json`, a cztery formaty eksportu w katalogu `exports`. Szczegółowe ograniczenia opisują `docs/VN00_IMPLEMENTATION.md` i `docs/CONTRACT_V1.md`.

## Notatki podstawowe (VN-02, prototyp)

Po zakończeniu pełnej transkrypcji uruchom:

```bash
python -m videonotes notes moje-notatki --window-minutes 5 --points 6
python -m videonotes notes-edit moje-notatki --point quote-c0000000-s00000 --text "Moja poprawiona notatka"
python -m videonotes notes-export moje-notatki
```

Notatka jest **ekstrakcyjna**, a nie wygenerowana przez model językowy: pokazuje tylko wybrane rzeczywiste wypowiedzi z transkrypcji wraz ze znacznikiem czasu i identyfikatorem segmentu. Ręczne zmiany nie naruszają surowej transkrypcji. Dostępny jest również widok notatek w GUI. Etap VN-02 pozostaje W TRAKCIE, ponieważ brakuje m.in. pełnego semantycznego opracowania, testów jakości na rzeczywistych wykładach i wersjonowanej regeneracji. Szczegóły: [VN02_NOTES.md](docs/VN02_NOTES.md).

## Pomiar jakości ASR (narzędzie VN-00, nie benchmark silników)

```bash
python -m videonotes benchmark --reference prawdziwy_tekst.txt --candidate whisper_cpp=wynik_cpp.txt --candidate faster_whisper=wynik_faster.txt --output wer_cer.json
```

Program porównuje lokalne pliki TXT, wylicza WER/CER i zapisuje **wyłącznie skróty SHA-256 i liczby**, bez tekstów nagrań. **Nie uruchamia** żadnego silnika ASR, nie dowodzi jego jakości, nie mierzy RAM/czasu i nie wysyła plików. Aby zamknąć VN-00, należy wykonać prawdziwy, kontrolowany eksperyment obu silników. Instrukcja: [ASR_QUALITY_BENCHMARK.md](docs/ASR_QUALITY_BENCHMARK.md).

## Historyczny punkt kontrolny po PR #3 i #4 (06.11.2026)

Kod **PR #3 i #4** jest w `develop`; `main` pozostaje bez zmian. Testy [CI #42248878505](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42248878505): **46/46 PASS Linux, 36/36 PASS Windows** (Windows obejmuje kontrakty, notatki i archiwum, nie całe urządzenie i ASR). Nie wykonano jeszcze pełnego benchmarku prawdziwego modelu Whisper ani testu kompletnego instalatora Windows. **Żaden etap nie jest formalnie DONE.** Aktualny status 9 etapów: [VN_STATUS.json](docs/VN_STATUS.json) — 8 W TRAKCIE, 1 PLANOWANY, 0 DONE. Nie przenosimy tego postępu automatycznie do historycznego rejestru 189 kryteriów w głównym repo Wiedory.

## Przenośna kopia projektu (VN-01/VN-06, wersja rozwojowa)

```bash
python -m videonotes backup moje-notatki --output kopia.vnproj
python -m videonotes restore kopia.vnproj --project odzyskane-notatki
python -m videonotes relink odzyskane-notatki --source nagranie.mkv --model ggml-base.bin --whisper-cli whisper-cli
```

Kopia lokalna zawiera transkrypcję i notatki, ale **nie nagranie, model ani binaria**. Usuwa ze skopiowanych metadanych bezwzględne ścieżki do lokalnych plików i sprawdza integralność SHA-256. Po przywróceniu można przeglądać tekst offline; wznowienie ASR wymaga ponownego podłączenia identycznego źródła i modelu. Kopia zawiera treść użytkownika, dlatego nie należy udostępniać jej publicznie. Funkcja nie oznacza jeszcze pełnego odbioru systemu backupów ani etapu VN-06. [Opis i ograniczenia](docs/VN_LOCAL_BACKUP.md).

### Historia i odbudowa notatek

Po późniejszej poprawce transkrypcji można wykonać `python -m videonotes notes-regenerate moje-notatki`, sprawdzić wcześniejsze wersje komendą `notes-history` i przywrócić zgodną wersję przez `notes-restore --revision <ID>`. Ręczne uwagi do nadal istniejących segmentów są zachowywane; zmiany do usuniętych segmentów pozostają w lokalnej historii. Funkcja dostępna jest także w GUI. [Dokładne zasady](docs/VN02_HISTORY.md).

## Rzeczywisty benchmark dwóch lokalnych silników (narzędzie VN-00)

Po zainstalowaniu lokalnych modeli `whisper.cpp` oraz `faster-whisper` można uruchomić `python -m videonotes benchmark-real` na tym samym fragmencie OBS. Otrzymasz WER/CER, czas obliczeń i — gdy dostępny jest opcjonalny `psutil` — RAM. Wykorzystuje realne procesy silników, nie tylko dwa gotowe pliki TXT. Pełna instrukcja: [REAL_ASR_LAB.md](docs/REAL_ASR_LAB.md). **Sam kod i testy z atrapami nie są dowodem rzeczywistej jakości rozpoznawania polskiej mowy.**

## Import audio (część VN-05)

Transkrypcję można uruchamiać również z plików WAV, MP3, M4A, FLAC, OGG i OPUS, nie tylko z filmów OBS. Dekodowanie odbywa się lokalnie przez FFmpeg i korzysta z tych samych checkpointów i eksportów. Obsługa zależy od zainstalowanych kodeków FFmpeg. Nagrywanie dźwięku systemowego i urządzeń jest nadal osobnym, nieukończonym zadaniem. [Opis i testy](docs/VN05_AUDIO_IMPORT.md).

**Bieżące wyniki regresji PR #8:** [66 testów Linux i 53 Windows PASS](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42295088894). To testy kodu, a nie odbiór fizycznego urządzenia ani realnej dokładności ASR.

## Wersja wykonywalna Windows (test developerski)

GitHub Actions buduje `VideoNotes-DEV.exe` i uruchamia testy podstawowego CLI na Windows. Artefakt jest oznaczony **DEV-NOT-OFFLINE**, nie zawiera FFmpeg ani modeli Whisper i nie jest jeszcze pełnym instalatorem. [Szczegóły i bramki wydania](docs/VN06_WINDOWS_DEV_BUILD.md).

**Przetestowany artefakt Windows DEV:** [GitHub Actions #42296659497](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42296659497), wynik SUCCESS. Do pobrania jest tymczasowy ZIP z `VideoNotes-DEV.exe` i SHA-256, ale **bez modelu ASR i FFmpeg**; nie jest to wydanie stabilne.

## Wielogodzinne nagrania mikrofonowe (VN-04, wersja rozwojowa)

Po ukończeniu sesji podzielonej na części `part-00000.wav`, `part-00001.wav` itd. nie należy transkrybować wyłącznie pierwszej części jako całego wykładu. W GUI wybierz **„Połącz części ukończonego nagrania WAV do transkrypcji”**, wskaż folder sesji i potwierdź lokalne połączenie. Alternatywa CLI:

```bash
python -m videonotes record-status KATALOG_SESJI
python -m videonotes record-join KATALOG_SESJI --output KATALOG_SESJI/recording-full.wav
python -m videonotes inspect KATALOG_SESJI/recording-full.wav
```

Program sprawdza ciągłość WAV i dziennik `finished`, nie nadpisuje gotowych plików, zachowuje oryginalne części, zapisuje nowy wynik atomowo i wymaga dodatkowego wolnego miejsca. Standardowy WAV ma limit około 4 GB. Testy automatyczne PR #63 i #64 są zielone, lecz **nie wykonano fizycznego testu mikrofonu Windows ani 2-godzinnej sesji**. Szczegóły: [VN04_MICROPHONE_CAPTURE.md](docs/VN04_MICROPHONE_CAPTURE.md).

## Przewodnik do nauki z cytatami (VN-02/03)

Video Notes pozwala przygotować **źródłowy przewodnik do nauki** z ukończonej transkrypcji. Program tworzy spis treści, chronologiczne cytaty ze znacznikami czasu, powtarzające się pojęcia, możliwe definicje, przykłady i fragmenty wymagające sprawdzenia. Całość jest lokalna i nie wykorzystuje płatnego API.

```powershell
python -m videonotes study-guide C:\\Notatki\\wyklad-001 --section-minutes 10 --detail full --docx
```

W interfejsie Windows jest przycisk **„Przewodnik do nauki — cytaty, pojęcia i pytania (VN-02/03)”**, z wyborem szczegółowości i opcjonalnym eksportem PDF przez lokalne LibreOffice. Zapisuje oddzielne `notes-study.md`, `notes-study.json` i opcjonalne DOCX/PDF; nie zastępuje oryginalnego rozpoznania ASR, notatki podstawowej ani historii poprawek. **Nie jest to semantyczne streszczenie AI; każda informacja pozostaje dosłownym cytatem źródłowym i wymaga weryfikacji.**

Instrukcja: [VN_STUDY_GUIDE.md](docs/VN_STUDY_GUIDE.md).

## Prywatny instalator Windows offline (VN-06 — testy wewnętrzne)

Po przygotowaniu legalnych lokalnych plików `VideoNotes-DEV.exe`, `ffmpeg.exe`, `ffprobe.exe`, `whisper-cli.exe` i modelu GGML możesz stworzyć zweryfikowaną prywatną paczkę `bundle-dev`, a następnie **rzeczywisty instalator Inno Setup EXE**, który zawiera te pliki bez automatycznego pobierania podczas instalacji:

```powershell
python -m videonotes bundle-verify C:\\Test\\VideoNotes-PRIVATE
python -m videonotes installer-dev --bundle C:\\Test\\VideoNotes-PRIVATE --iscc "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe" --output C:\\Test\\VideoNotes-PRIVATE-Setup.exe --internal-only
```

To **wyłącznie niepodpisana wersja do testów wewnętrznych**, bez prawa do publicznej dystrybucji niezweryfikowanych modeli i zależności. Testy Windows CI na syntetycznych plikach nie zastępują fizycznego sprawdzenia całkowicie offline. Instrukcja: [VN06_PRIVATE_INSTALLER.md](docs/VN06_PRIVATE_INSTALLER.md).

## Mikrofon Windows: Pauza/Wznów, ochrona nagrań i kontrola sygnału (VN-04/05)

Podczas lokalnego nagrywania w interfejsie Windows możesz kliknąć **Pauza** — FFmpeg domknie aktualny WAV, zachowa SHA-256 i przerwie rejestrowanie — a potem **Wznów nagrywanie** do nowej części bez nadpisywania poprzedniej. Zatrzymanie w pauzie finalizuje dotychczas nagrane audio. Kompletne części połączysz przyciskiem **„Połącz części ukończonego nagrania WAV do transkrypcji”**.

Program zapisuje nowe ujęcia w oddzielnych folderach `.vn-take-*` i potwierdza ich integralność przed atomowym przeniesieniem do głównej sesji. W przypadku awarii tych folderów **nie usuwa**, a `record-status` pokazuje je do ręcznej kontroli. Dzięki temu nie polega na nieskutecznej ochronie FFmpeg `-n` dla segmentów.

Dla ukończonego nagrania możesz także wybrać **„Sprawdź jakość nagrania WAV — cisza i przesterowanie”** albo:

```powershell
python -m videonotes record-status C:\\Nagrania\\wyklad-001
python -m videonotes record-analyze C:\\Nagrania\\wyklad-001
```

Kontrola pokazuje RMS/peak w dBFS, udział bardzo cichego dźwięku i clippingu, bez udostępniania audio lub transkrypcji. Automatyczne testy używają syntetycznego PCM i rzeczywistego FFmpeg, ale **nie zastępują testów fizycznego mikrofonu, DirectShow, dwóch źródeł audio ani dwugodzinnej sesji Windows**.

Instrukcja i bramki odbiorowe: [VN04_MICROPHONE_CAPTURE.md](docs/VN04_MICROPHONE_CAPTURE.md).

## Konspekty ze źródłowymi kategoriami — wykład, instruktaż, spotkanie, nauka (VN-03)

W konspekcie zaawansowanym możesz wybrać **cztery rzeczywiście odmienne szablony**. Program wyodrębnia dokładne cytaty z transkrypcji jako możliwe definicje i przykłady (wykład), wypowiedziane kroki/ostrzeżenia i sposób sprawdzenia (instruktaż), wzmianki o decyzjach i zadaniach (spotkanie) albo pytania do powtórki (nauka). Wszystkie informacje mają czas nagrania i ID źródła; dopasowanie do kategorii ma charakter heurystyczny, bez generowania faktów.

W GUI wybierasz szablon, poziom szczegółowości i długość części. Możesz wyświetlić źródłowy konspekt, wyeksportować DOCX/PDF i sprawdzić zgodność zapisanego JSON z aktualną transkrypcją. Istniejące eksporty nie są automatycznie nadpisywane po otwarciu okna.

```powershell
python -m videonotes advanced-notes C:\\Notatki\\wyklad --template tutorial --detail full --docx
python -m videonotes advanced-verify C:\\Notatki\\wyklad
```

Opis kategorii i ograniczeń: [VN03_FUNCTIONAL_TEMPLATES.md](docs/VN03_FUNCTIONAL_TEMPLATES.md). To **narzędzie porządkowania cytatów**, nie semantyczne streszczenie ani pełny odbiór VN-03.

## Klikalne źródła w notatkach (VN-02/VN-03)

Z notatki podstawowej, zaawansowanej oraz przewodnika do nauki można teraz **przejść bezpośrednio do oryginalnego fragmentu transkrypcji w edytorze Windows**. Wystarczy wybrać cytat i przycisk przejścia do źródła. Wyświetlany jest prawidłowy ID fragmentu i tekst, który możesz ręcznie poprawić.

Przejście jest zabezpieczone przed przypadkową utratą niezapisanych poprawek. W przypadku istniejącego szkicu aplikacja najpierw pyta o jego zachowanie lub świadome odrzucenie; nie kasuje tekstu bez ostrzeżenia. Program nie odtwarza jeszcze automatycznie dźwięku od danego timecode — łącznik wskazuje tekstowe źródło z oznaczeniem czasu.

Szczegóły: [VN03_FUNCTIONAL_TEMPLATES.md](docs/VN03_FUNCTIONAL_TEMPLATES.md).

## Inwentarz zależności offline do prywatnego pakietu Windows (VN-06)

Polecenie `python -m videonotes bundle-sbom KATALOG_PAKIETU --output raport.spdx.json` sprawdza istniejącą prywatną paczkę i zapisuje oddzielnie SPDX 2.3 z SHA-256 poszczególnych binariów/modelu. Wszystkie licencje są jawnie niezweryfikowane (`NOASSERTION`); brak podstaw do publikacji stabilnej wersji. Opis: [VN06_SBOM.md](docs/VN06_SBOM.md).

## Test lokalnego środowiska (VN-00/VN-06)

`python -m videonotes doctor --model C:\\Modele\\ggml-base.bin --workspace C:\\Notatki --source C:\\Nagrania\\test.mkv` pokazuje lokalnie diagnostykę binariów, ścieżek audio, wolnego dysku i SHA-256 modelu bez sieci czy logowania prywatnych ścieżek. Nie potwierdza realnej jakości ASR, fizycznego Windows ani licencji. [Instrukcja](docs/VN_OFFLINE_DIAGNOSTICS.md).

## Opcjonalne OCR klatek/slajdów OBS (VN-03B)

`python -m videonotes slide-ocr KATALOG_PROJEKTU --output slajdy.json` uruchamia lokalny Tesseract i FFmpeg na niewielkiej liczbie klatek wideo, a `slide-verify ... --file slajdy.json` sprawdza poprawność struktury raportu i SHA-256 źródła. Wymaga wcześniejszego zainstalowania Tesseract z odpowiednimi pakietami językowymi, nie pobiera modeli i **nie weryfikuje faktów** ani dokładności OCR. Szczegóły: [VN03B_SLIDE_OCR.md](docs/VN03B_SLIDE_OCR.md).

## Szkic semantyczny offline z opcjonalnym lokalnym llama.cpp (VN-02/03)

Polecenie `python -m videonotes semantic-draft KATALOG_PROJEKTU --model C:\\Modele\\model.gguf --llama-cli llama-cli --output szkic.json` przygotowuje odrębne szkice oparte na wybranych segmentach transkrypcji. `semantic-verify --file szkic.json` sprawdza powiązania z cytatami, a `semantic-export --file szkic.json --output szkic.md` tworzy czytelny plik. Nie wymaga sieci, ale wymaga zainstalowanego lokalnie binarium i modelu GGUF. **To nie jest automatyczna weryfikacja merytoryczna**, a wszystkie twierdzenia modelu muszą być sprawdzone przez człowieka. [Ograniczenia i instrukcja](docs/VN_SEMANTIC_DRAFT.md).

## Transkrypcja całego zakończonego nagrania z mikrofonu (VN-04)

Nowe polecenie `record-transcribe` obsługuje sesje WAV po pauzach, wymaga zgód i spójnego SHA-256, łączy wszystkie części bez nadpisania i kieruje je do identycznego lokalnego przepływu ASR/eksportu co pliki OBS. Po przerwaniu użyj istniejącego `resume`. Instrukcja: [VN04_RECORD_TO_ASR.md](docs/VN04_RECORD_TO_ASR.md). Nie zastępuje fizycznego testu mikrofonu Windows.

## Okno lokalnej analizy w interfejsie Windows

W aplikacji desktopowej dodano przycisk **„OCR slajdów i lokalne szkice AI (wymagają kontroli)”**. Otwiera osobne narzędzia do tworzenia szkicu semantycznego, OCR slajdów, eksportu Markdown i weryfikacji źródeł. Dłuższe operacje uruchamiane są w osobnym wątku bez blokowania okna; nie ma automatycznej synchronizacji ani wysyłki danych. Wyniki pozostają oznaczone jako niezweryfikowane. Testy prawdziwych widżetów Tk w CI nie zastępują odbioru na fizycznym Windows.

Aplikacja Tk oferuje również przycisk „Zakończone nagranie mikrofonowe → transkrypcja całej sesji”: jawny wybór zakończonej sesji, pustego folderu, ewentualnego WAV i modelu, potem wspólny proces ASR z postępem i bezpiecznym przerwaniem. Źródłowe nagrania są zachowywane.

## Ręczny odsłuch cytatu z oryginalnego źródła (VN-02)

`python -m videonotes play-source KATALOG_PROJEKTU --segment ID --seconds 15` (lub przycisk „Odtwórz zaznaczony fragment z nagrania” w GUI) weryfikuje SHA-256 oryginalnego nagrania, wybiera faktyczną ścieżkę audio projektu, wycina krótkie WAV i uruchamia lokalny FFplay. Wymaga osobno zainstalowanego FFplay; nie ingeruje w edycje ani nie przesyła materiałów. [Instrukcja i ograniczenia](docs/VN02_SOURCE_AUDIO_PLAYBACK.md).

## Łączenie odczytanych slajdów i transkrypcji według czasu (VN-03B)

`slide-align --ocr raport-ocr.json --output NOWY-indeks.json` przypisuje rozpoznane fragmenty obrazu do **najbliższych w czasie** segmentów mowy, bez twierdzenia, że temat jest zgodny. `slide-align-verify` odtwarza wyniki z aktualnego źródła, a `slide-align-md` eksportuje dosłowne OCR i cytaty. W GUI działa przycisk „Powiąż OCR z wypowiedziami według czasu”. [Instrukcja](docs/VN03_SLIDE_TRANSCRIPT_TIME_ALIGNMENT.md). Wszystkie powiązania wymagają sprawdzenia przez człowieka.

Lokalne szkice semantyczne zawierają dodatkowo konserwatywną kontrolę liczb, adresów i skrótów technicznych względem cytowanych fragmentów. Niepoparte identyfikatory powodują odmowę zapisu lub weryfikacji. To ograniczenie halucynacji, nie potwierdzenie poprawności merytorycznej. [Szczegóły](docs/VN_SEMANTIC_DRAFT.md).
