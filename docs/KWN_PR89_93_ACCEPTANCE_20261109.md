# KWN — techniczny odbiór PR #89–93 i otwarte kryteria

Stan według zweryfikowanego `develop`: **09.11.2026 (Warszawa)**. Repozytorium: `testowyemailaplikacja-spec/Video-notes`. Nie modyfikowano `Constant_app`, Supabase, Netlify ani stabilnego `main`.

## Nowe wdrożenia i dowody

| PR | Wdrożono | Potwierdzone CI po ostatniej poprawce | Granica odbioru |
| --- | --- | --- | --- |
| [#89](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/89) | VN-03B: lokalne OCR slajdów OBS, SHA źródła, Tesseract i weryfikator schematu | [42535755811](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42535755811) realny FFmpeg+Tesseract na oryginalnym syntetycznym wideo; [42535755792](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42535755792) 5/5, [42535755821](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42535755821) Inno, [42535755828](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42535755828) DEV — 8/8 PASS | Żadnego testu rzeczywistych slajdów CCNA / fizycznego Windows |
| [#90](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/90) | VN-02/03: lokalny `llama.cpp` GGUF, ścisły JSON, cytowane szkice wymagające kontroli i eksport MD | [42536188092](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42536188092) 5/5, [42536188114](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42536188114) DEV, [42536188119](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42536188119) Inno — 7/7 PASS | Model LLM zastąpiono w testach atrapą; ID źródła nie dowodzi prawdziwości parafrazy |
| [#91](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/91) | VN-04: wszystkie gotowe WAV → istniejąca ścieżka checkpointów Whisper i eksport | [42536726970](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42536726970) 5/5, [42536727171](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42536727171) Inno, [42536726935](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42536726935) DEV — 7/7 PASS | Rzeczywisty FFmpeg na syntetycznym WAV, ale ASR jest atrapą; brak fizycznego mikrofonu |
| [#92](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/92) | VN-02/03: osobne GUI opcjonalnych OCR i szkiców semantycznych | [42537008193](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42537008193) 2/2 realne Tk Linux/hosted Windows, [42537008197](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42537008197) 5/5, [42537008206](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42537008206) DEV — 8/8 PASS | Brak testów lokalnego GGUF i oceny jakości człowieka |
| [#93](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/93) | VN-04: okno desktop do pełnej transkrypcji zakończonej sesji, z wyborem WAV/projektu, postępem i przerwaniem | [42537324810](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42537324810) 2/2 Tk, [42537324676](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42537324676) 5/5, [42537324689](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/42537324689) DEV — 8/8 PASS | Brak fizycznego Windows z DirectShow i sesji 2h |

**Razem: pięć scalonych PR i 38/38 potwierdzonych prac CI PASS**, przy czym to liczba zadań CI, a nie odrębnych testów jednostkowych lub ukończonych faz. Przed uzyskaniem zielonych wyników pojawiły się i zostały naprawione trzy usterki: ścieżka importu rzeczywistego smoke OCR, odczyt zmiennych Tk z wątku roboczego oraz kolejność preflight przy wyborze połączonego WAV. Zapisano wyłącznie **wyniki końcowych ponowień**.

## Aktualny status etapów

| Etap | Stan formalny | Co nadal wymaga realnego odbioru |
| --- | --- | --- |
| VN-00 | W TRAKCIE | Naturalny PL/EN ASR z ręczną referencją, WER/CER, RAM, licencje i fizyczny Windows |
| VN-01 | W TRAKCIE | Rzeczywisty OBS MP4/MKV + 2 h Whisper, przerwanie i restart offline na docelowym sprzęcie |
| VN-02 | W TRAKCIE | Rzeczywisty GGUF, ocena semantyczna i dokładność liczb, terminów oraz merytoryczny odbiór człowieka |
| VN-03 | W TRAKCIE | Autentyczne wykłady/CCNA, OCR slajdów, zgodność głosu z ekranem i ręczny odbiór jakości |
| VN-04 | W TRAKCIE | Mikrofon Windows USB/DirectShow, 2 h i awarie sprzętu; GUI i integracja CLI są już wdrożone |
| VN-05 | W TRAKCIE | Loopback sprzętowy, synchronizacja mik+system, podłączenie/odłączenie i zgody |
| VN-06 | W TRAKCIE | Legalne modele/biblioteki, kompletna instalacja offline na czystym Windows, AV/SmartScreen, podpis/polityka |
| VN-07 | W TRAKCIE | Odrębny moduł beta Wiedora, autoryzowana integracja, dostępność i test portalu |
| VN-08 | PLANOWANE | Opcjonalny Android/iOS, decyzja po stabilizacji Windows |

**Suma: 0/9 DONE, 8/9 W TRAKCIE, 1/9 PLANOWANE**. Uruchomione modele na syntetycznej mowie lub prawdziwy Tesseract na sztucznym obrazie nie zastępują odbioru na realnych wykładach. Nie przenosimy tych wyników automatycznie do historycznego rejestru KWN 189 kryteriów w `Constant_app`.

## Procedura pozostałych bramek

Dokładny, wcześniej przygotowany zbiór testów HW/ASR/NOTE/MIC/MIX/WEB/PKG/HOST/MOB i wymagana forma dowodów znajduje się w [VN_HARDWARE_ACCEPTANCE_20261107.md](VN_HARDWARE_ACCEPTANCE_20261107.md). Do przeprowadzenia w bezpiecznym fizycznym środowisku: [REAL_ASR_LAB.md](REAL_ASR_LAB.md), [VN_SEMANTIC_DRAFT.md](VN_SEMANTIC_DRAFT.md), [VN03B_SLIDE_OCR.md](VN03B_SLIDE_OCR.md), [VN04_RECORD_TO_ASR.md](VN04_RECORD_TO_ASR.md), [VN06_PRIVATE_INSTALLER.md](VN06_PRIVATE_INSTALLER.md).

Nie umieszczać w publicznym repo nagrań użytkowników, transkrypcji, lokalnych modeli ani ścieżek prywatnych. Odbiór przez człowieka i legalność dystrybucji wymagają rzeczywistych dowodów. Produkcyjna stabilna publikacja, merge do `main` oraz integracja portalu **nie są** skutkiem tego technicznego odbioru.
