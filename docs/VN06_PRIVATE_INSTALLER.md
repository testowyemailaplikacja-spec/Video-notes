# VN-06 — prywatny instalator offline Windows (weryfikacja przedwydaniowa)

Data: 2026-11-08. Repozytorium robocze: `testowyemailaplikacja-spec/Video-notes` na `develop`.

## Co rzeczywiście zostało zaimplementowane

`python -m videonotes installer-dev` tworzy **pełny pakiet instalacyjny EXE Inno Setup z lokalnej, wcześniej zweryfikowanej paczki `bundle-dev`**. Daje to instalację dla bieżącego użytkownika Windows, pliki wykonawcze, FFmpeg/FFprobe, whisper.cpp, model GGML, manifest SHA-256, launcher i deinstalator. Skompilowany prywatny instalator może być kopiowany na komputer bez sieci — nie pobiera modelu ani binariów podczas instalacji.

Wymaga **własnych, lokalnych komponentów** i lokalnego kompilatora `ISCC.exe` Inno Setup 6 na komputerze budującym. Program nie pobiera binariów ani modeli z internetu. Użytkownik odpowiada za legalne pozyskanie i uprawnienie do prywatnego użycia. **Nie oznacza to pozwolenia na publiczną redystrybucję modelu lub bibliotek.**

## Budowa na Windows

Najpierw pobierz z zatwierdzonego workflow prywatny plik `VideoNotes-DEV.exe` i przygotuj własne pliki `ffmpeg.exe`, `ffprobe.exe`, `whisper-cli.exe` i zgodny model `ggml-*.bin`. Nigdy nie commituj modelu ani rzeczywistych nagrań.

```powershell
python -m videonotes bundle-dev --app C:\\Test\\VideoNotes-DEV.exe --ffmpeg C:\\Tools\\ffmpeg.exe --ffprobe C:\\Tools\\ffprobe.exe --whisper C:\\Tools\\whisper-cli.exe --model C:\\Models\\ggml-base.bin --output C:\\Test\\VideoNotes-PRIVATE --internal-only

python -m videonotes bundle-verify C:\\Test\\VideoNotes-PRIVATE

python -m videonotes installer-dev --bundle C:\\Test\\VideoNotes-PRIVATE --iscc "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe" --output C:\\Test\\VideoNotes-PRIVATE-Setup.exe --internal-only
```

Otrzymasz lokalny EXE i sumę SHA-256 wypisaną przez CLI. Kompilator generuje instalator w katalogu tymczasowym, a dopiero potem wynik jest opublikowany bez nadpisania istniejącego pliku (hard link). Przed budową oraz po kompilacji sprawdzane są wszystkie pliki źródłowe wobec manifestu. Odmowa następuje przy braku modelu, podmianie pliku, niepoprawnym manifestu, niedostępnym ISCC, błędnej kompilacji lub istniejącym celu.

Podczas instalacji program **nie uruchamia się automatycznie**. Instalacja działa na poziomie bieżącego użytkownika (`PrivilegesRequired=lowest`), a deinstalator usuwa pliki aplikacji. Oryginalne nagrania i projekty użytkownika nie są pakowane do instalatora.

## Automatyczna kontrola Windows

Workflow `vn-internal-installer.yml` przygotowuje jednorazową paczkę z **syntetycznymi, celowo nieuruchamialnymi** plikami modelu i programów, pozyskuje Inno Setup na jednorazowym runnerze, kompiluje prawdziwy instalator EXE, instaluje go w trybie cichym, porównuje SHA-256 z manifestem, a następnie odinstalowuje. **Nie publikuje wygenerowanego EXE**. Status `PASS` podajemy dopiero po zweryfikowaniu całej akcji.

Test syntetyczny potwierdza, że Inno może złożyć i skopiować pliki, a nie że nagrywanie, mikrofon, model ASR i prywatna sesja rzeczywiście działają offline na sprzęcie Windows.

## Kryteria, których nie wolno oznaczyć jako wykonane

- Nie wykonano testu Windows 10/11 bez internetu z prawdziwym modelem i legalnymi binariami, pełnym przepływem OBS → Whisper → notatki → DOCX/PDF.
- Brak potwierdzenia licencji redystrybucyjnych konkretnej dystrybucji FFmpeg/whisper/modelu, SBOM i skanowania antywirusowego artefaktów.
- Instalator jest **niepodpisany, nieatestowany**, ma nazwę INTERNAL TEST i nie stanowi wydania 1.0.
- Nie wykonano odbioru na fizycznych urządzeniach, deinstalacji z rzeczywistymi danymi ani testów dostępności użytkowej.

Dopiero osobny pełny odbiór i decyzja właściciela mogą pozwolić zmienić status `VN-06` na `DONE`.
