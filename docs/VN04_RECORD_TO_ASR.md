# VN-04 — ukończona sesja mikrofonowa do jednego silnika ASR

Komenda \`record-transcribe\` łączy nagrywanie WAV z istniejącym przepływem OBS → lokalny Whisper → checkpointy → TXT/SRT/VTT/JSON. Działa dopiero po zamknięciu sesji, weryfikacji SHA-256 i zapisanych zgód. Nie dopisuje funkcji automatycznego nasłuchu w tle.

Jedna część WAV:

\`\`\`powershell
python -m videonotes record-transcribe C:\\Nagrania\\sesja --project C:\\Notatki\\nowy --model C:\\Modele\\ggml-base.bin --whisper-cli C:\\Programy\\whisper-cli.exe
\`\`\`

Wiele części WAV po pauzach lub długim nagrywaniu:

\`\`\`powershell
python -m videonotes record-transcribe C:\\Nagrania\\sesja --project C:\\Notatki\\nowy --joined-wav C:\\Nagrania\\sesja\\joined-full.wav --model C:\\Modele\\ggml-base.bin --whisper-cli C:\\Programy\\whisper-cli.exe
\`\`\`

Połączony plik musi być nowy i nie może znajdować się w katalogu tworzonego projektu. Oryginalne WAV zostają nienaruszone; używamy istniejącej blokady nadpisania, kontroli ciągłości i limitu 4 GB RIFF WAV. Brak zgody na mikrofon/system audio lub uszkodzony SHA przerywa operację bez tworzenia nowego projektu.

Jeśli model przerwie działanie, projekt z dotychczasowymi checkpointami pozostaje na dysku. Wówczas użyj polecenia \`python -m videonotes resume C:\\Notatki\\nowy\`, a NIE ponownie \`record-transcribe\` do tego samego katalogu. Nie dochodzi do automatycznego usuwania nagrań.

Testy Linux CI: realne FFmpeg/FFprobe z syntetycznym PCM, a rozpoznawanie mowy tylko przez atrapę ASR. Nie jest to rzeczywisty mikrofon Windows, dwugodzinny sprzętowy test ani weryfikacja jakości mowy. VN-04 pozostaje w realizacji.
