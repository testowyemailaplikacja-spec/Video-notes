# VN-06 — testowy program uruchamialny Windows (DEV)

**06.11.2026:** wewnętrzna kompilacja prototypu PyInstaller, nie jest to kompletny instalator offline, wydanie stabilne ani dowód działania ASR.

Workflow `.github/workflows/vn06-windows-dev-binary.yml` kompiluje kod na runnerze Windows z Pythonem 3.13 i przypiętym PyInstaller 6.16.0 do `VideoNotes-DEV.exe`. Przeprowadza test wykonywalnego programu (`--version`, `--help` oraz obsługa brakującego pliku), sprawdza SHA-256 i publikuje krótkotrwały artefakt testowy CI GitHub Actions oznaczony `VideoNotes-Windows-DEV-NOT-OFFLINE`.

**Artefakt nie zawiera:** FFmpeg, FFprobe, whisper-cli, modeli ASR, prywatnych nagrań ani danych konta. Nie można traktować go jako samodzielnego programu do transkrypcji bez przygotowania tych lokalnych zależności.

## Lokalny build developerski

```powershell
python -m pip install pyinstaller==6.16.0
python -m PyInstaller --clean --noconfirm --onefile --console --name VideoNotes-DEV --paths . scripts/videonotes_entry.py
.\dist\VideoNotes-DEV.exe --version
```

## Bramka odbioru Windows

Do ukończenia VN-06 nadal potrzebne są: instalacja bez Pythona i internetu na czystym Windows, redystrybucja dozwolonego prawnie modelu i FFmpeg, kompletne uruchomienie ASR/GUI, testy dużych plików OBS, testy prywatności, licencje, SBOM, odzyskiwanie po błędach i ewentualnie podpis cyfrowy. **Żaden publiczny release ani zmiana Netlify nie są uruchamiane w tym workflow.**

Testy samego wykonywalnego narzędzia nie zastępują odbioru urządzenia użytkownika; do czasu prawdziwych testów sprzętowych VN-06 pozostaje W TRAKCIE.
