# VN-05 — lokalny import audio bez OBS

**Data:** 2026-11-06. **Stan:** pierwsza część VN-05 zaimplementowana do testów. Cały etap nadal W TRAKCIE.

Do istniejącego importu MP4/MKV/WebM i WAV dodano obsługę rozszerzeń **MP3, M4A, FLAC, OGG, OPUS oraz MOV**. Ta sama ścieżka kodu FFprobe → FFmpeg mono PCM/16kHz → lokalny ASR → checkpoint → transkrypcja/eksport służy nagraniom OBS i plikom audio. Nie powstał drugi, niespójny silnik.

Użytkownik może wybrać plik w interfejsie GUI lub wywołać:

```bash
python -m videonotes inspect wykład.mp3
python -m videonotes transcribe wykład.mp3 --project moje-notatki --model ggml-base.bin --whisper-cli whisper-cli --language pl
```

Format kontenera nie gwarantuje obsługi każdego kodeka. Właściwe kodeki rozpoznaje lokalny FFprobe, a przy nieobsługiwanym kodeku FFmpeg zwraca czytelny błąd. W nagraniach z wieloma strumieniami wybór ścieżki jest jawny.

**Kontrola techniczna:** `tests/test_audio_formats.py` tworzy własne syntetyczne pliki MP3/M4A/FLAC/OGG/OPUS/MOV przez FFmpeg, następnie sprawdza wykrycie audio, ekstrakcję WAV oraz testuje transkrypcję MP3 przez już istniejącą kolejkę i checkpoint z atrapą ASR. Testy te nie używają prawdziwego modelu i nie dowodzą poprawności rozpoznawania słów.

**Wciąż poza zakresem tego pakietu:** nagrywanie mikrofonem, przechwytywanie Windows loopback, miksowanie ścieżek, zgoda na nagrywanie innych osób, testy urządzeń USB i realne sesje. Etap VN-05 nie może uzyskać DONE, dopóki te wymagania nie zostaną spełnione.
