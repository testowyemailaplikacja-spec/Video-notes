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
