# KWN — lokalny rejestr dowodów odbioru, bez publikowania danych

## Po co?

Automatyczne CI sprawdza funkcje i symulacje, ale nie dowodzi jakości wykładu, mikrofonu, realnego GGUF, instalacji Windows offline ani licencji. Ta procedura pomaga rejestrować **wyniki wykonane przez człowieka** jako `SELF_REPORTED_PASS` / `SELF_REPORTED_FAIL` / `NOT_RUN`; nigdy nie aktualizuje automatycznie `VN_STATUS.json`.

## Użycie na komputerze testowym

```powershell
python scripts/vn_acceptance_evidence.py --init C:\\KWN-prywatne\\wyniki.json
# W pliku lokalnym uzupełnij wyłącznie dopuszczone pola.
python scripts/vn_acceptance_evidence.py --check C:\\KWN-prywatne\\wyniki.json
```

Nie uruchamiaj na publicznym runnerze z prywatnym plikiem. `--init` odmawia nadpisania istniejącego rejestru. `--check` wypisuje tylko wyniki zbiorcze, bez żadnych lokalnych ścieżek, nazw urządzeń, tekstów nagrań lub identyfikatorów recenzenta. Narzędzie nie łączy się z siecią.

## Schemat pojedynczego wyniku

```json
{
  "case_id": "ASR-04",
  "kind": "PHYSICAL_WINDOWS",
  "result": "PASS",
  "checked_at": "2026-11-11",
  "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "attested_by_human": true,
  "sample_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "wer": 0.15,
  "cer": 0.08,
  "elapsed_seconds": 85.5,
  "peak_ram_mb": 1200,
  "evidence_url": "https://github.com/testowyemailaplikacja-spec/Video-notes/issues/95"
}
```

**To przykład formatu, nie prawdziwy wynik.** Hash commita, pliku i metryki należy zastąpić rzeczywiście zmierzonymi danymi. Link musi prowadzić do **wyłącznie zanonimizowanych metadanych**, nie do nagrania/transkrypcji. Narzędzie nie sprawdza prawdziwości deklaracji, podpisu osoby ani tożsamości; jest tylko walidatorem formatu i kompletności lokalnych metryk.

Dopuszczalne rodzaje: `PHYSICAL_WINDOWS`, `HUMAN_REVIEW`, `LEGAL_REVIEW`, `PORTAL_REVIEW`, `PRODUCT_DECISION`; dobrane do kryterium z [macierzy](VN_HARDWARE_ACCEPTANCE_20261107.md). `CI` nie może zostać uznane za fizyczny PASS. `PKG-02` wymaga osobno Windows i przeglądu prawnego, `NOTE-02` wymaga fizycznego Word oraz recenzji, `WEB-02` wymaga testu systemowego i recenzji dostępności.

Wpis `NOT_RUN` powinien zawierać tylko `case_id`, `kind` i `result`. `FAIL` lub `PASS` wymaga daty, commita, świadomego potwierdzenia oraz linku do anonimowych dowodów. `ASR-01` dodatkowo wymaga WER/CER, a `ASR-03/04` także czasu i RAM; `ASR-05` czasu i RAM.

**Nigdy nie dodawaj do repozytorium surowego lokalnego pliku `wyniki.json`, nagrań, transkrypcji, nazwisk, ścieżek, danych urządzeń, sekretów ani modeli.** Podsumowanie z `--check` nadaje się do dalszej weryfikacji tylko pod warunkiem osobnego, niezależnego potwierdzenia dowodów.

Nawet `SELF_REPORTED_PASS` dla całej macierzy **nie oznacza automatycznego DONE** i nie upoważnia do publikacji. Decyzja o wydaniu oraz integracji z Wiedora pozostaje osobna.

## Kontrola zakresu i dat — 11.11.2026

Wprowadzono dodatkowe ograniczenia walidatora: lokalny plik rejestru do 2 MiB, maksymalnie 512 wpisów, zakaz dat przyszłych. Nie da się przekazać do dalszego odbioru raportu datowanego na jutro, który przesłania wcześniejszy negatywny wynik. Wszystkie testy nadal są **deklaracją operatora**, nie niezależnym potwierdzeniem testu fizycznego. Wpisy pozostają poza GitHub.
