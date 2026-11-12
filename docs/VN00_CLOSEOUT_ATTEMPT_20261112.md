# VN-00 — kontrola domknięcia etapu, 12.11.2026

## Status: W TRAKCIE — formalny odbiór NIEZALICZONY

**Ważne:** To raport faktycznie wykonanych prac źródłowych i identyfikacja nierozstrzygniętych bramek. Nie stanowi atestu rzeczywistych nagrań, fizycznego Windows ani opinii prawnej. Nie zmienia `VN_STATUS.json` ani `VN_MICROTASKS.json`.

### Zrealizowana poprawka bezpieczeństwa i odtwarzalności benchmarku

- W `videonotes/asr_lab.py` raport benchmarku rzeczywistych dwóch silników zawiera teraz SHA-256 `vocabulary.txt` i opcjonalnego `tokenizer.json`, oprócz istniejących SHA-256 modeli, konfiguracji, źródła i wspólnego PCM.
- Jeżeli obecny na starcie `tokenizer.json` zostanie zmieniony/usunięty podczas inferencji albo zostanie dodany podczas pomiaru, wyniki nie zostaną opublikowane. Dowiązania do tokenizera nie są przyjmowane.
- Referencja TXT przekazana jako symlink jest odrzucana **przed** normalizacją ścieżki i uruchomieniem FFprobe/ASR. Poprzednie `Path.resolve()` ukrywało taki symlink przed `quality._read()`.
- Dodano testy automatyczne w `tests/test_asr_lab.py` obejmujące kompletność fingerprintów, modyfikację/pojawienie się tokenizera i referencję będącą symlinkiem. Wynik CI musi być potwierdzony na ostatnim SHA, zanim pojawi się oznaczenie PASS.

### Licencje — wstępna, sprawdzalna analiza źródeł

| Komponent | Upstream i deklaracja | Zakres potwierdzenia | Pozostały warunek |
|---|---|---|---|
| whisper.cpp | https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE — MIT | Licencja projektu upstream | Zweryfikować konkretny commit, dystrybuowany build i zawarte zależności |
| Whisper — kod i oryginalne wagi | https://github.com/openai/whisper#license — MIT | Deklaracja upstream | Ustalić pochodzenie i SHA konkretnego modelu GGML |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE — MIT | Licencja wrappera upstream | Zbadać CTranslate2, PyAV, zależności runtime i konkretny pakiet |
| FFmpeg | https://ffmpeg.org/legal.html — LGPL 2.1+ lub GPL 2+ zależnie od konfiguracji | Oficjalna polityka licencyjna | Odczytać `ffmpeg -buildconf` dla konkretnego binarium; dołączyć wymagane źródła/noty i dokumentację po audycie |
| Model CTranslate2 | https://huggingface.co/Systran/faster-whisper-tiny | Wykorzystywany w syntetycznym CI z przypiętymi SHA/revizją | Potwierdzić komplet wag/plików i pochodzenie dla **tego**, który trafi do instalatora |

**Decyzja techniczna na tym etapie:** lokalny `whisper.cpp` na CPU pozostaje *kandydatem* na domyślny silnik Windows; `faster-whisper` to porównywana alternatywa. To **nie jest** ostateczny wybór jakościowy ani zgoda na dystrybucję. Dopóki nie ma wyników PL/EN na naturalnej mowie na docelowym Windows i pełnego audytu wybranego pakietu, formalny VN-00-03 pozostaje TODO.

### Rzeczywiste niezakończone bramki VN-00

| ID | Wymagany odbiór | Stan na 12.11 |
|---|---|---|
| VN-00-01 / ASR-01 | Legalne naturalne nagrania PL/EN, OBS MP4/MKV, trudny fragment, ręcznie sprawdzony referencyjny tekst; prywatne hashe | NOT_RUN |
| VN-00-02 / ASR-04 | Porównanie obu **prawdziwych** silników na tych samych naturalnych próbkach, WER/CER, wall time, peak RSS, CPU i raport | NOT_RUN na naturalnej mowie; CI na syntetycznym TTS działa |
| VN-00-03 / PKG-02 | Licencje konkretnych plików binarnych/modeli, budowanie, zależności, zatwierdzona decyzja technologiczna | Częściowa analiza upstream; NOT_APPROVED |
| VN-00-04 / HW-01 | Fizyczny Windows 10/11, test całkowicie offline, uruchomienie pakietu bez konta/internetu, weryfikacja SHA | NOT_RUN |

### Bezpieczna procedura formalnego odbioru

1. Na fizycznym Windows przygotować **lokalnie**, bez uploadu do repo, próbki i referencje z prawem użycia. Zachować sumy SHA i pochodzenie.
2. Uruchomić `python -m videonotes benchmark-real` zgodnie z `docs/REAL_ASR_LAB.md` osobno dla polskiego/angielskiego i różnych warunków akustycznych, pamiętając o tej samej długości referencji i WAV.
3. Zweryfikować oba silniki, WER/CER, czas, RAM i spójne SHA, udokumentować maszynę, wersje, wariant modeli oraz decyzję dotyczącą jakości; **nie kopiować transkrypcji** do publicznego repo.
4. Sprawdzić na fizycznym Windows bez dostępu do internetu pakiet DEV/instalator, uruchomienie, brak pobierania modeli i sumy plików. Wykonać przegląd licencji dokładnych binariów, nie samych nazw projektów.
5. Można utworzyć prywatny szablon dowodowy `python scripts/vn_acceptance_evidence.py --init lokalny-przeglad.json`, a potem walidować przez `--check`. Samo wpisanie `PASS` jest tylko deklaracją człowieka. Niezależna kontrola dowodów przed statusem DONE obowiązkowa.

Wszystkie wcześniejsze próbki TTS i syntetyczne OBS należy nadal oznaczać jako **syntetyczne**, a dostępne testy Linux/Windows CI nie zastępują fizycznej kontroli Windows.

## Zasada przekazania

Dopiero po dowodach obejmujących **wszystkie** cztery VN-00-01…04 oraz zgodności z bramką głównego planu wolno zmienić status VN-00 z `W_TRAKCIE` na `DONE`. Bez tego rejestry pozostają bez zmian.
