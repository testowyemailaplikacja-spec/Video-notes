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

## Dwustrumieniowy OBS przez pełny lokalny łańcuch CLI (07.11.2026)

Test `tests/test_obs_multitrack_cli.py` tworzy osobno **prawdziwe pliki MP4 i MKV z wideo i dwiema syntetycznymi ścieżkami audio** (tony 440 i 880 Hz), wykorzystując FFmpeg i FFprobe w GitHub-hosted Ubuntu. Sprawdza odmowę automatycznego wyboru ścieżki w dwustrumieniowym źródle, poprawny wybór globalnego indeksu każdej ścieżki, dekodowanie FFmpeg do PCM 16 kHz, wywołanie **rzeczywistego lokalnego procesu w miejscu `whisper-cli`**, parsowanie JSON, globalne znaczniki czasu, przerwanie po checkpointcie, wznowienie bez dubli, poprawkę użytkownika i eksport JSON/TXT/SRT/VTT bez zmiany surowej transkrypcji.

Zastosowane lokalne `synthetic-whisper-cli` **nie rozpoznaje mowy**. To deterministyczna atrapa programu zewnętrznego, która na podstawie częstotliwości otrzymanego WAV zapisuje testowe segmenty w formacie whisper.cpp. Weryfikuje prawdziwy łańcuch procesów i wybór ścieżki, a nie jakość PL/EN ASR, zgodność binarium whisper.cpp ani instalatora. Żadne prywatne nagranie lub licencjonowany model nie jest przesyłany na GitHub.

## Realne dekodowanie 121 minut skompresowanego OGG/Opus (08.11.2026)

Osobny workflow `vn-real-long-media.yml` generuje lokalnie i tymczasowo **121-minutowy plik OGG/Opus** z oryginalnym syntetycznym tonem. Program rzeczywiście otwiera ten plik przez FFprobe i wycina w FFmpeg 61 kolejnych fragmentów PCM po 2 minuty. Po 12. ukończonym fragmencie symuluje żądanie zatrzymania, wznawia od 13. fragmentu i weryfikuje, że każde wywołanie dotyczy unikalnego odcinka, wszystkie checkpointy i cztery eksporty są kompletne, a plik źródłowy ma niezmieniony hash.

**Silnik ASR jest tutaj atrapą**, bo celem jest prawdziwy demultiplekser i wielogodzinne obciążenie przetwarzania plików, a nie wydajność rozpoznawania mowy przez model. Test prawdziwego `whisper.cpp` na krótkiej syntetycznej mowie PL/EN jest oddzielny; nie wolno łączyć obu dowodów w twierdzenie, że przetestowano prawdziwą 121-minutową transkrypcję rozpoznawaniem mowy. Nie przeprowadzono pomiarów pamięci rzeczywistego silnika ASR podczas 2h, testów fizycznego Windows, crash/restart zasilania i modelu ostatecznego.

Nagranie testowe i transkrypcja są generowane w runnerze CI i usuwane po zakończeniu. Model, prywatne nagrania i dane użytkownika nie są pobierane ani umieszczane w repozytorium. Wynik PASS należy weryfikować z osobnego workflow, a etap VN-01 nadal pozostaje W_TRAKCIE.
