"""Separate local CPU process for faster-whisper benchmark only.

Requires the optional faster-whisper package and an already-present
CTranslate2 model directory. Never download a model during execution.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .errors import VideoNotesError
from .storage import atomic_write


def transcribe_local(wav: Path, model_path: Path, output: Path, *, language: str, threads: int) -> None:
    model_path = Path(model_path).expanduser().resolve()
    required = ("config.json", "model.bin", "vocabulary.txt")
    if not model_path.is_dir() or any(not (model_path / part).is_file() for part in required):
        raise VideoNotesError("Model faster-whisper wymaga lokalnych plików config.json, model.bin i vocabulary.txt.")
    if language not in {"pl", "en", "auto"} or not 1 <= threads <= 64:
        raise VideoNotesError("Nieobsługiwane ustawienia języka lub CPU.")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise VideoNotesError("Nie zainstalowano opcjonalnego faster-whisper. Nie pobieram go automatycznie.") from error
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=threads,
                         num_workers=1, local_files_only=True)
    segments, _info = model.transcribe(str(wav), beam_size=5,
                                       language=None if language == "auto" else language,
                                       vad_filter=False, condition_on_previous_text=True)
    # Iterating the generator is required to actually execute the inference.
    result = "\n".join(part.text.strip() for part in segments if part.text.strip())
    atomic_write(Path(output), (result + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Local faster-whisper CPU inference, no network")
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--language", required=True, choices=("pl", "en", "auto"))
    parser.add_argument("--threads", required=True, type=int)
    args = parser.parse_args()
    try:
        transcribe_local(args.wav, args.model_dir, args.output, language=args.language, threads=args.threads)
        return 0
    except VideoNotesError:
        # Do not print transcript, file paths or model internals.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
