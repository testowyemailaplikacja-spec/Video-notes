# KWN — uruchomienie beta Wiedora i dalsze wdrożenia (12.11.2026)

## 1. KWN BETA na Wiedorze: faktycznie opublikowana

Na osobne polecenie właściciela wdrożono wyłącznie testową betę Konwertera Notatek. Repozytorium docelowe hosta: `testowyemailaplikacja-spec/Constant_app`, gałąź `develop`. PR: [#203](https://github.com/testowyemailaplikacja-spec/Constant_app/pull/203), merge commit `0689332f7fae4c881b6cabee31568e0b16c2f943`. Wydanie Netlify `6af5f829ddad274ac6d1d713` zakończyło się statusem **READY**. Niezależnie pobrany z HTTPS `build-info.json` potwierdził dokładnie ten commit i identyfikator wydania. Przed integracją PR Preview `6af5f77a80ef5fd4951fe5bd` zakończył build READY.

Istniejący hostowy panel **Wersja beta · Tylko KWN** oferuje dwa rozdzielone wejścia:
- [Aplikacja KWN BETA](https://develop--constant-app.netlify.app/apps/notatki-web/) — samodzielny lokalny moduł WWW/PWA notatek, nagrań i biblioteki.
- [Video Notes BETA — edytor eksportów](https://develop--constant-app.netlify.app/apps/notatki-web/video-notes/) — import transkrypcji z programu Windows, lokalna korekta/eksport tekstu; **nie** uruchamia Python/Whisper/GGUF/desktopowego ASR.

Zewnętrzny odczyt HTTPS: katalog `/`, PWA, edytor, `source-version.json`, starsze `/apps/notatki/` i `build-info.json` zwracają **200**; niepublikowany techniczny dokument i ścieżka bety na produkcyjnym `main` zwracają **404**. Strony testowe mają `noindex,nofollow`. Zasoby `web/app.js` i `web/transcript-core.js` są skopiowanymi, audytowanymi blobami z Video-notes źródło `e22b21763f535cd73285c2d7f1596d3e3a805d1d`, potwierdzanymi nowym testem hostowym. Nie umieszczono modeli, nagrań ani innych danych użytkownika na serwerze.

**Ograniczenie:** GitHub Actions w hostowym PR #203 zakończyło oba zadania **przed pierwszym krokiem** (zero steps), więc pełne `npm run verify` / `verify:full` są **NOT_RUN**. Interaktywny test tej konkretnej wersji hosta nie został przeprowadzony: próba zdalnej sesji przeglądarkowej została odrzucona przez limit współbieżnych sesji. Istnieje wcześniejszy test rzeczywistego Chromium dla mostu WWW (Wiedora PR #189), ale nie należy przedstawiać go jako testu interakcji na aktualnym wydaniu #203. Nadal brakuje fizycznego Windows/NVDA, naturalnej mowy, lokalnych licencjonowanych modeli i pełnego odbioru wydania.

Po wdrożeniu host otrzymał **osobny dokumentacyjny PR #204** z rzeczywistym wynikiem publikacji i blokadami; nie wywołało to ponownego kosztownego Netlify builda. Produkcyjny `main`, starsze Notatki, CCNA, inne WPL, Supabase i role użytkowników pozostały nietknięte.

## 2. Kontynuacja źródłowego programu KWN

Niezależne źródło: `testowyemailaplikacja-spec/Video-notes`, gałąź `develop`. Po opublikowaniu bety ukończono:

| Etap | Realnie scalony PR | Poprawka i testy końcowe |
|---|---|---|
| VN-00 | [#154](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/154), `46c2e4c914da367288110b13f9b8a17e4219c84d` | Bezpieczny, ograniczony do 300001 B odczyt porównywanych plików TXT i odmowa symlinków, również kiedy plik rośnie po stat(). **7/7 CI PASS**, Linux/Windows i przeglądarki; [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/154/checks) |
| VN-07 | [#156](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/156), `ec2dcf318e89afa85fa663775c86430520fa9fd1` | Import transkrypcji i poprawek przeglądarkowych odrzuca zduplikowane klucze JSON, także przy ucieczce `\\uXXXX`. **6/6 CI PASS**, Linux/Windows i Chromium/Firefox/Edge/Chrome; [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/156/checks) |

Pierwotny PR #155 miał regresję **w fiksturze testowej**, która nie odtwarzała naprawdę duplikatu pola w JSON formatowanym z odstępami; prawidłowo zgłosił błąd w CI, został zamknięty bez scalania. Poprawione testy i program scalono dopiero przez PR #156 po zielonym 6/6. Łącznie finalne **13/13 zadań CI PASS** dla dwóch scalonych PR, nie jest to 13 zamkniętych kryteriów planu.

**Ważne rozdzielenie wersji:** po PR #156 gałąź źródłowa KWN zawiera ulepszony import JS, natomiast opublikowana beta Wiedory pozostaje celowo przypięta do **wcześniejszego, przetestowanego bloba JS**. Nowa wersja nie została po cichu opublikowana w hostowym środowisku; kolejna zbiorcza synchronizacja wymaga osobnej kontroli KWN i wydania `develop`. Nie podmieniać bloba tylko na podstawie samych numerów commitów.

## 3. Status etapów

Odbiór **publikacji bety i konkretnych PR kodowych** nie stanowi 100% ukończenia. Formalnie: **0/9 VN DONE, 8 W_TRAKCIE, 1 PLANOWANE**; mikrozadania: **2 DONE, 1 IN_PROGRESS (VN-07-05), 34 TODO**. VN-07-05 pozostaje W_TRAKCIE do full host regression, fizycznej przeglądarki/klawiatury/screen reader i wyników odbioru. Naturalne PL/EN, fizyczny Windows z mikrofonem i ASR 2h+, licencje modeli oraz decyzje człowieka nadal blokują formalne DONE etapów. Nie przenosić historycznego `KWN_STATUS.json` z 189 kryteriami na bieżący rejestr 37 mikroplanów.
