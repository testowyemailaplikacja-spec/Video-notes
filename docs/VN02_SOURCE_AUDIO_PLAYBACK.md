# VN-02 — ręczny odsłuch oryginalnego fragmentu transkrypcji

Przycisk **„Odtwórz zaznaczony fragment z nagrania”** w desktopowym edytorze uruchamia na żądanie lokalny odsłuch, bez wysyłania materiałów, zmiany ASR ani utraty niezapisanych poprawek. Działa również po przejściu do źródła przez klikalny cytat z notatki.

Wymagane są zainstalowane lokalnie **FFmpeg** i **FFplay** (programy użytkownika, nie stanowią automatycznie składnika wydania). Projekt musi wskazywać oryginalny niezmieniony plik OBS/audio. Przed odtworzeniem program weryfikuje rozmiar i SHA-256, wybiera dokładnie indeks ścieżki audio zapisany w `project.json`, przygotowuje krótki tymczasowy WAV, a następnie uruchamia lokalny FFplay w trybie audio. Plik tymczasowy jest usuwany po zakończeniu lub błędzie. CLI:

```powershell
python -m videonotes play-source C:\Notatki\projekt --segment c0000000-s00001 --seconds 15 --ffmpeg ffmpeg --ffplay ffplay
```

Odtwarzanie trwa maksymalnie 30 sekund (domyślnie 15), z maksymalnie sekundą poprzedzającą początek segmentu. FFplay jest uruchamiany z `shell=False`, bez zapisu treści do logu. Jeśli użytkownik nie ma urządzenia audio albo FFplay, pojawia się komunikat zamiast potwierdzenia sukcesu. Odsłuch wymaga osobnego działania użytkownika. Nie jest synchronizacją obrazu ze slajdami, nie potwierdza poprawności ASR i nie zastępuje odbioru jakościowego wykładu na fizycznym Windows.

## Ochrona odsłuchu przed nieaktualnym timecode (12.11.2026)

Przy odsłuchu fragmentu transkrypcji lokalny FFmpeg może potrzebować dłuższej chwili na pobranie próbek z dużego pliku OBS. Przed uruchomieniem FFplay aplikacja ponownie sprawdza **cały kontrakt projektu i transkrypcji**, oprócz już wykonywanego sprawdzenia SHA-256 nagrania. Jeżeli w tym czasie zmieniły się identyfikatory, czasy, segmenty lub ustawienia projektu, nie odtwarza pliku na podstawie nieaktualnego wyboru. Dwa testy syntetycznie modyfikują transkrypcję lub projekt podczas przygotowania lokalnego WAV i potwierdzają brak uruchomienia odtwarzacza. Nie zastępuje to rzeczywistego odsłuchu użytkownika ani oceny jakości rozpoznawania mowy.
