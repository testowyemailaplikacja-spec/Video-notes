# KWN — odbiór techniczny pakietów PR #131–136 (12.11.2026)

Źródło: testowyemailaplikacja-spec/Video-notes. Gałąź docelowa: develop. Wszystkie pięć pakietów kodu jest scalonych. Poniższe liczby dotyczą **uruchomień CI**, nie odbioru całych etapów ani testów na fizycznym sprzęcie.

| Etap | Scalone wdrożenie | Faktycznie poprawiony problem | Finalne testy GitHub CI |
|---|---|---|---|
| VN-05 | [PR #131](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/131), merge 26c3d29f08ebe6b8860dcab152deadf4fded0f5b | Najdłuższa cisza w raportach sygnału obejmuje granice WAV; po analizie weryfikacja stanu dziennika i SHA-256 | **10/10 PASS** — [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43210420480) |
| VN-04 | [PR #132](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/132), merge ff45ba1d6bdcbb310d731acacea30e1f28ca31b8 | Niedokończone, źle nazwane, ponadlimitowe części WAV lub osierocone foldery .vn-take nie są po cichu pomijane | **8/8 PASS** — [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43210732300) |
| VN-00 | [PR #134](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/134), merge 65594747c31af074b7801051f70720a947811f9e | Raport WER/CER benchmarku zapisany atomowo bez nadpisania wyniku równoległego benchmarku | **7/7 PASS** — [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43211434305) |
| VN-04 | [PR #135](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/135), merge 3b97908af7fb800c76774909c9bcf78305a688e6 | Podczas odzyskiwania niepełnego nagrania pełna lista WAV, SHA-256 oraz dziennik sprawdzane ponownie przed publikacją | **9/9 PASS** — [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43211779543) |
| VN-02 | [PR #136](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/136), merge e318446b9149e609ba5a4728f2eda6aae47346e5 | Eksport zatwierdzonych twierdzeń AI porównuje pełną zawartość decyzji i szkicu, nie tylko niezmienione liczniki approve/reject | **7/7 PASS** — [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43212396479) |

**Łącznie: 41/41 końcowych zadań GitHub CI PASS na finalnych head SHA pięciu PR-ów.** Zadania obejmowały m.in. Python/Windows/Linux, przeglądarki, GUI w środowiskach hostowanych oraz wybrane realne narzędzia FFmpeg na własnych danych syntetycznych. Nie są to 41 nowe mikrozadania planu.

## Konflikt i bezpieczna integracja

PR #133 (wersja źródłowa poprawki odzyskiwania WAV) zakończył CI 9/9 PASS, lecz konfliktował z równolegle scalonym PR #132 w dokumentacji VN-04. Nie scalono konfliktowej wersji. Utworzono nową gałąź z aktualnego develop, przeniesiono poprawkę kodu i testy oraz zachowano obie sekcje dokumentacji. Po 9/9 PASS poprawkę scalono jako PR #135; PR #133 zamknięto jako zastąpiony, bez merge.

## Czego ten cykl NIE odbiera

Oficjalny rejestr pozostaje 0/9 VN etapów DONE (8 W_TRAKCIE, 1 PLANOWANE), a mikroplan: 2/37 DONE, 1 IN_PROGRESS, 34 TODO. Nadal potrzebne są legalnie pozyskane naturalne nagrania PL/EN i ręczny wzorzec WER/CER; rzeczywisty test Windows offline z mikrofonem i loopback, długim nagraniem 2h+, awarią i wznowieniem; właściwe licencje modeli i narzędzi, ocena faktów przez człowieka, instalator/AV/SmartScreen i końcowy odbiór beta Wiedora.

Wykonane poprawki wykrywają rzeczywiste klasy błędów w kontrolowanych scenariuszach, ale nie tworzą atomowego snapshotu wobec dowolnego zewnętrznego procesu ignorującego blokady. Diagnostyka audio to analiza amplitudy, nie dowód poprawności transkrypcji. Zapis decyzji AI dowodzi tylko deklaracji użytkownika, nie niezależnego sprawdzenia faktów.

Nie zmieniano Constant_app, Netlify, Supabase ani produkcyjnego main. Nie publikowano prywatnych nagrań, lokalnych modeli i sekretów. Status BETA oraz izolacja KWN pozostają.
