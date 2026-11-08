# VN-00 — realny lokalny benchmark dwóch silników ASR

**Stan 06.11.2026:** wykonano kod do uruchamiania `whisper.cpp` i `faster-whisper` na identycznym audio. **Nie wykonano jeszcze benchmarku prawdziwych modeli i nagrań**. Pełny odbiór VN-00 pozostaje W TRAKCIE.

## Co przygotować

Na Windows/innym komputerze trzeba zainstalować lokalnie FFmpeg i FFprobe, dostarczyć lokalny `whisper-cli(.exe)` oraz kompatybilny model `ggml-*.bin`. Dla `faster-whisper` przygotuj lokalny folder modelu CTranslate2, zawierający co najmniej `config.json`, `model.bin` i `vocabulary.txt`, oraz opcjonalny pakiet Pythona `faster-whisper` z zależnościami. **Nie wpisuj nazwy modelu z sieci zamiast lokalnej ścieżki**, program nie pobiera modeli automatycznie.

Przygotuj legalny własny plik OBS MP4/MKV/WebM/WAV i ręcznie sprawdzony plik UTF-8 `wzorzec.txt` obejmujący dokładnie tę samą część nagrania.

## Komenda

```powershell
python -m videonotes benchmark-real "wyklad.mkv" --reference "wzorzec.txt" --cpp-executable "C:\Whisper\whisper-cli.exe" --cpp-model "C:\Whisper\ggml-base.bin" --faster-model-dir "C:\Modele\ct2-base" --language pl --threads 4 --stream 1 --start-seconds 0 --duration-seconds 300 --output "benchmark.json"
```

Najpierw użyj `python -m videonotes inspect wyklad.mkv`, aby sprawdzić globalny indeks właściwego strumienia audio. Dla wielu ścieżek `--stream` jest obowiązkowy.

## Metodologia

Program wycina jeden, identyczny fragment WAV mono/PCM 16kHz lokalnym FFmpeg. W osobnych procesach uruchamia `whisper.cpp` (CPU, beam=5, wybór języka) i `faster-whisper` (CPU int8, beam=5). W ten sposób nie porównuje wyników pochodzących z różnych nagrań. Mierzy wall-clock czasu od startu procesu (z ładowaniem modelu), oblicza WER/CER względem ręcznego wzorca i rejestruje rozmiary/hash modeli. Gdy operator zainstaluje `psutil` w środowisku benchmarkowym, program może monitorować szczytowe zużycie RAM procesu i dzieci. Bez tego pole `peak_rss_bytes` jest `null`, a `ram_measured` ma wartość `false` — brak wyniku nie jest zastępowany zgadywaniem.

Ustawienia modeli **nie są w pełni równoważne** (np. CTranslate2 int8 wobec konkretnego modelu GGML). Raport pozwala mierzyć system w danych warunkach, ale decyzja technologiczna wymaga jeszcze zgodności wersji i wybranego modelu, oszacowania WER na PL/EN, kosztu dystrybucji, licencji i rzeczywistego sprzętu Windows.

## Prywatność

Teksty wyniku i tymczasowe WAV są w katalogu tymczasowym systemu i usuwane po wykonaniu. Wyjście/stderr procesów są kierowane poza log publiczny. JSON raportu zawiera liczby, hashe, czas, RAM (jeśli mierzono), bez nazw ani zawartości nagrań. Nie commituj referencyjnych wykładów i plików *.txt z prywatnymi rozmowami do publicznego repo. Benchmark uruchamia lokalny kod, ale nazwa/wersja binariów nie jest niezależnie atestowana: `engine_binary_identity_independently_verified=false`.

**Blokada odbioru VN-00:** brak próbek PL/EN i kompatybilnych realnych modeli w autoryzowanym środowisku testowym, brak pomiaru na rzeczywistym Windows i zweryfikowanych licencji redystrybucji. Testy CI testują adaptery z atrapami, a nie rzeczywiste modele.

## Osobny test z rzeczywistym whisper.cpp na syntetycznej mowie PL/EN (08.11.2026)

Workflow `.github/workflows/vn-real-asr-smoke.yml` służy do sprawdzenia prawdziwego wywołania silnika ASR, ale wyłącznie na **dwóch oryginalnych, syntetycznych nagraniach TTS**, wygenerowanych lokalnie przez eSpeak NG w CI. Nie używa wykładów użytkowników ani prywatnych plików. W jednorazowym środowisku GitHub Actions pobiera i buduje konkretny commit `ggml-org/whisper.cpp` (`6a8addd258eadd6563f8c582e8acc535e6325364`), pobiera wielojęzyczny model `ggerganov/whisper.cpp/ggml-tiny.bin` z SHA-256 `be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21`, a następnie sprawdza ścieżkę `create_project → FFmpeg PCM → prawdziwy whisper-cli CPU → JSON → checkpoint → eksport TXT/SRT/VTT/JSON → notatka → DOCX` osobno dla PL i EN.

Model oraz binaria są pobierane **tylko przez workflow testowy** i nie trafiają do repozytorium ani do publicznych artefaktów. Produkt nadal nie pobiera modeli automatycznie. Wynik CI zapisuje wyłącznie liczbę fragmentów i czas, nie wypowiadaną/rozpoznaną treść. Test nie stosuje sztucznego progu WER/CER, bo nie jest to ręcznie zweryfikowane nagranie naturalnej mowy.

