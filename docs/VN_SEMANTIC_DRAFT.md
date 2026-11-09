# VN-02/VN-03 — lokalne szkice semantyczne llama.cpp (NIEZWERYFIKOWANE)

Lokalny program potrafi przygotować **opcjonalny, semantyczny szkic** z ukończonej poprawionej transkrypcji. Wymaga osobno zainstalowanego \`llama-cli\` i wybranego przez właściciela lokalnego modelu \`.gguf\`. Nie pobiera modelu, nie używa chmury, płatnego API, konta ani strony Wiedora. **Przed użyciem sprawdź licencję modelu i konkretnego binarium.**

\`\`\`powershell
python -m videonotes semantic-draft C:\\Notatki\\projekt --model C:\\Modele\\lokalny.gguf --llama-cli C:\\Narzędzia\\llama-cli.exe --output C:\\Notatki\\szkic-001.json --section-minutes 10
python -m videonotes semantic-verify C:\\Notatki\\projekt --file C:\\Notatki\\szkic-001.json
python -m videonotes semantic-export C:\\Notatki\\projekt --file C:\\Notatki\\szkic-001.json --output C:\\Notatki\\szkic-001.md
\`\`\`

## Co jest rzeczywiście zrobione

Każdy przedział transkrypcji jest opracowywany osobno, a dla oszczędzania RAM i kontekstu modelu wybierany jest ograniczony zestaw fragmentów. Lokalny \`llama-cli\` z \`--json-schema-file\` dostaje prompt w prywatnym pliku tymczasowym, a nie w argumentach linii poleceń; do stdout kierowany jest wynik bez wypisywania promptu. Nie jest to anonimowość wobec lokalnego, zainstalowanego programu modelowego. Strumienie stderr są odrzucane, a błędny JSON i nieznane ID cytatu są odrzucane bez zapisania częściowego wyniku.

Każde zaproponowane twierdzenie zawiera 1–3 identyfikatory fragmentów oraz dokładne fragmenty z poprawionej transkrypcji. Zapisywany jest SHA-256 lokalnego modelu i odcisk tekstu źródłowego. Jeśli źródło ulegnie zmianie, weryfikacja i eksport odmawiają. Szkic zapisuje się w **nowym** pliku \`JSON\`, a nie w \`notes.json\`, \`edits.json\` czy surowym \`transcript.json\`. Export Markdown zawiera oryginalne cytaty i czytelne ostrzeżenia.

## Czego to nadal nie dowodzi

Podanie poprawnego ID **nie oznacza**, że parafraza lub definicja modelu jest prawdziwa. Dlatego \`semantic_facts_verified=false\`, \`human_reviewed=false\` i wszystkie \`requires_human_review=true\`. Komenda \`semantic-verify\` sprawdza wyłącznie zgodność cytatów i bieżącego tekstu, nie prawdziwość twierdzeń. Brak dotychczas testu rzeczywistego modelu i jakości na materiałach wykładowych. Uruchomienie z bardzo dużym modelem może być powolne albo przekroczyć RAM, a niezgodna wersja \`llama-cli\` może nie obsługiwać żądanych flag — kończy się wtedy odmową bez zapisu.

Flagi CLI \`-m\`, \`-f\`, \`-n\`, \`--temp\`, \`--no-display-prompt\`, \`--json-schema-file\` bazują na współczesnym interfejsie llama.cpp. Trzeba użyć aktualnej, lokalnej instalacji. W praktyce potrzebne są testy modelu, rozdziałów, wielogodzinnej transkrypcji i ręcznej oceny jakości. VN-02 i VN-03 pozostają **W TRAKCIE**, nie DONE.

Testy jednostkowe obejmują format JSON, cytaty z ID/czasem, prywatny plik promptu, odmowę dla nieznanego ID, brak nadpisania i przerwany lokalny proces. Model jest atrapą, więc **nie jest to test realnej jakości LLM**.

## Ograniczanie niepopartych liczb, adresów i skrótów (09.11.2026)

Model nie może swobodnie dopisywać nowych **dosłownych liczb**, adresów IP, portów i wielkimi literami zapisanych skrótów technicznych, których nie ma w przypisanych fragmentach transkrypcji. Lokalny filtr odrzuca cały szkic bez zapisu, jeżeli któraś z tych cech nie ma śladu w cytowanych źródłach. Kontrola obejmuje też nagłówki i ponowną weryfikację wcześniej utworzonych plików. Dzięki temu dokument nie przejdzie weryfikatora tylko dlatego, że model podał poprawny, lecz nieistotny identyfikator źródłowy.

**Nie jest to weryfikacja faktów.** Dwa różne zdania mogą używać identycznych liczb i skrótów, a mimo to znaczyć coś innego. Program może też konserwatywnie odrzucić poprawne parafrazy z przekształconymi jednostkami, numeracją lub niepopartymi formalnie akronimami. Częściowo edytowane stare szkice mogą teraz wymagać ponownego wygenerowania. Liczby zapisane słownie oraz logiczne wnioskowanie nie są przez ten filtr potwierdzane. Wszystkie rezultaty pozostają oznaczone jako niezweryfikowane, wymagające kontroli człowieka.
