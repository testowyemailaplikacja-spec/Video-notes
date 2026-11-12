# KWN — odbiór techniczny pięciu pakietów PR #138–142 (12.11.2026)

**Repo:** `testowyemailaplikacja-spec/Video-notes`, **gałąź:** `develop`. Zmiany zostały faktycznie scalone i przetestowane. Jest to **odbiór poprawek kodu**, a nie całych etapów VN.

| Zakres | PR i commit squash do develop | Co zmieniono i udowodniono | Końcowe CI na finalnym SHA |
|---|---|---|---|
| VN-03B OCR | [#138](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/138), `03fcaa76b1633c06776c43ba408a8901bb324e42` | OCR sprawdza SHA-256 klatki **ponownie po odczycie Tesseract**. Zmiana klatki w trakcie odczytu blokuje nieaktualny raport; test deterministycznie mutuje klatkę po pierwszym hashowaniu. | **8/8 PASS**: [GitHub Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43224289419) |
| VN-03 przewodnik do nauki | [#139](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/139), `5fafe00939e07aa578e475f50f1ef2dc71cefc0d` | Zmiana transkrypcji/poprawek podczas generowania Markdown lub Word/PDF blokuje publikację starego przewodnika, z zachowaniem wcześniejszych plików. | **11/11 PASS**: [GitHub Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43224569402) |
| VN-02 szkic AI | [#140](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/140), `4d4e2a081f0bf5eb4e3bb48a7c6cc22d3c3283bb` | Eksport niezatwierdzonego szkicu Markdown sprawdza SHA-256 oraz zgodność ponownie zweryfikowanego źródła i **dokładnie renderowanej treści**. Test zmienia JSON na dysku i podstawia inne twierdzenie w samym odczycie. | **7/7 PASS**: [GitHub Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43225135905) |
| VN-06 przywracanie źródeł | [#141](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/141), `eebdab93038f6283b393ada54f976a09d0fdeb64` | Po FFprobe ponownie weryfikuje SHA-256 lokalnych mediów i modelu oraz pierwotny stan odtworzonego projektu, zanim zapisze nowe ścieżki. Testy: zmiana tego samego rozmiaru źródła/modelu i ustawień projektu. | **7/7 PASS**: [GitHub Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43225563343) |
| VN-04 zgody na nagrywanie | [#142](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/142), `3cc03856c8eb92ae639bd33eb699099a26d962b7` | Po przygotowaniu WAV, **przed utworzeniem projektu transkrypcji**, porównuje cały dziennik nagrania ze stanem przy rozpoczęciu. Cofnięcie zgody na mikrofon albo drugie źródło audio blokuje nowy projekt. | **7/7 PASS**: [GitHub Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43225950160) |

Łącznie na końcowych commitach head tych pięciu PR: **40/40 hostowanych zadań GitHub Actions PASS**. Są to zadania CI, a nie 40 kryteriów masterplanu. Testy obejmowały własne dane syntetyczne, Python Linux/Windows, wybrane rzeczywiste biblioteki/FFmpeg, browser smoke, GUI w hostowanych VM oraz w pakiecie VN-03B również testy ffmpeg/whisper.cpp na syntetycznych próbkach. Nie użyto prywatnych nagrań użytkownika.

## Ograniczenia i dalsze bramki

Rejestr `VN_STATUS.json` zachowuje: **0/9 etapów DONE, 8 W_TRAKCIE, 1 PLANOWANE**. Rejestr 37 mikrozadań: **2 DONE, 1 IN_PROGRESS, 34 TODO**. To nie stoi w sprzeczności z ukończeniem pięciu pakietów kodu — formalne mikrozadania wymagają osobnych kryteriów odbioru.

Nadal wymagane: naturalna mowa PL/EN + legalne próbki i ręczna referencja do WER/CER, prawdziwy lokalny GGUF i ocena faktów, fizyczny Windows z długimi nagraniami, mikrofonem/loopback i wymuszonym restartem, weryfikacja instalatora/licencji/AV oraz niezależny odbiór beta Wiedora. Ponowne odczyty i hashe ograniczają typowe wyścigi; nie są globalną transakcją wobec dowolnego zewnętrznego procesu, który zmienia źródła po końcowej kontroli.

Nie zmieniano `testowyemailaplikacja-spec/Constant_app`, Netlify, Supabase, produkcyjnego `main` ani blokady testowania KWN BETA. Nie publikowano prywatnych danych, legalnych modeli ani nagrań. Następny pakiet powinien zaczynać od aktualnego `develop` i sprawdzać `AGENTS.md`, plan i rejestr.
