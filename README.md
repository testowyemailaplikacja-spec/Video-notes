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

- Repozytorium zainicjalizowane.
- Program Windows, testy na sprzęcie, instalator i integracja z portalem — **niezaimplementowane**.
- Repozytorium źródłowe Wiedora pozostaje bez zmian.
