# Video Notes

**Samodzielna aplikacja do transkrypcji i tworzenia notatek z nagrań oraz dźwięku na żywo.**

Video Notes powstaje na bazie doświadczeń modułu **[Notatki](https://github.com/testowyemailaplikacja-spec/Constant_app/tree/develop/apps/notatki)** z platformy Wiedora (Constant App). **Konwerter plików jest osobnym projektem i nie wchodzi w zakres Video Notes.**

## Kolejność rozwoju

1. **VN-00** — fundamenty programu, analiza istniejących Notatek i wybór lokalnego silnika transkrypcji.
2. **VN-01** — import nagrań OBS (MP4/MKV/WebM), wyodrębnienie mowy i transkrypcja 1:1 ze znacznikami czasu, eksport TXT/SRT.
3. **VN-02** — podstawowe notatki z transkrypcji: tytuły, punkty, streszczenie i możliwość edycji.
4. **VN-03** — zaawansowane notatki: konspekty, rozdziały, terminologia, cytaty źródłowe, opcjonalna analiza slajdów.
5. **VN-04** — nagrywanie wykładu mikrofonem na żywo i późniejsza transkrypcja.
6. **VN-05** — dodatkowe źródła dźwięku, np. audio systemowe, z kontrolą zgód i urządzeń.
7. **VN-06** — dopracowanie aplikacji Windows, instalacja, wydania offline i testy.
8. **VN-07** — zintegrowanie jako **oddzielnego modułu Wiedora** bez uzależniania działania samodzielnego programu od portalu.
9. **VN-08** — opcjonalne warianty mobilne.

## Założenia

- Pierwsza wersja dla Windows, bez obowiązkowego konta, płatnego API i przesyłania nagrań do chmury.
- Użytkownik zachowuje nagrania, transkrypcje i notatki lokalnie.
- Transkrypcja 1:1 nie oznacza gwarancji bezbłędnego rozpoznawania słów.
- Pracujemy etapami. **Kopia istniejącego kodu Notatek stanowi materiał referencyjny, nie potwierdzenie ukończenia programu Windows.**
- **Nie implementujemy w tym repozytorium konwersji PDF/DOC/DOCX/obrazów/MP3 itp. jako osobnego konwertera.** Przetwarzanie audio potrzebne do transkrypcji (np. odczyt ścieżki z filmu OBS) należy do Video Notes.

Dokument główny projektu: [Plan rozwoju Video Notes](docs/PLAN_ROZWOJU_VIDEO_NOTES.md). Analiza źródła: [Notatki w Constant App](docs/ANALIZA_NOTATEK_WIEDORA.md).

## Stan

- **06.11.2026: VN-00 i VN-01 W TRAKCIE.** Dodano lokalny prototyp źródłowy Python z FFmpeg/FFprobe, opcjonalnym whisper.cpp, CLI, GUI Tkinter, checkpointami i eksportem.
- **19/19 testów PASS** lokalnie na Linux z syntetycznymi próbkami. Realny silnik ASR i instalator Windows nie były jeszcze testowane; żaden etap nie jest DONE.
- `Constant_app` pozostaje bez zmian; prace prowadzone są wyłącznie tutaj.
- Repozytorium źródłowe Wiedora pozostaje bez zmian.

## Uruchomienie kodu rozwojowego VN-00 / VN-01

Wymagania: Python 3.10+, FFmpeg/FFprobe, lokalny program `whisper-cli` i legalnie pozyskany model `.bin`. Brak automatycznego pobierania modeli, kont i usług w chmurze. To nie jest jeszcze samodzielny instalator Windows.

```bash
python -m videonotes inspect nagranie.mkv
python -m videonotes transcribe nagranie.mkv --project moje-notatki --model ggml-base.bin --whisper-cli whisper-cli --language pl --stream 1
python -m videonotes resume moje-notatki
python -m videonotes export moje-notatki
python -m videonotes gui
python -m unittest discover -s tests -v
```

Indeks `--stream` należy odczytać poleceniem `inspect`. Przy wielu ścieżkach dźwiękowych trzeba go wybrać jawnie. Program zachowuje surowe segmenty w `transcript.json`, poprawki w `edits.json`, a cztery formaty eksportu w katalogu `exports`. Szczegółowe ograniczenia opisują `docs/VN00_IMPLEMENTATION.md` i `docs/CONTRACT_V1.md`.
