# KWN — zbiorczy odbiór techniczny PR #126–129 (12.11.2026)

Źródło: testowyemailaplikacja-spec/Video-notes, gałąź develop. Odbiór dotyczy zmian rzeczywiście scalonych do develop, **nie pełnego zakończenia etapów**.

| Etap | PR, squash commit | Zmiana rzeczywista | Weryfikacja finalnego head SHA |
|---|---|---|---|
| VN-01 — PCM z FFmpeg | [#126](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/126) — 23e7b2c0da85a551a2fc679a3103c3c83ce84126 | Sprawdzanie fizycznej dostępności wszystkich ramek PCM; niedopuszczanie uciętych WAV do ASR; FFmpeg z -n zamiast -y (bez nadpisania) | **8/8 PASS**, [workflow](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43161691133) |
| VN-01 — checkpoint źródła/modelu | [#127](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/127) — 7ca1734af9b24e2990dab5b7592fb86177cb4bee | Weryfikacja atrybutów źródła i modelu przed fragmentem i po ASR, przed zapisem checkpointu; wykrywanie typowych zmian w toku transkrypcji przy zachowaniu wcześniej ukończonych fragmentów | **9/9 PASS**, [workflow](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43161864211) |
| VN-06 — stabilny backup | [#128](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/128) — 3b686fb1714ffebb4d44f2e0c4d86e912841f316 | Ponowna weryfikacja danych projektu, transkrypcji, notatek, ręcznych poprawek i historii przed opublikowaniem ZIP; przy równoległej zmianie odmowa zamiast mieszania stanów | **7/7 PASS**, [workflow](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43162438055) |
| VN-02 — własność blokad | [#129](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/129) — 74253fa6e1573359e6e9edef6eceab006c415126 | Tworzenie, ręczna edycja, regeneracja i przywracanie notatek nie usuwają podmienionej blokady. Wspólna kontrola tożsamości pliku uwzględnia odmienną aktualizację metadanych NTFS i POSIX | **10/10 PASS**, [workflow](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43163071262) |

**Łącznie 34/34 końcowych zadań CI PASS** na finalnych commitach head czterech PR. Do testów należały Python Linux/Windows, faktyczne FFmpeg na danych syntetycznych, przeglądarki file://, wybrane hostowane testy Tk i dokumentów oraz w szczególnych workflow syntetyczne długie nagrania i realny whisper.cpp na syntetycznym TTS. Liczba 34 oznacza zadania CI, nie 34 kryteria etapu.

## Co wykazały testy, zanim nastąpiło scalenie

W PR #128 pierwotny scenariusz testowy źle wskazywał katalog historii (odczyt odbywa się z podrzędnego notes-history); poprawiono test i ponownie uzyskano 7/7 PASS.

W PR #129 Linux ujawnił natychmiastowe ponowne użycie numeru inode po usunięciu pliku blokady. Dodano sprawdzenie dat i rozmiaru, lecz Windows ujawnił, że metadane NTFS mogą aktualizować się przy zamknięciu deskryptora, co pozostawiało fałszywe aktywne blokady. Poprawiono sposób sprawdzania tożsamości osobno dla POSIX i Windows i powtórzono końcowe 10/10 PASS. **Nie scalano wadliwych commitów.**

## Nadal otwarte warunki pełnego odbioru

Rejestr VN zachowuje 0/9 ukończonych etapów (8 W_TRAKCIE, 1 PLANOWANE) i 2/37 formalnie zakończonych mikrozadań. Powody: brak legalnych naturalnych próbek i ludzkiej transkrypcji referencyjnej PL/EN do WER/CER, brak końcowego fizycznego Windows ze sprzętem USB i nagraniem 2h+, brak prawdziwego GGUF i merytorycznej oceny treści, licencji dystrybucyjnych, podpisu i testu instalatora, brak pełnego niezależnego odbioru Wiedora.

Wariant VN-01 z kontrolą metadanych nie jest kryptograficzną ochroną przed złośliwym procesem przywracającym dawne atrybuty. Kontrola kopii dwoma odczytami także nie stanowi transakcyjnej migawki systemu plików wobec dowolnych procesów zewnętrznych. Obie poprawki eliminują typowe bezpiecznie reprodukowane wyścigi, bez deklaracji absolutnej odporności.

Nie zmieniono repozytorium Wiedora, Netlify, Supabase ani gałęzi main, nie przetwarzano ani publikowano prywatnych nagrań/modeli. Oznaczenie beta i izolacja pracy nad KWN pozostają obowiązujące.
