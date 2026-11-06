# VN-03 — konspekt źródłowy (częściowa implementacja)

Data: 2026-11-06. Pierwszy moduł konspektu wielopoziomowego w repo Video-notes. Bez zmian w Constant_app, Supabase i Netlify.

## Uruchomienie

    python -m videonotes advanced-notes KATALOG_PROJEKTU --template lecture --detail standard --section-minutes 10

Dostępne szablony: lecture, tutorial, meeting, study. Szczegółowość: brief, standard, full. Wyniki: exports/notes-advanced.md oraz exports/notes-advanced.json. Wypowiedzi są cytowane z aktualnie poprawionej transkrypcji razem z identyfikatorem segmentu i czasem. Pole source_sha256 wiąże wynik z treścią transkrypcji. Interfejs Tkinter udostępnia podgląd tylko do odczytu.

## Granice funkcjonalne

To deterministyczny konspekt ekstrakcyjny dzielony według czasu, a NIE semantyczny model językowy, streszczenie, analiza slajdów ani weryfikacja faktów. Etykiety możliwej definicji, przykładu i pytania są tylko podpowiedziami heurystycznymi. Nie są dowodem pewności ASR. Nie dodajemy faktów, definicji ani wyjaśnień spoza źródła. Wybrane cytaty nie obejmują każdej wypowiedzi w dłuższym nagraniu.

Prywatność: pełna praca offline, brak płatnych API, kont, telemetrii i nowych zależności. Eksport jest przebudowywany z aktualnych korekt; oryginalne project.json, transcript.json, edits.json, notes.json oraz ręczne poprawki pozostają nietknięte. Cytaty w Markdown są blokami kodu, żeby nie interpretuwać HTML i linków z transkrypcji.

## Odbiór

Testy kodu: tests/test_advanced_notes.py, kompletna regresja Linux i podzbiór Windows w CI. Nadal potrzebne: rzeczywiste wykłady, poprawna segmentacja semantyczna, definicje i przykłady ocenione przez człowieka, spójność wielogodzinnych opracowań, testy rozdziałów materiałów CCNA, oddzielny OCR, DOCX/PDF i weryfikacja działania na fizycznym Windows. VN-03 pozostaje W_TRAKCIE, nie DONE.
