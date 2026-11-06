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
