# VN-07 — samodzielna przeglądarkowa przeglądarka transkrypcji (prototyp offline)

Data: 2026-11-06. Kod wyłącznie w repozytorium Video-notes. Nie jest jeszcze zintegrowany z Wiedora, Netlify, Supabase ani kontami.

## Uruchomienie

Otwórz lokalnie plik web/index.html w nowoczesnej przeglądarce Windows/macOS/Linux, bez serwera WWW, internetu, konta ani zależności npm. Wszystkie pliki JS i CSS znajdują się obok pliku HTML; nie pobieramy bibliotek z CDN.

Najpierw wyeksportuj transkrypcję desktopową:

    python -m videonotes export KATALOG_PROJEKTU

Następnie w lokalnej stronie wybierz KATALOG_PROJEKTU/exports/transcript.json. Obsługiwany jest wersjonowany format videonotes-export-v1. Nie wczytuj bezpośrednio wewnętrznego transcript.json z katalogu projektu; zawiera inną strukturę i nie obejmuje poprawek.

Interfejs przedstawia segmenty z czasami, pozwala przeszukiwać do 50 000 segmentów, ręcznie poprawiać wybrany tekst w pamięci strony i pobierać aktualny wynik w TXT, SRT, VTT lub JSON. Oryginalny plik nie jest modyfikowany. Wszelkie zmiany znikną po zamknięciu strony, jeśli użytkownik nie pobierze nowego eksportu.

## Bezpieczeństwo i prywatność

Przetwarzanie odbywa się w pamięci przeglądarki. Kod nie wykonuje żądań sieciowych, nie używa płatnych API, localStorage, synchronizacji i telemetrii. Nie przechowuje nagrań. Treść transkrypcji jest wyświetlana przez DOM textContent, nie innerHTML. Parser odrzuca nieznany schemat, uszkodzony JSON, duplikaty identyfikatorów, złe czasy, za długie segmenty i pliki przekraczające 20 MB. Poprawki są trzymane w słowniku bez prototypu i eksportowane dopiero po świadomym kliknięciu.

Niektóre przeglądarki ograniczają lokalny dostęp do innych zasobów dla stron file://. Dlatego korzystamy z klasycznych skryptów, a dane użytkownik wybiera przez standardowy input file; nie ma CORS importu ES modules ani fetch. Potrzebny odbiór fizyczny w Chrome, Edge i Firefox.

## Testy i granice

    node --check web/transcript-core.js
    node --check web/app.js
    node --test tests/web-core.test.cjs

Testy są dodane do GitHub Actions Linux/Windows. Potwierdzają walidację kontraktu, czasów, ochronę źródła, eksporty i obsługę złośliwego tekstu. Nie zastępują testów GUI przeglądarek, testów dostępności, wydajności dużych importów ani bezpieczeństwa integracji z portalem.

**VN-07 pozostaje W_TRAKCIE.** To działający lokalny interfejs odczytu/edycji istniejącego eksportu, ale bez ASR w przeglądarce, nagrywania na WWW, synchronizacji, wdrożenia do Wiedora i pełnego odbioru użytkownika. Dalsza publikacja na platformie wymaga osobnego zlecenia, testów hosta i wcześniejszych bramek KWN.
