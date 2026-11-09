# KWN Video Notes — formalny odbiór pakietów PR #103 i #104

**Data:** 9 listopada 2026 r.

**Repozytorium robocze:** `testowyemailaplikacja-spec/Video-notes`  
**Gałąź bazowa:** `develop`, po integracji PR #104: `f3454af8b6cfd273c096d9900938a92807bcf515`.  
**Gałąź stabilna:** `main` bez zmian. Wiedora/Netlify nie zmieniono.

## Wdrożenia

**PR #103** — `https://github.com/testowyemailaplikacja-spec/Video-notes/pull/103`. Dodano lokalny dziennik decyzji dotyczących każdego twierdzenia szkicu llama.cpp. Decyzje `approve`/`reject` wymagają jawnego `--confirm`, są zapisywane w odrębnych plikach bez nadpisania. Weryfikacja obejmuje integralność szkicu, źródła, identyfikatorów, cytatów i wszystkich decyzji. Eksport Markdown jest dostępny dopiero po rozpatrzeniu wszystkich twierdzeń i zawiera wyłącznie te zatwierdzone przez użytkownika. Zmiana źródła, obca decyzja, podmiana cytatu lub konflikt równoległy wywołują odmowę. Nie udaje to niezależnej weryfikacji faktów ani tożsamości.

**PR #104** — `https://github.com/testowyemailaplikacja-spec/Video-notes/pull/104`. W zakładce lokalnej analizy Tk dodano `Oceń szkic AI`. Osobne okno wyświetla ID twierdzenia, cytaty, źródłowe czasy, decyzje i stan recenzji. Użytkownik może wyraźnie zatwierdzić/odrzucić, wyeksportować zatwierdzony zakres i wrócić do niego później. Blokada nie pozwala pracować nad recenzją podczas niezapisanej korekty transkrypcji. Nie ma automatycznych zatwierdzeń, publikowania w hostowanej Wiedorze ani transferu źródłowych nagrań.

## Dowody odbioru CI — ostateczne commity PR

| PR | GitHub Actions run | Zweryfikowane zadania | Wynik |
|---|---|---|---|
| #103 | [42694635216](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42694635216) | Linux/Windows Python + przeglądarki | **5/5 PASS** |
| #103 | [42694635639](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42694635639) | Windows DEV EXE | **1/1 PASS** |
| #103 | [42694635341](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42694635341) | Prywatny Inno synthetic smoke | **1/1 PASS** |
| #104 | [42695708549](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42695708549) | Linux/Windows Python + przeglądarki | **5/5 PASS** |
| #104 | [42695708700](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42695708700) | Windows DEV EXE | **1/1 PASS** |
| #104 | [42695709291](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42695709291) | Realne kontrolki Tk Linux Xvfb i Windows VM | **2/2 PASS** |

**Łącznie: 15/15 PASS.** Początkowy CI PR #103 wykrył brak ID twierdzenia w Markdown; po poprawce weryfikacja na ostatecznym commicie zakończyła się kompletem PASS. Nie należy mieszać pierwszej nieudanej próby z wynikiem odbiorowym.

## Bramy pozostające otwarte

1. **VN-02/VN-03:** jakościowe porównanie realnego wykładu PL/EN, prawdziwy GGUF/llama.cpp, sprawdzenie poprawności merytorycznej przez człowieka, realne slajdy CCNA i rzeczywisty odbiór DOCX/Word.
2. **VN-00/VN-01:** prawdziwe nagrania OBS i godzinowy/wielogodzinny Whisper na docelowym sprzęcie, RAM/WER/CER, pełny offline Windows.
3. **VN-04/VN-05:** fizyczny mikrofon, system audio/loopback, 2h, uszkodzenia sprzętu, awarie/dysk i przywracanie.
4. **VN-06:** licencje dystrybucyjne modeli i narzędzi, podpis, antywirus, instalator na fizycznym Windows.
5. **VN-07/VN-08:** autoryzowana izolowana beta Wiedory oraz ewentualne przyszłe moduły mobilne.

**Stan formalny po odbiorze:** **0/9 DONE**, **8/9 W_TRAKCIE**, **1/9 PLANOWANE**. Żaden etap nie został oznaczony DONE tylko dlatego, że uruchomiono syntetyczne CI.
