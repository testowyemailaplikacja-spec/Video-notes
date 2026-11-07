"""Real FFmpeg 2h+ compressed audio import/checkpoint/resume acceptance.

CI-only test. The 2h+ recording is an original generated sine wave, and
inference is a *stub*. Real container decoding and 61 separate 2-minute WAV
extractions execute using installed FFmpeg; this is NOT a real ASR stress test.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
import threading
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.exports import export_project
from videonotes.media import probe
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project

DURATION_SECONDS = 2 * 3600 + 60  # 121 minutes, 61 chunks x 120 seconds


class SyntheticEngine:
    calls: list[int] = []

    def __init__(self, executable, model):
        pass

    def transcribe(self, wav, *, language, offset_ms, duration_ms):
        self.calls.append(offset_ms)
        # Checkpoint state should be grounded in the actual extracted PCM WAV.
        import wave
        with wave.open(str(wav), "rb") as reader:
            if reader.getnframes() <= 0 or reader.getframerate() != 16_000:
                raise VideoNotesError("FFmpeg nie zwrócił realnego poprawnego PCM.")
        return [{"start_ms": offset_ms,
                 "end_ms": offset_ms + min(duration_ms, 1000),
                 "text": f"Syntetyczny marker {offset_ms}"}]


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VideoNotesError("Wymagane lokalne FFmpeg i FFprobe.")
    with tempfile.TemporaryDirectory(prefix="vn-2h-real-media-") as temp:
        root = Path(temp)
        compressed = root / "sine-2h.ogg"
        started = time.perf_counter()
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
            "-t", str(DURATION_SECONDS), "-c:a", "libopus",
            "-b:a", "12k", str(compressed),
        ], check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=360)
        generation_seconds = time.perf_counter() - started
        duration = probe(compressed)["duration_ms"]
        if not 7_260_000 <= duration <= 7_261_000:
            raise VideoNotesError("Testowe 121-minutowe audio ma nieprawidłowy czas.")
        expected_chunks = math.ceil(duration / 120_000)
        if expected_chunks != 61:
            raise VideoNotesError("Oczekiwano dokładnie 61 fragmentów.")
        source_digest = hashlib.sha256(compressed.read_bytes()).hexdigest()
        model = root / "fake-only-model.bin"
        model.write_bytes(b"Not a real ASR model. Test has a deterministic stub.")
        folder = root / "project"
        create_project(compressed, folder, model=model,
                       whisper_cli="synthetic-cli", language="pl", chunk_ms=120_000)
        stop = threading.Event()
        def on_progress(done, total):
            if total != 61:
                raise VideoNotesError("Niewłaściwy postęp dzielenia audio.")
            if done == 12:
                stop.set()
        SyntheticEngine.calls = []
        processing_started = time.perf_counter()
        try:
            transcribe_project(folder, asr_factory=SyntheticEngine,
                               progress=on_progress, cancel=stop.is_set)
        except VideoNotesError as error:
            if "Przerwano na żądanie" not in str(error):
                raise
        else:
            raise VideoNotesError("Sztuczne przerwanie przy 12. fragmencie nie zadziałało.")
        partial = read_project(folder)[1]
        if partial["completed_chunks"] != list(range(12)):
            raise VideoNotesError("Błędny checkpoint po przerwaniu 121-minutowej sesji.")
        if (folder / ".processing.lock").exists():
            raise VideoNotesError("Blokada nie została zdjęta po świadomym zatrzymaniu.")
        completed = transcribe_project(folder, asr_factory=SyntheticEngine)
        if completed["completed_chunks"] != list(range(61)):
            raise VideoNotesError("Wznowienie nie przetworzyło kompletnych 121 minut.")
        if len(completed["segments"]) != 61 or len({x["id"] for x in completed["segments"]}) != 61:
            raise VideoNotesError("Nieprawidłowa liczba lub powielone segmenty po wznowieniu.")
        if len(SyntheticEngine.calls) != 61 or len(set(SyntheticEngine.calls)) != 61:
            raise VideoNotesError("Wznowienie ponownie przetworzyło zapisane fragmenty.")
        again = transcribe_project(folder, asr_factory=SyntheticEngine)
        if again != completed or len(SyntheticEngine.calls) != 61:
            raise VideoNotesError("Powtórne wznowienie nie jest idempotentne.")
        exports = export_project(folder)
        if len(exports) != 4:
            raise VideoNotesError("Błędny eksport 121-minutowej transkrypcji.")
        if compressed.stat().st_size <= 0 or hashlib.sha256(compressed.read_bytes()).hexdigest() != source_digest:
            raise VideoNotesError("Przetwarzanie zmieniło źródłowe nagranie.")
        print(json.dumps({
            "schema": "videonotes-real-2h-ffmpeg-ci-v1",
            "real_ffmpeg_audio_extraction": True,
            "real_speech_recognition": False,
            "audio_type": "original generated Opus tone, no human voice",
            "duration_ms": duration,
            "chunks": 61,
            "interrupted_after": 12,
            "source_size_bytes": compressed.stat().st_size,
            "generation_seconds": round(generation_seconds, 3),
            "checkpoint_resume_and_export_seconds": round(time.perf_counter() - processing_started, 3),
            "source_preserved": True,
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
