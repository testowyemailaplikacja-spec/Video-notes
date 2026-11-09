# VN-02/VN-07 — blokada zapisu poprawek transkrypcji

**Problem:** gdy okno Windows/Tk i import pliku z przeglądarki próbowały w podobnym momencie zmienić \`edits.json\`, oba narzędzia odczytywały starszą wersję i mogły nadpisać wzajemne poprawki mimo atomowego zapisu pojedynczego pliku. Od tej wersji oba korzystają ze wspólnej, lokalnej blokady \`.transcript-edits.lock\`.

## Zasada

Każda ręczna zmiana segmentu (\`edit\`, GUI) i import \`import-web-edits --apply\` muszą uzyskać blokadę **przed** odczytem aktualnych danych. Jeżeli plik blokady już istnieje, zapis jest odmawiany — bez oczekiwania, bez ukrytego nadpisania. Podgląd \`import-web-edits\` bez \`--apply\` nie wymaga blokady, ponieważ nie zmienia plików. Oryginalne \`transcript.json\` jest nadal nietykalne; powiązania źródłowe i eksporty pozostają takie jak dotychczas.

Do diagnostyki:

\`\`\`powershell
python -m videonotes edit-lock-status C:\\Notatki\\projekt
python -m videonotes edit-lock-recover C:\\Notatki\\projekt --confirm
\`\`\`

Wszystkie wyniki to stan procesu \`active\`, \`stale\`, \`unknown\`, \`invalid\` albo \`missing\`. **Wolno usunąć wyłącznie potwierdzoną osieroconą blokadę**, gdy proces już nie istnieje i użytkownik jawnie poda \`--confirm\`. Jeśli program działa lub status jest niejasny, blokadę należy zostawić. Program nie zabija procesów. Testy sprawdzają blokadę w rzeczywiście uruchomionym drugim procesie, w tym hosted Windows, oraz konflikty importu WWW.

Blokada jest *kooperacyjna*: chroni tylko narzędzia Video Notes używające tych samych procedur. Nie chroni przed niezależnym edytorem tekstowym bezpośrednio zmieniającym \`edits.json\`, zewnętrzną synchronizacją folderu, zmianą modelu ASR ani uszkodzeniem dysku. Import HTML/JS nie pracuje na żywo z bazą desktopową: nadal wymaga jawnego wyeksportowania poprawek i wskazania lokalnego pliku. To nie jest odbiór fizycznego Windows, całego KWN ani integracji z Wiedorą.
