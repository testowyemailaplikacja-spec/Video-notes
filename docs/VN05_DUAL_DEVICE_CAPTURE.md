# VN-05 — mikrofon plus opcjonalne drugie wejście DirectShow

Data: 2026-11-06. Prace wyłącznie w niezależnym repo Video-notes; bez zmian Constant_app, Netlify i Supabase.

## Zastosowanie

Program potrafi nagrywać wskazany mikrofon i opcjonalne drugie urządzenie audio Windows (np. Stereo Mix albo skonfigurowane urządzenie loopback). Oba wejścia muszą być widoczne w DirectShow. Nie każdy komputer udostępnia Stereo Mix. Aplikacja nie obchodzi uprawnień systemowych i nie aktywuje ukrytego przechwytywania.

Lista urządzeń:

    python -m videonotes record-devices

Nagrywanie dwóch wejść:

    python -m videonotes record-mic --device "Microphone USB" --system-device "Stereo Mix" --output C:\nagrania\sesja-001 --consent --consent-system

**Dwie osobne zgody są obowiązkowe**: --consent na mikrofon oraz --consent-system na drugie źródło. Samo wskazanie urządzenia bez zgody nie uruchomi FFmpeg. Bez drugiego źródła zachowano działanie samego mikrofonu. Dwa wejścia nie mogą mieć tej samej nazwy.

## GUI

W oknie nagrywania dostępne są pola Mikrofon oraz opcjonalne System audio. Wykryj pokazuje aktualną listę wejść DirectShow, a oddzielny checkbox potwierdza zgodę na system audio. Po tym użytkownik świadomie potwierdza rozpoczęcie. Zatrzymaj zamyka plik WAV.

## Technicznie

FFmpeg czyta dwa niezależne wejścia, stosuje resampling i miksowanie amix do PCM mono 16 kHz/16 bit. Materiał nadal jest dzielony co 2 godziny. Dziennik recording.json przechowuje informacje o zgodach, nie nazwy urządzeń. Wszystkie pliki pozostają lokalnie.

## Granice odbioru

**VN-05 pozostaje W_TRAKCIE.** Kod testowany przez atrapy FFmpeg nie dowodzi działania sprzętowego. Niezbędne są testy prawdziwych urządzeń i jakości miksowania, synchronizacji, dostępu Windows, odłączania mikrofonu, limitów miejsca i nagrań 2h. Na komputerach bez loopback potrzebny jest odrębny adapter albo konfiguracja urządzenia. Nie zmieniamy statusu na DONE bez tych dowodów.

## Dokładność diagnostyki sygnału między częściami (12.11.2026)

Raport `record-analyze` mierzy najdłuższą nieprzerwaną ciszę także wtedy, gdy zaczyna się w jednym pliku `part-XXXXX.wav`, a kończy w następnym. Wcześniej licznik resetował się na granicy plików, przez co np. 6 sekund ciągłej ciszy rozdzielonych na trzy części mogło wyglądać jak 2 sekundy. Poszczególne raporty części pozostają bez zmian, natomiast wynik całej sesji sumuje ciszę przechodzącą przez granicę i zawsze pozostaje tylko wskazówką o poziomie sygnału, nie dowodem, że głos został rozpoznany poprawnie. Po analizie ponownie sprawdzany jest dziennik oraz SHA-256 części WAV; jeżeli nagranie zmieniło się w trakcie pomiaru, wynik zostaje odrzucony. Próbki nagrań w testach są syntetyczne i nie stanowią odbioru dwóch fizycznych urządzeń DirectShow.
