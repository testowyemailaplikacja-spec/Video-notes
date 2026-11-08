"""End-to-end real whisper.cpp on original, generated two-track OBS-like media.

Ephemeral CI: two own TTS WAVs, synthetic silent track and synthetic black
video. No user recordings, public transcripts, cloud inference or paid APIs.
This is NOT natural-lecture quality evaluation or a physical Windows test.
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
from videonotes.exports import edit_segment, export_project
from videonotes.media import probe
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project


def make_two_track_media(audio: Path, output: Path) -> None:
    # Audio stream #1: silence / system sound; stream #2: actual microphone TTS.
    # In particular, accepting the first track would silently transcribe silence.
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:r=1",
        "-i", str(audio),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-map", "0:v:0", "-map", "2:a:0", "-map", "1:a:0",
        "-c:v", "mpeg4", "-q:v", "8", "-c:a", "aac",
        "-shortest", "-y", str(output),
    ]
    try:
        subprocess.run(command, capture_output=True, check=True, timeout=90)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise VideoNotesError("Nie udało się zbudować syntetycznego kontenera OBS.") from error


def check_real_media(audio: Path, container: str, language: str,
                     whisper: Path, model: Path, root: Path) -> dict:
    media = root / f"{language}.{container}"
    make_two_track_media(audio, media)
    info = probe(media)
    streams = info["audio_streams"]
    if len(streams) != 2 or streams[0]["index"] == streams[1]["index"]:
        raise VideoNotesError("Brak dwóch niezależnych ścieżek audio.")
    if media.stat().st_size < 1000 or info["duration_ms"] < 1000:
        raise VideoNotesError("Syntetyczny plik OBS jest niekompletny.")

    refused = root / f"refused-{language}-{container}"
    try:
        create_project(media, refused, model=model, whisper_cli=str(whisper),
                       language=language, chunk_ms=30000)
    except VideoNotesError:
        if refused.exists():
            raise VideoNotesError("Odmowa wyboru ścieżki utworzyła projekt.")
    else:
        raise VideoNotesError("Brak jawnego wyboru spośród dwóch ścieżek.")

    target = root / f"project-{language}-{container}"
    source_hash = hashlib.sha256(media.read_bytes()).hexdigest()
    started = time.perf_counter()
    project = create_project(media, target, model=model,
                             whisper_cli=str(whisper), language=language,
                             stream=streams[1]["index"], chunk_ms=30000)
    transcript = transcribe_project(target)
    stored_project, stored, edits = read_project(target)
    if stored != transcript or project["id"] != stored_project["id"] or edits["edits"]:
        raise VideoNotesError("Niepoprawny checkpoint transkrypcji OBS.")
    if stored_project["source"]["stream_index"] != streams[1]["index"]:
        raise VideoNotesError("Wybrano inną ścieżkę audio.")
    if stored["completed_chunks"] != [0] or not stored["segments"]:
        raise VideoNotesError("Prawdziwy model nie rozpoznał próbki OBS.")
    if not all(s["text"].strip() and 0 <= s["start_ms"] < s["end_ms"]
               for s in stored["segments"]):
        raise VideoNotesError("Transkrypcja zawiera pusty lub błędny segment.")

    raw_bytes = (target / "transcript.json").read_bytes()
    first = stored["segments"][0]
    correction = "Ręczna poprawka źródła OBS — test bez chmury."
    edit_segment(target, first["id"], correction)
    exported = export_project(target)
    if len(exported) != 4 or any(not file.is_file() for file in exported):
        raise VideoNotesError("Nie zapisano czterech formatów eksportu.")
    if (target / "transcript.json").read_bytes() != raw_bytes:
        raise VideoNotesError("Edytowanie nadpisało surowy wynik modelu.")
    for suffix in (".txt", ".srt", ".vtt", ".json"):
        payload = (target / "exports" / ("transcript" + suffix)).read_text("utf-8")
        if correction not in payload:
            raise VideoNotesError("Brak ręcznej poprawki w eksporcie.")
    if hashlib.sha256(media.read_bytes()).hexdigest() != source_hash:
        raise VideoNotesError("Plik wejściowy został zmodyfikowany.")
    return {
        "container": container,
        "language": language,
        "tracks": len(streams),
        "selected_track_explicitly": True,
        "real_whisper_inference": True,
        "checkpoint_chunks": len(stored["completed_chunks"]),
        "recognized_segments": len(stored["segments"]),
        "source_preserved": True,
        "human_edit_keeps_raw_asr": True,
        "exports_checked": 4,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--whisper", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--pl", type=Path, required=True)
    parser.add_argument("--en", type=Path, required=True)
    args = parser.parse_args()
    for item in (args.whisper, args.model, args.pl, args.en):
        if not item.is_file() or not item.stat().st_size:
            raise VideoNotesError("Brak wymaganego lokalnego składnika testu.")
    with tempfile.TemporaryDirectory(prefix="vn-obs-real-asr-") as folder:
        root = Path(folder)
        results = [
            check_real_media(args.pl, "mp4", "pl", args.whisper, args.model, root),
            check_real_media(args.en, "mkv", "en", args.whisper, args.model, root),
        ]
    print(json.dumps({
        "schema": "videonotes-real-obs-multitrack-asr-ci-v1",
        "audio_kind": "original synthetic TTS with silent second track",
        "engine": "real whisper.cpp CPU",
        "cases": results,
        "public_user_media": False,
        "natural_lecture_wer_evaluated": False,
        "physical_windows_test": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
