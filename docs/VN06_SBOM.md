# VN-06 — lokalny inwentarz SBOM SPDX 2.3 prywatnego instalatora

**Stan 08.11.2026:** narzędzie wytwarza czytelną maszynowo listę pięciu składników zweryfikowanego pakietu wewnętrznego. Nie pobiera ich i nie uzyskuje automatycznie praw licencyjnych.

Po zbudowaniu pakietu `bundle-dev` wykonaj:

```powershell
python -m videonotes bundle-verify C:\\Test\\VideoNotes-PRIVATE
python -m videonotes bundle-sbom C:\\Test\\VideoNotes-PRIVATE --output C:\\Test\\VideoNotes-PRIVATE.spdx.json
```

Raport zawiera standardowe pola SPDX 2.3, ścieżki względne `./VideoNotes-DEV.exe`, `./bin/ffmpeg.exe`, `./bin/ffprobe.exe`, `./bin/whisper-cli.exe`, `./bin/model.bin`, sumy SHA-256 i relacje `DESCRIBES`. Program sprawdza integralność całej paczki zarówno przed budową raportu, jak i przed zapisem. Zapis jest atomowy w obrębie dysku i nigdy nie nadpisuje istniejącego raportu. Nie wolno umieszczać go w katalogu samego pakietu, ponieważ zmieniłby chroniony zestaw plików. Dokument nie zawiera absolutnych ścieżek wejściowych.

**Ważne ograniczenia:** każda licencja jest jawnie oznaczona `NOASSERTION`. Inwentarz nie potwierdza legalności dystrybucji, tożsamości dostawcy, pochodzenia modelu, zgodności GPL/LGPL, bezpieczeństwa kodu, braku luk, podpisu cyfrowego, zgodności z polityką SmartScreen ani działania na fizycznym Windows bez internetu. Przed publikacją wymagany jest osobny przegląd licencji, wersji zależności, AV, podpisania i testów sprzętowych.

Testy `tests/test_sbom.py` korzystają z syntetycznych plików. Sprawdzają zgodność hashy z manifestem, oznaczenie nieustalonych licencji, brak ścieżek prywatnych, ochronę przed nadpisaniem oraz odmowę wygenerowania raportu dla zmienionej paczki. **VN-06 pozostaje W TRAKCIE** do spełnienia rzeczywistych bramek odbioru.
