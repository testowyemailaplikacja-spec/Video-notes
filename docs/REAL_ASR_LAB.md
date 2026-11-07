# VN-00 — realny lokalny benchmark dwóch silników ASR

**Stan 06.11.2026:** wykonano kod do uruchamiania `whisper.cpp` i `faster-whisper` na identycznym audio. **Nie wykonano jeszcze benchmarku prawdziwych modeli i nagrań**. Pełny odbiór VN-00 pozostaje W TRAKCIE.

## Co przygotować

Na Windows/innym komputerze trzeba zainstalować lokalnie FFmpeg i FFprobe, dostarczyć lokalny `whisper-cli(.exe)` oraz kompatybilny model `ggml-*.bin`. Dla `faster-whisper` przygotuj lokalny folder modelu CTranslate2, zawierający co najmniej `config.json` i `model.bin`, oraz opcjonalny pakiet Pythona `faster-whisper` z zależnościami. **Nie wpisuj nazwy modelu z sieci zamiast lokalnej ścieżki**, program nie pobiera modeli automatycznie.

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
