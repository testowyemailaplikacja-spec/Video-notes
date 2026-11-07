# VN — Odbiór fizyczny, jakościowy i bramka wydania (07.11.2026)

**Repozytorium wykonawcze:** `testowyemailaplikacja-spec/Video-notes`, gałąź `develop`. Platforma `Constant_app`, Netlify i Supabase pozostają poza tą procedurą. Niniejszy dokument opisuje testy, **nie jest dowodem ich wykonania**.

## 1. Kryteria wejścia

1. Osobny komputer Windows 10/11 x64 z dostępem do mikrofonu, kartą dźwiękową/loopback (o ile wspierany), możliwością odcięcia Wi-Fi i Ethernetu oraz użytkownikiem bez uprawnień administratora. Zanotować model CPU, RAM, wersję Windows, sterowniki, ilość miejsca i wyniki Windows Defender/SmartScreen bez ujawniania danych osobowych.
2. Dozwolone nagrania testowe: polski wykład 5–10 min, angielski tutorial 5–10 min, MP4 z OBS, MKV z mikrofonem i audio systemowym na osobnych ścieżkach, nagranie 2+ h, szum i cisza, plik błędny i bez audio. **Nie przesyłać prywatnych materiałów do GitHub Actions.**
3. Skontrolowane lokalnie `ffmpeg.exe`, `ffprobe.exe`, `whisper-cli.exe`, zgodny plik GGML `.bin`; osobno lokalne `faster-whisper` i model dla benchmarku. Zweryfikować legalność pochodzenia i warunki redystrybucji przed publikacją.
4. Aktualny commit `develop` i komplet zielonych GitHub Actions Linux/Windows/DEV EXE. Zielony CI **nie oznacza** udanego testu sprzętowego.

## 2. Przygotowanie pakietu bez automatycznego pobierania

Przenieść artefakt `VideoNotes-DEV.exe` z zatwierdzonego workflow na komputer testowy i zweryfikować SHA-256 pliku. Z **własnych legalnych lokalnych** binariów i modelu złożyć pakiet poleceniem:

```powershell
python -m videonotes bundle-dev --app C:\Test\VideoNotes-DEV.exe --ffmpeg C:\Tools\ffmpeg.exe --ffprobe C:\Tools\ffprobe.exe --whisper C:\Tools\whisper-cli.exe --model C:\Models\ggml-base.bin --output C:\Test\VideoNotes-LOCAL --internal-only
python -m videonotes bundle-verify C:\Test\VideoNotes-LOCAL
```

Obowiązkowy test negatywny: skopiować prywatną paczkę do osobnego katalogu, zmienić jeden bajt `bin/model.bin`, uruchomić jej `START-VIDEO-NOTES.cmd`; GUI ma **nie wystartować**, a oryginalnej paczki nie modyfikować. Wynik `bundle-verify` potwierdza lokalne SHA-256, nie autentyczność pakietu, licencje czy podpis cyfrowy.

## 3. Macierz testów (status początkowy NOT_RUN)

