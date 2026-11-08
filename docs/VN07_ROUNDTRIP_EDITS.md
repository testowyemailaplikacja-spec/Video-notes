# VN-07 — bezpieczna wymiana poprawek WWW → desktop

**Zakres (08.11.2026):** import poprawek ze statycznego lokalnego `web/index.html` do istniejącego projektu Windows/Python, bez konta, serwera ani przesyłania materiałów. To nie jest synchronizacja Wiedora ani funkcja rozpoznawania mowy w przeglądarce.

## Użycie

1. W desktopie: `python -m videonotes export KATALOG_PROJEKTU`.
2. W przeglądarce otwórz `web/index.html`, załaduj `exports/transcript.json`, wprowadź poprawki i kliknij **Poprawki do programu (JSON)**. Zapisz plik `web-corrections.json`. Pobranie pełnego `transcript.json` pozostaje osobnym eksportem.
3. Na komputerze desktopowym wykonaj najpierw podgląd, a potem jawny zapis:

```powershell
python -m videonotes import-web-edits C:\\Notatki\\Projekt --file C:\\Pobrane\\web-corrections.json
python -m videonotes import-web-edits C:\\Notatki\\Projekt --file C:\\Pobrane\\web-corrections.json --apply
python -m videonotes export C:\\Notatki\\Projekt
```

## Zabezpieczenia

Format `videonotes-web-corrections-v1` zawiera wyłącznie zmienione pozycje: `project_id`, `id`, `start_ms`, `end_ms`, `before` (tekst zaimportowany do WWW) i `after` (poprawka użytkownika). Import sprawdza schemat, rozmiar, identyfikator projektu, unikalność segmentów, dokładne czasy i zgodność tekstu bazowego. Konflikt pojedynczej zmiany **odrzuca całą paczkę** — nie ma częściowego zapisu ani zgadywania, co autor chciał zachować. Podgląd nie modyfikuje plików; `--apply` modyfikuje atomowo jedynie `edits.json`, pozostawiając pozostałe poprawki oraz oryginalny `transcript.json`. Gdy poprawiony tekst jest identyczny z surowym ASR, import usuwa nadmiarową poprawkę.

Nie importuj pełnego `transcript.json` przez `import-web-edits`: to inny format. Nie modyfikuj pliku projektu podczas importu; zmiana wykryta przed zapisem powoduje odmowę. Nie ma gwarancji synchronizacji przy jednoczesnych zapisach z dwóch procesów, zewnętrznych blokadach plików ani odporności na utratę zasilania podczas zapisu systemu plików. Po zmianie transkrypcji istniejące notatki mogą być nieaktualne i wymagają osobnej, kontrolowanej regeneracji.

## Odbiór

Testy Node i Python potwierdzają strukturę paczki, poprawki Unicode, brak zapisu bez `--apply`, przywrócenie oryginału, konflikty, niedozwolone pola, duplikaty, limit 20 MB oraz zachowanie niepowiązanych poprawek. Testy przeglądarkowe w CI należy osobno potwierdzić po scaleniu. **VN-07 pozostaje W TRAKCIE**: brak integracji do Wiedora, rzeczywistego przeglądarkowego ASR i fizycznego odbioru Windows. Brak wnioskowania o zakończeniu etapu na podstawie testów automatycznych.
