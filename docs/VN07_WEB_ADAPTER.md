# VN-07 — samodzielna przeglądarkowa przeglądarka transkrypcji (prototyp offline)

Data: 2026-11-06. Kod wyłącznie w repozytorium Video-notes. Nie jest jeszcze zintegrowany z Wiedora, Netlify, Supabase ani kontami.

## Uruchomienie

Otwórz lokalnie plik web/index.html w nowoczesnej przeglądarce Windows/macOS/Linux, bez serwera WWW, internetu, konta ani zależności npm. Wszystkie pliki JS i CSS znajdują się obok pliku HTML; nie pobieramy bibliotek z CDN.

Najpierw wyeksportuj transkrypcję desktopową:

    python -m videonotes export KATALOG_PROJEKTU

Następnie w lokalnej stronie wybierz KATALOG_PROJEKTU/exports/transcript.json. Obsługiwany jest wersjonowany format videonotes-export-v1. Nie wczytuj bezpośrednio wewnętrznego transcript.json z katalogu projektu; zawiera inną strukturę i nie obejmuje poprawek.

Interfejs przedstawia segmenty z czasami, pozwala przeszukiwać do 50 000 segmentów, ręcznie poprawiać wybrany tekst w pamięci strony, przywracać wybrany segment do wersji z importu i pobierać aktualny wynik w TXT, SRT, VTT lub JSON. Oryginalny plik nie jest modyfikowany. Wszelkie zmiany znikną po zamknięciu strony, jeśli użytkownik nie pobierze nowego eksportu.

## Bezpieczeństwo i prywatność

Przetwarzanie odbywa się w pamięci przeglądarki. Kod nie wykonuje żądań sieciowych, nie używa płatnych API, localStorage, synchronizacji i telemetrii. Nie przechowuje nagrań. Treść transkrypcji jest wyświetlana przez DOM textContent, nie innerHTML. Parser odrzuca nieznany schemat, uszkodzony JSON, duplikaty identyfikatorów, złe czasy, za długie segmenty i pliki przekraczające 20 MB. Poprawki są trzymane w słowniku bez prototypu i eksportowane dopiero po świadomym kliknięciu.

Niektóre przeglądarki ograniczają lokalny dostęp do innych zasobów dla stron file://. Dlatego korzystamy z klasycznych skryptów, a dane użytkownik wybiera przez standardowy input file; nie ma CORS importu ES modules ani fetch. Potrzebny odbiór fizyczny w Chrome, Edge i Firefox.

## Testy i granice

    node --check web/transcript-core.js
    node --check web/app.js
    node --test tests/web-core.test.cjs tests/web-controller.test.cjs

Testy są dodane do GitHub Actions Linux/Windows. Potwierdzają walidację kontraktu, czasów, ochronę źródła, eksporty i obsługę złośliwego tekstu. Nie zastępują testów GUI przeglądarek, testów dostępności, wydajności dużych importów ani bezpieczeństwa integracji z portalem.

**VN-07 pozostaje W_TRAKCIE.** To działający lokalny interfejs odczytu/edycji istniejącego eksportu, ale bez ASR w przeglądarce, nagrywania na WWW, synchronizacji, wdrożenia do Wiedora i pełnego odbioru użytkownika. Dalsza publikacja na platformie wymaga osobnego zlecenia, testów hosta i wcześniejszych bramek KWN.

## Aktualizacja 07.11.2026 — eksport i ochrona zmian

* Przywrócenie wybranego segmentu do stanu z importowanego JSON; przy niezapisanym tekście wymagane jest potwierdzenie odrzucenia zmian. Nie odzyskuje surowego ASR z programu Windows.
* Eksport tworzy tylko żądany format TXT/SRT/VTT/JSON, aby nie zużywać pamięci na pozostałe trzy wyniki. API `renderExports` pozostaje dla kompatybilności.
* CI Linux i Windows uruchamia także `tests/web-controller.test.cjs`: testy niezapisanych zmian, wyścigów importu, przywracania tekstu.
* Testy są symulacją DOM, nie odbiorem Chrome/Edge/Firefox, dostępności ani integracji hosta; VN-07 nadal W_TRAKCIE.

## Integralność eksportu napisów — 07.11.2026

W SRT i VTT każdy segment pozostaje jednym cue: wielowierszowe poprawki są łączone w pojedynczy wiersz przez spacje, aby tekst nie wstrzykiwał pozornych znaczników czasu i nowych bloków napisów. W VTT znaki `&`, `<`, `>` są kodowane jako tekst, aby nie interpretować wpisanej transkrypcji jako składni WebVTT. Eksporty TXT/JSON zachowują oryginalne znaki nowej linii i tekst użytkownika. Testy syntetyczne obejmują oba eksportery (Python i WWW); nie zastępują testu rzeczywistych odtwarzaczy napisów.

## Poprawki bezpieczeństwa edycji (07.11.2026)

* Jeśli zawartość edytora różni się od zapisanej w pamięci poprawki, pobieranie TXT/SRT/VTT/JSON jest wstrzymywane. Najpierw trzeba kliknąć „Zachowaj poprawkę”, aby nie pobrać pozornie poprawnego pliku bez ostatnich zmian. Nie dochodzi do automatycznego nadpisania szkicu.
* Gdy import JSON trwa asynchronicznie, a użytkownik w międzyczasie dopisze lub zapisze poprawki, aplikacja ponownie wymaga świadomego potwierdzenia przed zastąpieniem dokumentu. Odrzucenie zachowuje dotychczasowy dokument i szkic.
* Syntetyczne testy kontrolera sprawdzają blokadę eksportu i konflikt importu; nadal potrzebne są testy rzeczywistych przeglądarek, klawiatury i czytnika ekranu. Etap VN-07 pozostaje W_TRAKCIE.
