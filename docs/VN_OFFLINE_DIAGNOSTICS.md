# VN-00/VN-06 — diagnostyka lokalnego środowiska bez wysyłania danych

Nowe polecenie `doctor` sprawdza podstawową dostępność lokalnych narzędzi, bez połączeń z siecią, transkrybowania wypowiedzi i ingerowania w projekty.

```powershell
python -m videonotes doctor --ffmpeg C:\\Narzędzia\\ffmpeg.exe --ffprobe C:\\Narzędzia\\ffprobe.exe --whisper-cli C:\\Narzędzia\\whisper-cli.exe --model C:\\Modele\\ggml-base.bin --workspace C:\\Notatki --source C:\\Nagrania\\test.mkv
```

Dane wyjściowe JSON pokazują rozpoznaną odpowiedź `-version` FFmpeg/FFprobe, obecność binarnego Whisper (bez uruchamiania modelu), SHA-256 i rozmiar wskazanego modelu, opcjonalną liczbę ścieżek audio i ich kodeki oraz wolne miejsce na dysku. Ścieżki lokalne, nazwy urządzeń, tytuły strumieni i słowa z transkrypcji nie są wypisywane. Dostępność binarium nie dowodzi poprawnej współpracy z konkretnym modelem ani jakości rozpoznawania.

Flagi `asr_inference_tested`, `physical_microphone_tested`, `physical_windows_offline_tested`, `license_verified`, `release_ready` pozostają zawsze `false` — tych faktów nie można zweryfikować zwykłą diagnostyką. Prawdziwy test ASR jest dostępny osobno w `benchmark-real`. Fizyczny odbiór Windows i licencje nadal wymagają kontroli.

Testy Python wykorzystują syntetyczne wyniki procesów, lokalny plik modelu i brak źródła lub błędny FFprobe. Nie potwierdzają próby fizycznego urządzenia.

## Dodatkowe opcjonalne narzędzia (09.11.2026)

```powershell
python -m videonotes doctor --ffmpeg ffmpeg --ffprobe ffprobe --ffplay ffplay --tesseract tesseract --ocr-language pol+eng --llama-cli llama-cli --gguf-model C:\Modele\lokalny.gguf
```

Komenda sprawdza lokalnie odpowiedź `-version` FFplay i Tesseract, lokalnie zainstalowane języki OCR, obecność właścicielskiego `llama-cli` (bez uruchamiania modelu), nagłówek `GGUF` i SHA-256 pliku modelu. Pokazuje wyłącznie krótkie informacje diagnostyczne i listę **brakujących kodów języka**; nie wypisuje lokalnych ścieżek, tekstów OCR ani wyników działania modeli.

Pole `capability_candidates_not_acceptance` mówi jedynie, czy podstawowe lokalne składniki danej ścieżki *wydają się być zainstalowane*. Nawet gdy ma wartość `true`, nie stanowi to potwierdzenia legalności, kompatybilności ABI, realnego działania modelu GGUF, poprawnej transkrypcji lub OCR na wykładzie, jakości głośników, fizycznego urządzenia Windows, ani ukończenia VN-06. To wstępny filtr przed prawdziwym odbiorem.
