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

Test jest wykonywany w tym samym `vn-real-asr-smoke.yml` z tym samym wcześniej weryfikowanym modelem lokalnym. Status: **PASS**, zweryfikowano pełny workflow [PR #59 / Actions 42465075107](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42465075107) (prawdziwe Whisper CPU na syntetycznych MP4/MKV) i pięć pozostałych kontroli Linux/Windows/Chromium/Firefox/Edge [Actions 42465074909](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42465074909). Nawet pozytywny wynik nie jest odbiorem rzeczywistych nagrań OBS, WER/CER wykładu, długiej inferencji ani instalacji offline na fizycznym Windows. Nie wolno na jego podstawie zamknąć VN-00/VN-01.


## Potwierdzone porównanie dwóch rzeczywistych silników — PR #55

[GitHub Actions 42428095863](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42428095863): wszystkie kroki workflow PASS, w tym prawdziwe CPU `whisper.cpp` i `faster-whisper` na jednakowych, oryginalnych próbkach polskiego i angielskiego TTS. Raporty zawierają WER/CER względem skryptu syntetycznego nagrania oraz czas i RSS obu procesów. Wyniki pozostają niewystarczające do decyzji o jakości na naturalnym wykładzie, do licencji redystrybucyjnej i odbioru offline Windows. Przeszło też 7/7 pozostałych checków PR; scalenie z `develop` [PR #55](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/55).

## Prawdziwy checkpoint i wznowienie po zatrzymaniu ASR — PR #61 (08.11.2026)

[PR #61](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/61) został scalony do `develop` po **6/6 kontrolach PASS**, w tym [rzeczywisty whisper.cpp CPU, Actions 42465450853](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42465450853) i [5 testów Linux/Windows/browser, Actions 42465450897](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42465450897). `scripts/real_resume_asr_smoke.py` tworzy wyłącznie oryginalny syntetyczny 34-sekundowy głos TTS i MKV z dwiema ścieżkami, używa rzeczywistego FFmpeg i modelu Whisper. Przerywa po zapisaniu pierwszego fragmentu 30 s, wznawia transkrypcję drugiego, sprawdza identyczny zapis pierwszej części, brak duplikatów, niezmienność ukończonego projektu po kolejnym resume oraz cztery eksporty. Nie przetwarza prywatnych nagrań. **Nie jest to 2-godzinny test realnego modelu na wykładzie, fizyczna instalacja Windows, pomiar stabilności sprzętu ani odbiór VN-01.**

## Rozszerzony odbiór źródłowych notatek po prawdziwym ASR (08.11.2026)

Test `scripts/real_asr_smoke.py` po rozpoznaniu polskiego i angielskiego syntetycznego TTS rzeczywistym `whisper.cpp` dodatkowo sprawdza:

1. Ręczna korekta rozpoznanej wypowiedzi nie zmienia surowego `transcript.json`.
2. Dotychczasowa notatka podstawowa staje się jawnie nieaktualna i nie może być po cichu eksportowana jako aktualna.
3. Regeneracja cytatów zachowuje poprzednią wersję w historii, a nowa notatka wiąże poprawiony tekst z tym samym ID źródłowym.
4. Konspekt zaawansowany `MD/JSON/DOCX` powstaje z **rzeczywistego lokalnego wyniku ASR**, zawiera cytaty o prawidłowych ID i czasach, poprawioną treść w Word DOCX oraz nie dodaje obcych wypowiedzi.

To test **ekstrakcyjnego konspektu źródłowego**, nie semantycznego rozumienia wykładu. Zestaw testowy generowany jest wyłącznie w jednorazowym CI, bez prywatnych nagrań i bez wysyłania transkrypcji. Status wykonania należy potwierdzić na GitHub Actions powiązanym z PR przed oznaczeniem `PASS`. Formalny odbiór VN-02/VN-03 nadal wymaga jakościowej oceny prawdziwych materiałów i urządzeń.


## Aktualizacja pomiarów i prywatności — 12.11.2026 (VN-00)

Przed uruchomieniem rzeczywistego rozpoznawania program lokalnie weryfikuje plik referencyjny: UTF-8, limit 300 KB, niepustą treść i dopuszczalną liczbę słów. Błędny wzorzec nie uruchamia FFmpeg ani modeli. Raport przechowuje teraz `input_clip.pcm_sha256`: hash *identycznego tymczasowego WAV*, z którego korzystały oba silniki. Zwalidowane metryki to wyłącznie `wall_seconds`, `peak_rss_bytes`, `ram_measured`, `cpu_seconds_observed`, `cpu_measured`. Wszystkie inne pola otrzymane od uruchamiacza są pomijane, więc ścieżki lokalne i tekst nie dostaną się przypadkiem do raportu. `NaN`, `Infinity`, ujemny RAM/czas i sprzeczne flagi pomiarowe są odrzucane, a raport nie jest wtedy tworzony.

Licznik `cpu_seconds_observed` bazuje na próbkach procesu i jego żyjących dzieci, wymaga lokalnie zainstalowanego `psutil` i **stanowi dolne oszacowanie**, nie pełny bilans zużycia CPU. Jeśli pomiar jest niedostępny, otrzymuje `null`, a `cpu_measured=false`. Zarówno te testy CI, jak i hash PCM nie dowodzą jakości rzeczywistej transkrypcji: VN-00-01/02 nadal wymagają legalnych naturalnych nagrań i referencji użytkownika, a wybór silnika musi nastąpić dopiero po ocenie jakości i licencji.

### Liniowa weryfikacja referencji przed inferencją — 12.11.2026

Przed wykonaniem czasochłonnego `whisper.cpp` i `faster-whisper` wywoływana jest oddzielna, liniowa kontrola lokalnego wzorca. Czyta tylko ograniczony plik TXT, sprawdza UTF-8, niepusty tekst oraz limit 6000 słów. Nie wykonuje niepotrzebnego porównania Levenshteina wzorca z nim samym (co ma istotne znaczenie dla dużych referencji). Zwraca wyłącznie powodzenie lub zredagowany błąd, bez prywatnych słów i ścieżek. Walidacja nie potwierdza jednak, że tekst faktycznie pochodzi z wybranego fragmentu audio; wymaga to fizycznego odbioru użytkownika.

## Integralność benchmarku (12.11.2026)

Polecenie `benchmark-real` wylicza SHA-256 nagrania, ręcznej referencji, pliku modelu whisper.cpp oraz lokalnych składników CTranslate2 (`model.bin`, `config.json`, `vocabulary.txt`) **przed** uruchomieniem obu silników. Po analizie porównuje je ponownie i odrzuca wynik, jeśli którykolwiek plik zmienił się podczas pomiaru. Dodatkowo po każdym silniku kontroluje SHA-256 identycznego wejściowego WAV/PCM, aby pierwszy proces nie mógł po cichu zmienić próbki dla drugiego. Nie publikuje JSON z niespójnymi danymi, nie zapisuje prywatnych transkrypcji.

To zabezpiecza powtarzalność pomiaru, ale **nie dowodzi** autentyczności licencji, zgodności wag/modeli ani jakości na naturalnych nagraniach. Ponowne hashowanie dużego nagrania i modeli dodaje operacje dyskowe poza mierzonym czasem procesów; należy uwzględnić ten koszt przy długich próbach. Testy regresyjne celowo zmieniają osobno źródło, referencję, oba modele i PCM i sprawdzają brak publikacji.

## Wynik benchmarku bez nadpisania przy równoległych uruchomieniach (12.11.2026)

Po zakończeniu dwóch pomiarów aplikacja publikuje JSON za pomocą kompletnego pliku tymczasowego zapisanego na tym samym dysku i atomowego utworzenia nowej nazwy przez `os.link`. Drugi benchmark nie może nadpisać wyniku pierwszego, nawet jeśli oba procesy na początku sprawdziły, że ścieżka nie istnieje. Odrzucane są też istniejące i wiszące dowiązania symboliczne. Przy kolizji raport z innego uruchomienia jest zachowany, a plik tymczasowy usuwany. Nie dotyczy to porównywalności rzeczywistych wyników: naturalne nagrania PL/EN, ręczna referencja, oba legalne modele i fizyczny test offline nadal są wymagane przed odbiorem VN-00.

## Ochrona lokalnych pomiarów tekstowych WER/CER (12.11.2026)

Polecenie `benchmark` (porównujące gotowe pliki TXT, niezależnie od uruchomienia rzeczywistego silnika) nie nadpisuje już istniejących raportów. Raport JSON powstaje w lokalnym pliku tymczasowym, jest synchronizowany na dysk, a następnie publikowany tylko pod **nową** nazwą bez zastępowania pliku utworzonego przez równoległy pomiar. Próba wskazania istniejącego pliku wejściowego jako wyjścia nie usuwa ręcznej transkrypcji referencyjnej. Po porównaniu narzędzie ponownie sprawdza SHA-256 wszystkich plików TXT, aby nie opublikować WER/CER dla materiałów zmienionych w trakcie obliczeń. Testy obejmują konkurencyjny raport i zmianę wzorca po wczytaniu. Funkcja wciąż nie weryfikuje pochodzenia wyników ASR ani licencji modeli i nie zastępuje benchmarku prawdziwej mowy.

## Limit odczytu plików TXT także podczas zmiany pliku (12.11.2026)

Porównywanie WER/CER odczytuje teraz **maksymalnie 300 001 bajtów** i odrzuca zawartość przekraczającą limit 300 000 bajtów, nawet jeśli plik był mały podczas początkowego `stat()`, ale urósł tuż przed odczytem. Unikamy w ten sposób niekontrolowanego wczytania wielogigabajtowego pliku do RAM. Wzorce i kandydaci będący dowiązaniami symbolicznymi także są odrzucani. Dwa testy sprawdzają takie dowiązania i deterministyczny wzrost pliku między kontrolą rozmiaru a odczytem. Metryki pozostają lokalne; naturalna referencja PL/EN i ręczny odsłuch nadal są bramkami VN-00.

## Ochrona przed osieroconymi procesami benchmarku (12.11.2026)

Każdy lokalny silnik działa w osobnej grupie procesów. Przekroczenie limitu czasu, niezerowy kod wyjścia lub przerwanie benchmarku powoduje zatrzymanie także jego procesów potomnych (grupa POSIX albo `taskkill /T /F` na Windows), bez wypisywania mowy lub lokalnych ścieżek. Testy automatyczne Linux sprawdzają proces potomny, który inaczej pozostałby aktywny. Test kodu Windows nie zastępuje odbioru na fizycznym komputerze ani porównania jakości ASR na naturalnej mowie.