Źródła komponentów: [whisper.cpp](https://github.com/ggml-org/whisper.cpp), [model multilingual tiny](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-tiny.bin) i [MIT dla Whisper oraz wag](https://github.com/openai/whisper/blob/main/README.md#license). Licencję i warunki całej przyszłej dystrybucji należy osobno skontrolować przed wydaniem.

**Nie zamyka VN-00 ani VN-01:** prawdziwe PL/EN wykłady, ocena WER/CER przez człowieka, porównanie faster-whisper, pomiar na docelowym komputerze Windows, 2h, stabilny instalator i licencje redystrybucji nadal są wymagane. Wynik workflow trzeba zweryfikować przed zmianą statusu.

## Porównanie dwóch prawdziwych lokalnych silników na syntetycznym TTS (08.11.2026)

Workflow `vn-real-asr-smoke.yml` po osobnym teście prawdziwego `whisper.cpp` może dodatkowo uruchomić **rzeczywisty lokalny benchmark dwusilnikowy** dla tych samych próbek eSpeak NG (PL i EN). Dla Whisper.cpp wykorzystuje commit `6a8addd258eadd6563f8c582e8acc535e6325364` i znany SHA-256 wielojęzycznego modelu GGML tiny. Dla `faster-whisper` instaluje opcjonalny pakiet tylko na jednorazowej maszynie CI i pobiera lokalną konwersję CTranslate2 `Systran/faster-whisper-tiny` z przypiętej rewizji `d90ca5fe260221311c53c58e660288d3deb8d356`; model.bin musi mieć SHA-256 `dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1`.

Ten sam fragment WAV mono/PCM 16 kHz trafia osobno do dwóch prawdziwych procesów CPU przez funkcję `benchmark-real`, z ręcznie zadanym wzorcem odpowiadającym oryginalnemu tekstowi syntezatora. Wynik zawiera **WER, CER, czas i obserwowane maksimum RSS** przez lokalny psutil. Wyniki benchmarków pozostają tylko w katalogu tymczasowym runnera i nie zawierają pełnego tekstu nagrań ani transkrypcji. Wzorzec TTS nie jest równoważny nagraniu naturalnej mowy z sali.

Nie porównuje to dwóch technologii na identycznym formacie/kwantyzacji wag (GGML vs CTranslate2 int8), a ani wynik CI, ani pomiar na współdzielonej maszynie wirtualnej nie przesądzają o wyborze silnika, jakości naturalnych PL/EN wykładów ani wydajności docelowego Windows. Modele nie są dystrybuowane w produkcie, a warunki licencyjne wymagają osobnego odbioru wydawniczego.

Źródła: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [oficjalny model tiny CTranslate2](https://huggingface.co/Systran/faster-whisper-tiny) (MIT), [whisper.cpp](https://github.com/ggml-org/whisper.cpp).

### Wymagany plik `vocabulary.txt` (diagnoza CI 08.11.2026)

Pierwsze rzeczywiste wykonanie porównania dwóch silników wykazało, że pakiet modelu CTranslate2 z samymi `model.bin`, `config.json` i `tokenizer.json` jest niekompletny: `faster-whisper` zwraca błąd `Cannot load the vocabulary from the model directory`. Poprawiono testowy zestaw na pinowane pliki obejmujące `vocabulary.txt` oraz dodano wcześniejszą walidację tego wymogu w aplikacji, aby nie rozpoczynać benchmarku z błędnym modelem. Dopiero pełny pozytywny przebieg obu silników uzasadnia wpisanie WER/CER i RSS jako przetestowanych.

### Zgodność PyAV przy faster-whisper 1.2.1

Drugi test rzeczywistej inferencji ujawnił niezależny błąd zależności: faster-whisper 1.2.1 wywołuje `av.open(metadata_errors=...)`, lecz PyAV 19 usunął ten parametr. Objaw: `TypeError: open() got an unexpected keyword argument 'metadata_errors'`. W CI przypięto zgodną wersję **PyAV 18.1.0** obok `faster-whisper==1.2.1`; sam produkt wciąż nie instaluje żadnych pakietów automatycznie. Jest to tymczasowa macierz zgodności, którą należy zaktualizować po wydaniu poprawionej wersji faster-whisper i sprawdzeniu jej ponownie.

Dowód aktualnego upstream: https://github.com/SYSTRAN/faster-whisper/issues/1589 . Wydanie stabilne musi zweryfikować licencje, lockfile/SBOM, zgodność obu pakietów i rzeczywisty Windows; udane CI Linux na TTS nie wystarcza do zamknięcia VN-00.


## Dodatkowa bramka automatyczna: dwie ścieżki OBS + prawdziwy ASR (08.11.2026)

Test `scripts/real_obs_multitrack_asr_smoke.py` tworzy w CI **oryginalne, syntetyczne** pliki MP4 (PL) i MKV (EN) z obrazem, cichą pierwszą ścieżką audio i mową TTS na **drugiej** ścieżce. Następnie wykonuje prawdziwy `FFprobe → FFmpeg → whisper.cpp CPU → zapis checkpointu → ręczna poprawka → cztery eksporty`, sprawdzając, że przy dwóch ścieżkach wymagany jest jawny wybór i że poprawki nie nadpisują surowego ASR ani pliku wejściowego.

Test jest wykonywany w tym samym `vn-real-asr-smoke.yml` z tym samym wcześniej weryfikowanym modelem lokalnym. Status: **oczekuje na wynik workflow nowego PR**; sam zapis testu nie dowodzi PASS. Nawet pozytywny wynik nie jest odbiorem rzeczywistych nagrań OBS, WER/CER wykładu, długiej inferencji ani instalacji offline na fizycznym Windows. Nie wolno na jego podstawie zamknąć VN-00/VN-01.
