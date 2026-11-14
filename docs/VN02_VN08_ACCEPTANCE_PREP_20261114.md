# KWN — przygotowanie VN-02-01 i VN-08-02 (14.11.2026)

Repozytorium robocze: Video-notes, gałąź develop po zatwierdzeniu CI.

## VN-02-01 — realny lokalny model GGUF

Moduł videonotes/gguf_probe.py sprawdza magię, wersję GGUF v2/v3 i wybrane granice nagłówka. To nie jest sprawdzenie wszystkich tensorów, licencji, prawdziwości informacji ani potwierdzenie zgodności z llama.cpp. Żaden plik modelu nie jest automatycznie pobierany.

Po legalnym pozyskaniu modelu właściciel może uruchomić z katalogu repozytorium:

~~~powershell
python scripts/semantic_gguf_acceptance.py --project "C:\KWN\projekt" --model "C:\KWN\model.gguf" --llama-cli "C:\Programy\llama-cli.exe" --out-dir "C:\KWN\prywatne-wyniki\proba-01"
~~~

Skrypt uruchamia rzeczywisty lokalny proces llama-cli poprzez istniejące semantic-draft, sprawdza stabilne ID cytatów, czasy, związanie ze źródłem i zapisuje report.json (czas; opcjonalnie próbkowany RAM/CPU przez psutil). private-draft.json zawiera cytaty z transkrypcji: nigdy nie wysyłać tego katalogu do GitHub. Po przerwaniu i ponownej próbie wybrać nowy katalog, by zachować wcześniejsze wyniki.

Raport nie uznaje treści za zgodną z rzeczywistym nagraniem. Wymagane są nadal: licencjonowany model, test naturalnej mowy, poprawność liczb i definicji na źródle, ręczny review/approve/reject, pełny sprzętowy pomiar RAM/CPU i sprawdzenie po restarcie. Atrapom w testach jednostkowych nie przyznawać statusu odbioru. Brak takiego dowodu oznacza pozostawienie VN-02-01 bez DONE.

## VN-08-02 — niezależny kontrakt mobilny

Pythonowy videonotes/mobile_import.py to przygotowanie granicy importu, nie gotowa aplikacja Android ani iOS. Odczytuje lokalny plik w porcjach do 64 KiB, do 20 MiB łącznie, sprawdza podstawowe znaczniki podmiany źródła, liczy SHA-256 i wymaga poprawnego kontraktu videonotes-export-v1. Zwraca odłączoną kopię danych. Nie zmienia surowej transkrypcji, nie tworzy konta i nie łączy się z siecią. Niepoprawny i przerwany import nie zapisuje częściowych wyników. Na obecnym etapie po awarii należy ponownie wybrać plik, bo wznawianie od offsetu po restarcie nie jest implementowane.

Proponowany zakres do decyzji VN-08-01:
A — tylko prywatny czytnik i korektor lokalnych eksportów; najmniej zależności i ryzyk, rekomendowane MVP.
B — zakres A plus natywne nagrywanie mikrofonu wymagające zgód i badania działania w tle.
C — zakres B plus lokalne ASR na urządzeniu z osobną analizą RAM, baterii, modeli i licencji.

Do pełnej specyfikacji potrzebne: decyzja A/B/C, wersje Android/iOS, minimalny budżet pamięci, testy rzeczywistych urządzeń, polityka trwałych checkpointów, osobne import/eksport poprawek i odbiór uprawnień. Nie włączono żadnych niezatwierdzonych funkcji mobilnych.


### Lokalny podgląd paczki poprawek z pliku (VN-08-02)

`videonotes.mobile_import.import_mobile_corrections_file(document, path)` czyta lokalny
plik poprawki bez jej zastosowania. Sprawdza, czy plik jest regularny,
nie jest symlinkiem, ma nie więcej niż 20 MiB, nie zmienił się podczas odczytu,
a następnie wymaga pełnej zgodności ID projektu, źródłowych ID, czasów i tekstu
przed poprawkami. Zwraca odłączone `changes`, `source_sha256`,
`source_bytes` i `read_only=True`. Digest odpowiada dokładnie bajtom,
które zostały zwalidowane. Nie tworzy mobilnej aplikacji i nie zapisuje
zmian do projektu. Przykład integracji (wyłącznie pliki własne użytkownika):

