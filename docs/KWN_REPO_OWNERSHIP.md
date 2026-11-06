# KWN / Video Notes — zasada jednego repozytorium

**Potwierdzenie właściciela 06.11.2026:** `testowyemailaplikacja-spec/Video-notes` jest właściwym repozytorium roboczym Konwertera Notatek (KWN). Rozwój i testy funkcjonalne prowadzić tylko tutaj. Istniejąca beta na portalu Wiedora `develop` może pozostać widoczna, ale nie jest bieżącym źródłem kodu programu.

**Video-notes / develop**: transkrypcja, edycja, notatki, Windows, ASR, modele, adaptery, testy i PR-y. **Video-notes / main**: stabilny kod. **Constant_app / develop**: dopiero większe zatwierdzone pakiety, testy pasywne portalu (linki, izolacja, bezpieczeństwo), zbiorcza publikacja Netlify. **Constant_app / main**: bez automatycznego wydania.

**Dwa plany mają odrębny status.** Historyczny rejestr w `Constant_app` liczył 189 kryteriów / 22 etapy, a `Video-notes` ma VN-00–VN-08. Nie łączyć ich liczników automatycznie i nie przenosić statusów DONE bez dowodów dla właściwego kodu. Konwerter Plików PDF/DOCX to oddzielny program.

**Status 06.11.2026:** PR #1 scalony do develop; prototyp OBS/FFmpeg → lokalny adapter ASR → checkpointy → eksport i wstępny GUI. Lokalne 19/19 testów PASS, GitHub Actions Linux/Windows PASS na dostępnych testach. Brak jeszcze prawdziwego testu modelu PL, pełnej instalacji Windows offline i formalnego zamknięcia VN-00/VN-01. Patrz `docs/VN00_IMPLEMENTATION.md`.