| ID | Scenariusz | Warunek PASS | Stan |
| --- | --- | --- | --- |
| HW-01 | Czysty Windows, sieć odłączona PRZED startem | Program, model i FFmpeg działają bez sieci oraz konta | NOT_RUN |
| ASR-01 | OBS MP4, jeden strumień, PL 5–10 min | Tekst, znacznik czasu i eksport TXT/SRT; WER/CER zmierzone | NOT_RUN |
| ASR-02 | OBS MKV, mikrofon i system audio osobno | Dwa strumienie wykryte, wybrany użyty zgodnie z decyzją | NOT_RUN |
| ASR-03 | OBS / tutorial EN | Zmierzone WER/CER i prędkość CPU, brak językowych duplikatów | NOT_RUN |
| ASR-04 | Realne whisper.cpp vs faster-whisper | Ten sam PCM, mierzone WER, CER, czas oraz RAM i zapisano decyzję | NOT_RUN |
| ASR-05 | 2+ h źródło i anulowanie/wznowienie | Nie ma duplikatów, brak utraty zapisanych checkpointów, RAM stabilny | NOT_RUN |
| ASR-06 | Plik uszkodzony, pusty, bez audio, brak modelu | Czytelny błąd i ochrona projektu | NOT_RUN |
| NOTE-01 | Rzeczywiste wykłady/CCNA, notatka podstawowa | Wszystkie cytaty pochodzą ze źródła, ocena człowieka zapisana | NOT_RUN |
| NOTE-02 | Konspekt zaawansowany, Markdown/JSON/DOCX | Kontrola zgodności cytatów i otwarcie DOCX w Word/LibreOffice | NOT_RUN |
| NOTE-03 | Regeneracja, undo, backup/restore | Poprawki użytkownika zachowane lub jawnie wskazany konflikt | NOT_RUN |
| MIC-01 | Mikrofon DirectShow, wybór i jawna zgoda | Nagranie odtwarzalne, Start/Stop zwalnia urządzenie | NOT_RUN |
| MIC-02 | Mikrofon 2 h + odłączenie, brak miejsca, wymuszony crash | Poprawne segmenty pozostają czytelne, stan needs_review po awarii | NOT_RUN |
| MIX-01 | Mikrofon + Stereo Mix/loopback z dwiema zgodami | Synchronizacja mowy i audio, brak cichego nagrywania | NOT_RUN |
| MIX-02 | Brak Stereo Mix lub odmowa uprawnień | Jasny komunikat, mikrofon samodzielny nadal działa | NOT_RUN |
| WEB-01 | Plik `web/index.html` otwarty z dysku w Chrome/Edge/Firefox | Import/edycja/eksport, ochrona przed utratą niezapisanych zmian | NOT_RUN |
| WEB-02 | Duży dozwolony JSON, klawiatura i czytnik ekranu | Responsywność, fokus, etykiety ARIA, brak zewnętrznych żądań | NOT_RUN |
| PKG-01 | Kontrola paczki, tamper i uruchomienie offline | Sumy SHA, brak niepożądanych plików, restart bez internetu | NOT_RUN |
| PKG-02 | Instalator, odinstalowanie, AV/SmartScreen, licencje | Rzeczywisty instalator i zweryfikowane prawa/podpis lub jawna polityka | NOT_RUN |
| HOST-01 | Izolowana beta Wiedora po wcześniejszych odbiorach | Osobna karta modułu, regresja platformy PASS, test granicy KWN | NOT_RUN |
| MOB-01 | Android/iOS (zakres opcjonalny VN-08) | Dopiero po zatwierdzeniu architektury, testach urządzeń | NOT_RUN |

**Rejestr wyników** dla każdego ID: data, commit, OS/sprzęt, źródło dozwolonego materiału (tylko lokalny identyfikator i SHA), dokładne kroki, wynik PASS/FAIL/NOT_RUN, wynik WER/CER/czas/RAM w razie potrzeby, uzasadnienie, ścieżka do **prywatnego** dowodu, osoba odbierająca. Publicznie wolno publikować tylko zanonimizowane agregaty. WER/CER i progi jakości trzeba uzgodnić po eksperymencie, nie wymyślać na podstawie mocków.

## 4. Aktualny dowód automatyczny

PR #16: testy Linux/Windows oraz DEV EXE PASS, ochrona edycji i zakończenia nagrywania.  
PR #17: testy Linux/Windows oraz DEV EXE PASS, kontrola integralności pakietu.  
PR #18: testy Linux/Windows oraz DEV EXE PASS, opcjonalny lokalny eksport DOCX.

Nie wykonano w tych PR-ach prawdziwej transkrypcji na modelach ASR, fizycznego nagrywania ani instalacji offline na odrębnym komputerze. **Nie podnosić statusu etapu do DONE** bez całej macierzy jego bramki akceptacji; źródło prawdy to `docs/VN_STATUS.json`.

## 5. Reguła integracji i wydania

`main` jako stabilna baza; codzienny kod KWN na odrębnych gałęziach → PR → sprawdzone CI → `develop`. Integracja z Wiedora jako odrębna beta wymaga pełnego odbioru potrzebnych pakietów, izolowanych testów hosta i odrębnej autoryzacji publikacji. Bez wystarczających licencji, oceny AV/Windows, jakości mowy i testów fizycznych nie tworzyć publicznego wydania 1.0.

## 6. Automatyczna regresja po PR #20–22 (07.11.2026)

Wszystkie poniższe przebiegi zostały zweryfikowane jako `success` **po odpowiednim ostatnim commicie PR**, przed scaleniem z `develop`:

