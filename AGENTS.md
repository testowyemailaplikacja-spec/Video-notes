# Zasady pracy w repozytorium Video Notes

1. **Video Notes to samodzielna aplikacja transkrypcji i opracowywania notatek.** Wzorcem jest `apps/notatki/` Wiedora. **Konwerter plików to osobny projekt**, nie realizujemy jego funkcji w Video Notes.
2. Hierarchia: aktualne polecenie użytkownika → ten plik → `docs/PLAN_ROZWOJU_VIDEO_NOTES.md` → rzeczywisty kod/testy.
3. `reference/wiedora-notatki/` zawiera **wyłącznie migawkę źródeł do analizy**; nie traktuj jej jako działającego programu Windows. Nowy silnik i UI implementuj poza `reference/`.
4. Kolejność: VN-00 fundamenty → VN-01 OBS/transkrypcja → VN-02 notatki podstawowe → VN-03 zaawansowane → VN-04 mikrofon → VN-05 inne źródła → VN-06 wydanie Windows → VN-07 integracja Wiedora → VN-08 mobilne.
5. Program Windows: offline po pełnej instalacji, bez obowiązkowego konta, płatnego API i automatycznej wysyłki materiałów. Pliki, transkrypcje i notatki zostają lokalne.
6. Wydziel silnik ASR, import/OBS, sesje nagrywania, modele notatek, zapis lokalny, eksport i GUI. Przygotuj stabilny kontrakt danych dla przyszłego adaptera WWW.
7. W istniejącym repo `Constant_app`, Supabase, Netlify i danych użytkowników **niczego nie zmieniaj** bez osobnego zadania.
8. Nie deklaruj przetestowania ani ukończenia funkcji bez wyników testów. Przy zmianie kodu sprawdź błędy, regresję i realne scenariusze, a przy wydaniu sprzęt Windows.
9. Nie przenoś do publicznego repo sekretów, danych użytkowników ani prywatnych konfiguracji. Pilnuj licencji modeli i zależności.
10. Nie nadpisuj cudzej równoległej pracy. Przed aktualizacją pobierz najnowszy plik i zweryfikuj stan gałęzi.
