"""Privacy-preserving preparatory manifest for owner-provided PL/EN ASR samples.

A hash and a valid reference file do not establish speaker consent,
natural speech, reference correctness or legal redistribution rights.
Never print local filenames, recording text or user-provided paths.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import sha256_file
from .errors import VideoNotesError
from .media import probe
from .quality import validate_reference_file

SCHEMA = "videonotes-private-asr-input-preflight-v1"


def inspect_asr_samples(samples: dict[str, tuple[Path, Path]],
                        *, ffprobe: str = "ffprobe") -> dict:
    """Check local media and reference preconditions, no ASR/model execution."""
    if not isinstance(samples, dict) or set(samples) != {"pl", "en"}:
        raise VideoNotesError("Wymagane są osobne próbki PL i EN.")
    results = []
    inputs = []
    for language in ("pl", "en"):
        pair = samples[language]
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise VideoNotesError("Błędna para nagranie/referencja.")
        source, reference = (Path(x).expanduser() for x in pair)
        if (source.is_symlink() or reference.is_symlink() or not source.is_file()
                or not reference.is_file() or source.stat().st_size == 0):
            raise VideoNotesError("Brak bezpiecznego pliku źródła lub referencji.")
        validate_reference_file(reference)
        info = probe(source, ffprobe)
        tracks = info.get("audio_streams")
        if (not isinstance(tracks, list) or not tracks
                or type(info.get("duration_ms")) is not int
                or info["duration_ms"] <= 0):
            raise VideoNotesError("Nagranie nie zawiera poprawnego audio.")
        hashes = (sha256_file(source), sha256_file(reference))
        inputs.append((source, reference, hashes))
        results.append({
            "language": language, "media_sha256": hashes[0],
            "reference_sha256": hashes[1],
            "duration_ms": info["duration_ms"], "audio_track_count": len(tracks),
            "reference_format_checked": True,
            "natural_speech_verified": False,
            "legal_permission_verified": False,
            "reference_alignment_verified": False,
            "model_inference_performed": False,
        })
    for source, reference, hashes in inputs:
        # Recheck after probing both files; no report for concurrent edits.
        validate_reference_file(reference)
        if sha256_file(source) != hashes[0] or sha256_file(reference) != hashes[1]:
            raise VideoNotesError("Pliki ASR zmieniły się podczas preflightu.")
    return {"schema": SCHEMA, "samples": results, "private_data_uploaded": False,
            "formal_asr_acceptance": False}
