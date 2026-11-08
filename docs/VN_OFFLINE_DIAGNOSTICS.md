# VN-00/VN-06 — diagnostyka lokalnego środowiska bez wysyłania danych

Nowe polecenie `doctor` sprawdza podstawową dostępność lokalnych narzędzi, bez połączeń z siecią, transkrybowania wypowiedzi i ingerowania w projekty.

```powershell
python -m videonotes doctor --ffmpeg C:\\Narzędzia\\ffmpeg.exe --ffprobe C:\\Narzędzia\\ffprobe.exe --whisper-cli C:\\Narzędzia\\whisper-cli.exe --model C:\\Modele\\ggml-base.bin --workspace C:\\Notatki --source C:\\Nagrania\\test.mkv
```

Dane wyjściowe JSON pokazują rozpoznaną odpowiedź `-version` FFmpeg/FFprobe, obecność binarnego Whisper (bez uruchamiania modelu), SHA-256 i rozmiar wskazanego modelu, opcjonalną liczbę ścieżek audio i ich kodeki oraz wolne miejsce na dysku. Ścieżki lokalne, nazwy urządzeń, tytuły strumieni i słowa z transkrypcji nie są wypisywane. Dostępność binarium nie dowodzi poprawnej współpracy z konkretnym modelem ani jakości rozpoznawania.

Flagi `asr_inference_tested`, `physical_microphone_tested`, `physical_windows_offline_tested`, `license_verified`, `release_ready` pozostają zawsze `false` — tych faktów nie można zweryfikować zwykłą diagnostyką. Prawdziwy test ASR jest dostępny osobno w `benchmark-real`. Fizyczny odbiór Windows i licencje nadal wymagają kontroli.

Testy Python wykorzystują syntetyczne wyniki procesów, lokalny plik modelu i brak źródła lub błędny FFprobe. Nie potwierdzają próby fizycznego urządzenia.
