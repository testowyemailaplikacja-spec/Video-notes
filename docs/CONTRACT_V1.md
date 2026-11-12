# Video Notes — lokalny kontrakt danych v1 (VN-00)

**06.11.2026:** kod i testy kontraktu istnieją, ale format wymiany nie jest jeszcze zatwierdzony do produkcji ani do adaptera WWW.

Program trzyma projekt w lokalnym katalogu użytkownika. Nagranie OBS i model ASR pozostają w lokalizacji wskazanej przez użytkownika. Niczego automatycznie nie wysyła ani nie pobiera.

| Plik | Znaczenie | Gwarancja |
| --- | --- | --- |
| `project.json` | Wersja, UUID, źródło i SHA-256, wybrany indeks ścieżki audio, czas, lokalny model i jego SHA-256 | przy wznowieniu sprawdzana zgodność źródła i modelu |
| `transcript.json` | Surowe segmenty (`id`, `chunk_index`, `start_ms`, `end_ms`, `text`, `status=raw`) i `completed_chunks` | atomowy zapis całego ukończonego fragmentu |
| `edits.json` | Mapa poprawek po ID segmentu | oryginalna transkrypcja nie jest nadpisywana |
| `exports/transcript.txt` | Tekst po poprawkach | UTF-8 |
| `exports/transcript.srt` | Napisy po poprawkach | globalny czas HH:MM:SS,mmm |
| `exports/transcript.vtt` | Napisy po poprawkach | globalny czas HH:MM:SS.mmm |
| `exports/transcript.json` | Przenośny wynik z poprawkami | oddzielny od surowych segmentów |

Obowiązują wersje `videonotes-project-v1`, `videonotes-transcript-v1`, `videonotes-edits-v1`. Segmenty mają jawne identyfikatory, ciągłe indeksy ukończonych fragmentów, czas w milisekundach i walidację długości. Cisza jest ukończonym fragmentem o zerowej liczbie segmentów. Przy błędzie ASR nie nadpisuje się poprzedniego checkpointu.

Wykrycie zmiany SHA-256 pliku lub modelu zatrzymuje wznowienie. Obliczenie SHA-256 wielogigabajtowego filmu wymaga czasu, ale działa ze stałą pamięcią. FFmpeg i whisper.cpp są uruchamiane bez powłoki systemowej; ich potencjalnie prywatne logi nie są przekazywane na stdout.

**Otwarte:** przenośny backup, relokacja pliku źródłowego, migracje v1→v2, odzyskiwanie starego pliku blokady po awarii, instalator Windows i końcowy kontrakt WWW. Nie oznaczać ich DONE na podstawie samego schematu.

## Integralność eksportu napisów — 07.11.2026

W SRT i VTT każdy segment pozostaje jednym cue: wielowierszowe poprawki są łączone w pojedynczy wiersz przez spacje, aby tekst nie wstrzykiwał pozornych znaczników czasu i nowych bloków napisów. W VTT znaki `&`, `<`, `>` są kodowane jako tekst, aby nie interpretować wpisanej transkrypcji jako składni WebVTT. Eksporty TXT/JSON zachowują oryginalne znaki nowej linii i tekst użytkownika. Testy syntetyczne obejmują oba eksportery (Python i WWW); nie zastępują testu rzeczywistych odtwarzaczy napisów.

## Jawne odzyskanie blokady po awarii (07.11.2026)

Po przerwanym działaniu procesu `.processing.lock` może pozostać na dysku. Bez usuwania jakichkolwiek plików projektu sprawdź:

```bash
python -m videonotes lock-status KATALOG_PROJEKTU
```

Stan `active` oznacza działający proces, `stale` potwierdzony brak procesu o danym PID, `unknown` niewystarczające uprawnienia/wynik, `invalid` nieznany format blokady, `missing` brak blokady. **Tylko dla `stale`** po kontroli, że poprzednia transkrypcja rzeczywiście się zakończyła, uruchom:

```bash
python -m videonotes lock-recover KATALOG_PROJEKTU --confirm
python -m videonotes resume KATALOG_PROJEKTU
```

Na Windows sprawdzanie obecności procesu korzysta z `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`, nigdy z potencjalnie destrukcyjnego `os.kill(pid,0)`. Dla aktywnych, nieznanych, uszkodzonych i zmienionych w trakcie kontroli blokad odmowa jest obowiązkowa. Odzyskiwanie nie kasuje żadnych zapisanych checkpointów, transkrypcji ani edycji. PID może zostać wykorzystany ponownie przez inny proces, dlatego w takiej sytuacji odzyskiwanie jest zachowawczo blokowane; test realnej awarii Windows nadal pozostaje otwarty.

## Wyłączność tworzenia projektu — 12.11.2026

Dwa równoczesne procesy tworzące projekt w tym samym katalogu mogły wcześniej przejść kontrolę pustego katalogu i nadpisać wzajemnie pliki `project.json`, `transcript.json` lub `edits.json`. Teraz przed sprawdzeniem pustego katalogu tworzone jest wyłączne `.creating.lock` w katalogu docelowym. Druga próba odmawia zapisu; ukończony projekt pozostaje niezmieniony. Po udanym utworzeniu trzech plików lub obsłużonym błędzie blokada jest zwalniana. Pusty katalog wskazany przez użytkownika nadal jest obsługiwany.

Jeżeli proces zostanie gwałtownie zakończony, plik `.creating.lock` może pozostać. **Nie usuwać go automatycznie ani nie nadpisywać częściowo zapisanych projektów**. Sprawdzić, czy poprzedni proces zakończył się i czy nie istnieją dane do uratowania. Jest to blokada tworzenia nowego projektu, oddzielna od `.processing.lock` używanej podczas transkrypcji; polecenie `lock-recover` jej nie dotyczy. Dowody testowe obejmują równoległe wywołania i awarię syntetyczną, ale nie stanowią testu fizycznej awarii Windows.
