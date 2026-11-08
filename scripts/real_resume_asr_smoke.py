"""Genuine local Whisper cancellation/restart over 2 FFmpeg chunks (synthetic TTS).

Tests persistence across an actual real ASR process; it is not a two-hour or
physical Windows test. Does not upload or print speech/transcripts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.exports import export_project
from videonotes.media import probe
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project
from scripts.real_obs_multitrack_asr_smoke import make_two_track_media


def extend_original_tts(wav: Path, destination: Path) -> None:
    # Two adjacent 30-second chunks; never rely on a fake ASR engine.
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "12", "-i", str(wav), "-t", "34",
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-y", str(destination),
    ]
    try:
        subprocess.run(command, capture_output=True, check=True, timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise VideoNotesError("Nie można utworzyć dłuższej syntetycznej wypowiedzi.") from error
    if probe(destination)["duration_ms"] != 34_000:
        raise VideoNotesError("Niepoprawna długość 34-sekundowej próbki.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--whisper", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--pl", type=Path, required=True)
    args = parser.parse_args()
    for item in (args.whisper, args.model, args.pl):
        if not item.is_file() or not item.stat().st_size:
            raise VideoNotesError("Brak wymaganego pliku lokalnego.")
    with tempfile.TemporaryDirectory(prefix="vn-real-resume-ci-") as directory:
        root = Path(directory)
        wav, media, folder = root / "speech-34s.wav", root / "obs-two-tracks.mkv", root / "project"
        extend_original_tts(args.pl, wav)
        make_two_track_media(wav, media)
        info = probe(media)
        if len(info["audio_streams"]) != 2 or not 30_500 <= info["duration_ms"] <= 35_500:
            raise VideoNotesError("Nie uzyskano dwustrumieniowego nagrania 2-chunk.")
        voice_track = info["audio_streams"][1]["index"]
        create_project(media, folder, model=args.model, whisper_cli=str(args.whisper),
                       stream=voice_track, language="pl", chunk_ms=30_000)
        progress: list[tuple[int, int]] = []
        began = time.perf_counter()
        def notice(done: int, total: int) -> None:
            progress.append((done, total))
        def cancel_after_first() -> bool:
            return bool(progress and progress[-1][0] >= 1)
        try:
            transcribe_project(folder, progress=notice, cancel=cancel_after_first)
        except VideoNotesError as error:
            if "Przerwano na żądanie" not in str(error):
                raise
        else:
            raise VideoNotesError("Nie przerwano po zatwierdzonym pierwszym chunku.")
        _project, before, _edits = read_project(folder)
        if before["completed_chunks"] != [0] or not before["segments"] or (folder / ".processing.lock").exists():
            raise VideoNotesError("Przerwany proces nie zachował poprawnego checkpointu.")
        first_chunk = json.dumps(before["segments"], ensure_ascii=False, sort_keys=True)
        first_hash = hashlib.sha256((folder / "transcript.json").read_bytes()).hexdigest()
        after = transcribe_project(folder)
        _project, recovered, _edits = read_project(folder)
        if recovered != after or recovered["completed_chunks"] != [0, 1]:
            raise VideoNotesError("Wznowienie prawdziwego ASR zgubiło chunk.")
        preserved = [segment for segment in recovered["segments"] if segment["chunk_index"] == 0]
        if json.dumps(preserved, ensure_ascii=False, sort_keys=True) != first_chunk:
            raise VideoNotesError("Wznowienie zmieniło wcześniejszy checkpoint.")
        if not any(segment["chunk_index"] == 1 for segment in recovered["segments"]):
            raise VideoNotesError("Brak rozpoznanego tekstu w drugim fragmencie.")
        after_bytes = (folder / "transcript.json").read_bytes()
        again = transcribe_project(folder)
        if again != after or (folder / "transcript.json").read_bytes() != after_bytes:
            raise VideoNotesError("Ponowne wznowienie zmodyfikowało gotowy projekt.")
        exported = export_project(folder)
        if len(exported) != 4 or any(not item.is_file() for item in exported):
            raise VideoNotesError("Brakuje lokalnych formatów po odzyskaniu.")
        summary = {
            "schema": "videonotes-real-asr-resume-ci-v1",
            "real_whisper_cpp_cpu": True,
            "source_kind": "original repeated Polish synthetic TTS with two audio tracks",
            "duration_ms": info["duration_ms"],
            "cancelled_after_chunk": 1,
            "completed_after_resume": len(recovered["completed_chunks"]),
            "segments_after_resume": len(recovered["segments"]),
            "raw_checkpoint_sha256_before_resume": first_hash,
            "no_duplicate_segments": len({s["id"] for s in recovered["segments"]}) == len(recovered["segments"]),
            "idempotent_rerun": True,
            "exports": len(exported),
            "elapsed_seconds": round(time.perf_counter() - began, 3),
            "physical_windows_test": False,
            "two_hour_model_test": False,
        }
        if not summary["no_duplicate_segments"]:
            raise VideoNotesError("Powielone identyfikatory wypowiedzi po wznowieniu.")
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
