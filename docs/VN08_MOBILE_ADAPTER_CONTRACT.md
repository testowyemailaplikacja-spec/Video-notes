# VN-08 — granica adapterów mobilnych (przygotowanie, nie wdrożenie)

Data: 12.11.2026. **VN-08 pozostaje PLANOWANE.** Bez zgody na budowę pełnej aplikacji mobilnej. Żaden test w tym dokumencie nie dowodzi nagrywania na fizycznym Androidzie lub iOS.

## Wspólna warstwa danych

Dla przyszłych klientów Android/iOS jedynym początkowym kontraktem wymiany jest istniejący `videonotes-export-v1` z desktop/WWW. Moduł `videonotes/mobile_contract.py` dostarcza odczyt i walidację bez sieci, w zgodzie z ograniczeniami adaptera WWW: 20 MiB danych JSON, do 50 000 segmentów, identyfikatory ASCII, czasy w ms w zakresie 24 h, rozmiar tekstu liczony w UTF-16 (jak JS), brak duplikatów ID i kluczy JSON, prawidłowy UTF-8. Walidator zwraca osobną kopię: nie zapisuje projektu ani nie ingeruje w surowy ASR. Export częściowy (`complete=false`) jest dopuszczalny.

Dzięki temu w przyszłości możliwe będzie odczytanie lokalnie wyeksportowanej transkrypcji i poprawianie jej na urządzeniu, bez zakładania, że urządzenie uruchomi desktopowego Whisper. Powrót poprawek na desktop wymaga osobnego, już istniejącego kontraktu `videonotes-web-corrections-v1` i ochrony konfliktów, a nie zastąpienia oryginalnego `transcript.json`.

## Interfejs przyszłej aplikacji

- `FilePicker`: świadomy wybór lokalnego pliku i jawnie udzielony dostęp do niego.
- `TranscriptReader`: walidacja eksportu v1, czytanie i nawigacja po segmentach bez sieci.
- `CorrectionsWriter`: osobny plik poprawek z powiązaniem ID/czas/tekst pierwotny, nigdy automatyczne nadpisanie źródła.
- `Recorder`: osobny adapter natywny, który musi raportować realną dostępność urządzeń, uprawnienia, sesję i miejsca na dysku. Nie uruchamiać w tle bez jawnej decyzji użytkownika.
- `ASRProvider`: opcjonalny lokalny silnik o znanych licencjach i wymaganiach urządzenia; `unavailable` jest poprawnym wynikiem. Żadnego automatycznego wysyłania nagrania do API.
- `CheckpointStore`: atomowe zapisy części, odtwarzanie po awarii, identyfikatory i SHA-256. Wymaga testów systemowych, nie tylko schematu JSON.

## Platformy i ograniczenia

Android: nagrywanie mikrofonu i przechwytywanie audio innych aplikacji to odrębne mechanizmy wymagające odpowiednich zgód i ograniczeń wersji Androida. Nie zakładać dostępności system audio ani nie obchodzić odmowy innych aplikacji. Długie nagrywanie i działanie w tle wymagają osobnej strategii foreground service i testów na konkretnych urządzeniach.

iOS: dostęp do mikrofonu wymaga zgody, a przechwytywanie ekranu/audio i działanie w tle podlegają ograniczeniom platformy. Nie zakładać ogólnego loopback. Zależnie od dozwolonego scenariusza należy zweryfikować AVAudioSession, ReplayKit oraz politykę publikacji.

**Decyzja produktowa przed implementacją:** czy mobilny MVP ma być tylko czytnikiem/edytorem eksportów, czy obejmować nagrywanie mikrofonu i lokalne ASR; osobno wybrać minimalne OS i budżet pamięci/modelu. Bez tego nie tworzyć natywnych uprawnień ani publikacji w sklepach.

## Testy i odbiór

Automatyczne `python -m unittest tests.test_mobile_contract -v` obejmują odczyt, kopię bez mutacji, Unicode, powtórzenia mowy, odrzucanie duplikatów kluczy, błędnych czasów, przekroczenia limitu, niepoprawnego UTF-8 i segmentów. Przydatne późniejsze testy kontraktowe: wspólne przykłady Python/JS/Kotlin/Swift, aktualizacja v1→v2, restart z checkpointu, brak uprawnień, brak pamięci, brak sieci. **Testy emulatorów i fizycznych Android/iOS, mikrofonu, loopback i sklepu nie zostały wykonane.**