| PR | Przebieg | Zakres | Wynik |
| --- | --- | --- | --- |
| [#20](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/20) | [42376117022](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42376117022) | Linux+Windows source CI, kontroler WWW, eksport, cofanie zmian | PASS |
| [#21](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/21) | [42376444170](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42376444170) | Linux+Windows source CI, napisy SRT/VTT i testy regresji | PASS |
| [#21](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/21) | [42376444161](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42376444161) | Budowa i smoke test Windows DEV EXE | PASS |
| [#22](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/22) | [42376671607](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42376671607) | Linux+Windows source CI, zabezpieczenia backupu | PASS |
| [#22](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/22) | [42376671514](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42376671514) | Budowa i smoke test Windows DEV EXE | PASS |

**Ważne:** te testy syntetyczne nie są fizycznym odbiorem ani testem instalacji offline. Statusy HW-01, ASR-01…06, MIC-01…02, MIX-01…02, WEB-01…02, PKG-01…02, HOST-01 oraz MOB-01 pozostają `NOT_RUN` zgodnie z tabelą. Odbiór rzeczywistego ASR i urządzeń nie może być zastąpiony powodzeniem CI.

## Regresja długiej sesji, bez fałszywego odbioru sprzętu

Test `tests/test_pipeline_long.py` uruchamia **syntetyczny** projekt 2 godziny 1 minuta w 61 fragmentach po maksymalnie 120 sekund, symuluje anulowanie po 12 zapisanych fragmentach, sprawdza wznowienie bez duplikatów, eksport i idempotentność kolejnego resume. Nie tworzy rzeczywistego nagrania 2h, nie uruchamia Whisper/FFmpeg i nie mierzy RAM ani jakości mowy. Jego PASS nie zmienia `ASR-05` i `HW-01` z `NOT_RUN` — potrzebny jest nadal fizyczny eksperyment z legalnym nagraniem i modelem.

## 7. Rzeczywisty test przeglądarki Chrome/Chromium — wyłącznie Linux CI

[GitHub Actions 42379566243](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42379566243) dla PR #30: **PASS** source Linux, source Windows i rzeczywistego headless Chromium na Ubuntu. Przeglądarka otworzyła `file://web/index.html`; lokalny syntetyczny import JSON, edycja, odmowa eksportu szkicu, poprawny TXT, ochrona przed utratą zmian i brak zasobów HTTP(S) w rejestrze `performance` zakończyły się powodzeniem. Nie przesyłano nagrań i nie uruchamiano ASR.

Jest to potwierdzony podtest przeglądarkowy, **nie całe WEB-01** (Chrome/Edge/Firefox na Windows), nie test dostępności/dużego 50k JSON (WEB-02), nie test Windows offline, nie publikacja beta Wiedora. Statusy w głównej macierzy pozostają NOT_RUN do wykonania wszystkich wymaganych wariantów.

## 8. Automatyczna macierz przeglądarkowa PR #32 i #33 (07.11.2026)

- [PR #32, Actions 42380043594](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42380043594): rzeczywisty headless Chrome i Edge w GitHub-hosted Windows oraz Chromium w Ubuntu, `file://` i lokalny import/edycja/eksport bez sieci — wszystkie wymagane joby PASS.
- [PR #33, Actions 42415998182](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42415998182): wszystkie cztery joby PASS (Python/Node Linux, Python/Node Windows, headless Chromium Ubuntu, headless Chrome i Edge Windows). Dodatkowo syntetyczna transkrypcja 50 000 segmentów, render maksymalnie 75 wierszy, wyszukanie ostatniego segmentu, stronicowanie i zachowanie fokusu po wyborze segmentu.
- Mierzone `50k synthetic browser interactions` w CI: Chromium Ubuntu **207 ms**, Chrome Windows **160 ms**, Edge Windows **109 ms**. To pomiary jednej próbki na współdzielonych runnerach, a nie gwarantowane wyniki urządzeń użytkowników.
- Tabela ma podpis dla czytnika, edytor nazwę regionu, aktywny przycisk `aria-pressed`, a fokus jest przywracany po odrysowaniu listy. To **automatyczny podtest**, nie odbiór przez użytkownika czytnika ekranu.

**Pozostają NOT_RUN:** Firefox na rzeczywistym Windows (`WEB-01`), test ręczny klawiatury i czytnika ekranu na fizycznym Windows oraz pomiary pamięci i responsywności na docelowym sprzęcie (`WEB-02`). Nie zmienia to pełnych statusów tych kryteriów w tabeli ani żadnego statusu etapu VN. Integracja hosta `HOST-01` wciąż wymaga osobnej bramki.
