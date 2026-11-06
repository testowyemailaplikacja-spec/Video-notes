# VN-00 / VN-01 — implementacja i dowody

**Data:** 06.11.2026. **Repo:** testowyemailaplikacja-spec/Video-notes. **Status:** VN-00 W TRAKCIE; VN-01 W TRAKCIE; żaden z tych etapów nie przeszedł pełnej bramki akceptacji.

## Zaimplementowany kod

1. FFprobe odkrywa ścieżki audio w MP4/MKV/WebM/WAV. Wielościeżkowy plik wymaga jawnego wyboru indeksu; brak audio i uszkodzone pliki dają błąd.
2. FFmpeg wycina odcinki PCM mono/16 kHz na dysk tymczasowy. Nie ma wymogu wczytywania całego filmu OBS do RAM.
3. Adapter whisper.cpp używa lokalnego pliku wykonywalnego i modelu, parsuje JSON i globalne czasy. Nie pobiera modeli ani nie korzysta z płatnego API.
4. Katalog projektu zapisuje wersjonowany JSON, SHA-256 źródła i modelu, checkpoint po całym fragmencie, poprawek nie miesza z surowym ASR.
5. CLI umożliwia inspect/transcribe/resume/status/edit/export; GUI Tkinter umożliwia wybór źródła, ścieżki audio, modelu, rozpoczęcie, wznowienie i poprawki.
6. Eksport: TXT, SRT, VTT, JSON. Nie zmieniono Constant_app, Netlify ani Supabase.

## Weryfikacja lokalna

`python -m unittest discover -s tests -v`: **19/19 PASS, 0 FAIL, 0 SKIP**, Linux, Python 3.13.5, FFmpeg/FFprobe. Realne przetwarzanie syntetycznych WAV i dwustrumieniowego MKV, uszkodzony MKV, materiał bez audio, restart po symulowanym błędzie ASR, cisza w drugiej części, brak duplikacji segmentów, blokada równoległa, odmowa nadpisania istniejącego projektu, walidacja JSON, polskie znaki, podpisy czasowe i eksport.

**Ograniczenie dowodu:** prawdziwego modelu Whisper nie uruchomiono. Test integracyjny transkrypcji używał kontrolowanego stubu, a test adaptera ASR mocka. Testy CLI/FFmpeg nie są testem jakości polskiego rozpoznawania mowy ani działania samodzielnego instalatora Windows.

## Brakujące bramki VN-00

1. Legalne próbki rzeczywistych OBS PL/EN 5–10 min, MKV z mikrofonem i dźwiękiem komputera, nagranie 2+ h; brak prywatnych nagrań w publicznym repo.
2. Porównanie whisper.cpp oraz faster-whisper na tej samej próbce: WER, szczyt RAM, CPU, czas/minutę nagrania, pakowalność i warunki licencyjne.
3. Czysty Windows 10/11 bez sieci, instalator ze wszystkimi zależnościami i modelem, testy sprzętowe, długie pliki i brak miejsca na dysku.
4. Decyzja właściciela o licencji własnego produktu oraz dystrybucji modeli.
5. Testy awarii zasilania i odzyskiwania blokady przetwarzania, bezpieczeństwo plików 2+ GiB, walidacja sprzętu i koszt hashowania.

## Następny zakres

Wykonać rzeczywiste benchmarki dwóch silników ASR i decyzję technologiczną, następnie Windows offline i test GUI. VN-02–VN-08 pozostają nieukończone. Nie przenosić zmian na główną stronę przed zbiorczą aktualizacją i osobną zgodą.

Źródła interfejsów (zweryfikowane 06.11): https://github.com/ggml-org/whisper.cpp/tree/master/examples/cli i https://ffmpeg.org/ffmpeg.html.
