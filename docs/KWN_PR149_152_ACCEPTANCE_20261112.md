# KWN — odbiór techniczny PR #149–152 (12.11.2026)

Źródło: `testowyemailaplikacja-spec/Video-notes`, docelowa gałąź `develop`. Zmiany są **scalone do źródłowego repo**. Ta strona rejestruje *ukończone pakiety kodu*, a nie całościowy odbiór etapów VN.

| Etap | PR / merge commit | Zmiana faktyczna | Końcowe CI |
|---|---|---|---|
| VN-00 | [#149](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/149), `3021aa09fc4be3b681e5613bcb78b55035e33502` | Tekstowy benchmark WER/CER publikuje raport tylko do nowego .json, nie nadpisuje ani wzorca, ani raportu równoległego pomiaru. Po porównaniu ponownie sprawdza SHA-256 każdego TXT. | **7/7 PASS**, [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43259741932) |
| VN-07 | [#150](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/150), `1636a99a13fa952574259ded4868121ccb885a8a` | Import poprawek WWW odrzuca zduplikowane nazwy pól JSON, symlink i pliki ponad 20 MB; przed zastosowaniem sprawdza hash pliku poprawek i dokładny, aktualny projekt/transkrypcję/edits. | **7/7 PASS**, [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43260117138) |
| VN-02 | [#151](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/151), `0c6a55698c5675412a11ab412e3ac5a48d5696fe` | Eksport notatki podstawowej TXT, Markdown i DOCX powtarza walidację notatek i ręcznych poprawek po renderowaniu, przed publikacją. Edycja w trakcie renderowania zachowuje wcześniej zaakceptowane dokumenty. | **10/10 PASS**, [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43260557802) |
| VN-03 | [#152](https://github.com/testowyemailaplikacja-spec/Video-notes/pull/152), `96a40a42a4b9b08a4f7b835c9eb8b4c0c29b4962` | Indeks OCR–mowa wybiera deterministycznie najbliższy segment o tym samym znaczniku czasu według leksykalnego ID; test obejmuje odwrócone wpisy i losową referencję pełnego przeglądu. | **7/7 PASS**, [Actions](https://github.com/testowyemailaplikacja-spec/Video-notes/actions/runs/43261060393) |

**Łącznie: 31/31 końcowych zadań GitHub CI PASS na finalnych head SHA tych czterech PR.** Są to zadania CI, nie 31 zadań planu. Wykonano syntetyczne testy regresji, testy Python na Windows i Linux, stosowne przeglądarkowe smoke tests i hostowane testy GUI. Nie przeprowadzono pełnego testu na fizycznym komputerze Windows użytkownika.

## Istotne ograniczenia

Rejestr `docs/VN_STATUS.json` nadal wykazuje **0/9 etapów DONE, 8 W_TRAKCIE, 1 PLANOWANE**; mikroplan `docs/VN_MICROTASKS.json`: **2 DONE, 1 IN_PROGRESS, 34 TODO**. Przyrost jakości kodu nie kończy automatycznie kryteriów wymagających realnego sprzętu, człowieka lub licencji.

Brakuje szczególnie: naturalnych PL/EN próbek ze sprawdzonym wzorcem WER/CER, porównania rzeczywistych modeli i RAM na docelowym CPU; fizycznego mikrofonu USB/loopback i przerwania długiej sesji 2h+; prawdziwego modelu GGUF i kontroli faktów; legal review zależności/instalatora, próby aktualizacji/odinstalowania/AV/SmartScreen, czytnika ekranu i odbioru beta Wiedora.

Ponowny odczyt i kontrola hashów to ograniczenie typowych wyścigów, nie globalna blokada niekooperujących procesów zewnętrznych. Indeksowanie mowy przy slajdach jest tylko **czasowe**, a nie semantyczne. Nie zmieniono `testowyemailaplikacja-spec/Constant_app`, Netlify, Supabase, produkcyjnego `main`, praw do prywatnych nagrań ani modelu. Status izolowanego KWN BETA pozostaje zachowany.