~~~python
from pathlib import Path
from videonotes.mobile_import import import_portable_file, import_mobile_corrections_file
source = import_portable_file(Path("transcript.json"))
preview = import_mobile_corrections_file(source["document"], Path("corrections.json"))
# Przed zastosowaniem zmian wymagana jest oddzielna, świadoma operacja
# desktopowa z walidacją aktualnego stanu projektu.
~~~

Testy syntetyczne obejmują poprawny podgląd, SHA-256, błędne lub zduplikowane
pola JSON, limit rozmiaru, symlinki i zmianę zawartości podczas odczytu.
To przygotowanie kontraktu, nie odbiór rzeczywistego Androida/iOS.

### Bezpieczny lokalny eksport poprawek do pliku

`videonotes.mobile_import.export_mobile_corrections_file(document, edits, destination)`
tworzy nową paczkę JSON w istniejącym lokalnym katalogu. Nie nadpisuje
poprzedniej paczki ani istniejących plików: przygotowuje i synchronizuje
plik tymczasowy, a następnie publikuje go atomowym hard linkiem. Na nośniku
bez obsługi hard linków zgłasza błąd zamiast zostawić plik częściowy.
Odrzuca dowiązania katalogów na ścieżce docelowej oraz nazwy inne niż `.json`.

~~~python
from pathlib import Path
from videonotes.mobile_import import export_mobile_corrections_file, import_mobile_corrections_file
report = export_mobile_corrections_file(source["document"], {"s0": "Poprawiona wypowiedź"}, Path("corrections-new.json"))
preview = import_mobile_corrections_file(source["document"], Path("corrections-new.json"))
assert report["patch_sha256"] == preview["source_sha256"]
~~~

Te funkcje nie aktualizują żadnych edycji projektu; podgląd służy do
świadomego przekazania później do obsługi desktopowej. Testy obejmują
roundtrip, integralność SHA, odmowę nadpisania, niepowodzenie publikacji
i symulację równoległego utworzenia pliku. Nie jest to test fizycznego
urządzenia, aktualizacji mobilnego pliku przez system Android/iOS ani
gwarancja trwałości na nagły zanik zasilania.

## Testy automatyczne

~~~sh
python -m unittest tests.test_gguf_probe tests.test_mobile_import tests.test_mobile_contract tests.test_semantic_draft -v
python -m unittest discover -s tests -v
node --test tests/web-mobile-contract.test.cjs
~~~

Testy syntetyczne w CI potwierdzają wyłącznie działanie kodu oraz zgodność kontraktu. Nie zastępują testów rzeczywistego modelu, licencjonowanego nagrania, fizycznego Windows, Androida czy iOS.

## Rozgraniczenie zasobów

Zwykły ChatGPT / CI: poprawki kodu, testy bez modelu, weryfikacja kontraktu, raport techniczny i przygotowanie scenariuszy.

Work / tester: tylko brakujący odbiór realnego GGUF i naturalnego audio, fizyczne Windows/Android/iOS oraz ręczne sprawdzenie twierdzeń. Decyzja o zakresie aplikacji i licencjach należy do właściciela/osoby upoważnionej.

## Mobilny obieg poprawek (niezależny od natywnych API)

`videonotes/mobile_corrections.py` zawiera `render_mobile_corrections(document, edits) -> bytes` i `parse_mobile_corrections(document, payload) -> dict`. Korzysta z istniejącego odwracalnego `videonotes-web-corrections-v1`; sprawdza oryginalny tekst (`before`), ID segmentu i czasy, limit 20 MiB, JSON i kompletność wszystkich zmian przed ich zwróceniem. Jest to warstwa pamięciowa: nie zapisuje projektu ani nie nakłada zmian bez decyzji użytkownika. Import eksportu i stworzenie paczki poprawek można testować bez urządzeń mobilnych; konkretna aplikacja Android/iOS nadal zależy od VN-08-01.

Test `tests/test_mobile_corrections.py` kontroluje źródła, brak zapisu, niejednoznaczne pola i konflikty; `tests/web-mobile-contract.test.cjs` sprawdza dwustronne przyjęcie paczki przez walidator Python i faktyczny kod JS przeglądarki. Nadal trzeba zweryfikować urządzenia i zatwierdzić zakres mobilnego MVP.
