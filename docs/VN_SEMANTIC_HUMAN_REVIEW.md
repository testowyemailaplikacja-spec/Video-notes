# VN-02/VN-03 — ręczny odbiór szkiców AI, twierdzenie po twierdzeniu

**Cel:** nie przenosić niezweryfikowanych parafraz generowanych przez lokalny model do zaakceptowanych notatek. Nowy moduł pozwala właścicielowi podjąć jednoznaczną decyzję o każdym twierdzeniu, zachowując szkic, źródło i zapis decyzji bez nadpisywania.

Po wykonaniu \`semantic-draft\` oraz porównaniu twierdzeń z rzeczywistym nagraniem i cytatami:

\`\`\`powershell
python -m videonotes semantic-review-init C:\Notatki\projekt --file C:\Notatki\szkic.json --review C:\Notatki\recenzja-001
python -m videonotes semantic-review-status C:\Notatki\projekt --file C:\Notatki\szkic.json --review C:\Notatki\recenzja-001
python -m videonotes semantic-review-mark C:\Notatki\projekt --file C:\Notatki\szkic.json --review C:\Notatki\recenzja-001 --claim claim-000000-000 --decision approve --reviewer "Lokalny recenzent" --confirm
python -m videonotes semantic-review-mark C:\Notatki\projekt --file C:\Notatki\szkic.json --review C:\Notatki\recenzja-001 --claim claim-000001-000 --decision reject --reviewer "Lokalny recenzent" --note "Niepoparte nagraniem" --confirm
python -m videonotes semantic-review-export C:\Notatki\projekt --file C:\Notatki\szkic.json --review C:\Notatki\recenzja-001 --output C:\Notatki\notatka-oceniona.md
\`\`\`

Każda decyzja wymaga \`--confirm\` i jest publikowana jako osobny, niezmienny plik \`decisions/claim-....json\`, chroniony odciskiem SHA-256 źródła, szkicu i twierdzenia. Nie istnieje tryb masowej automatycznej akceptacji. Po błędnej decyzji należy rozpocząć **nową recenzję w nowym katalogu**, pozostawiając poprzednią jako ślad audytu.

\`semantic-review-status\` każdorazowo sprawdza powiązanie z poprawioną transkrypcją, strukturę manifestu i każdą decyzję. Eksport jest zablokowany do rozpatrzenia wszystkich twierdzeń. W Markdown znajdują się tylko te z decyzją \`approve\`, dokładne cytaty i ostrzeżenie o granicach kontroli.

**Program nie weryfikuje tożsamości recenzenta ani prawdziwości jego zatwierdzeń.** Etykieta recenzenta to deklaracja użytkownika; nie jest podpisem cyfrowym ani niezależnym audytem. Rzeczywistą kontrolę musi wykonać człowiek na legalnym nagraniu. KWN nie wysyła recenzji do sieci; pliki zawierające treść wykładu są prywatne i nie należy umieszczać ich na publicznym GitHubie. CI używa syntetycznych transkrypcji i decyzji, dlatego VN-02/VN-03 pozostają W TRAKCIE.
