"""Optional local whisper.cpp adapter; no models or libraries auto-downloaded."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .errors import VideoNotesError
from .media import _run, executable

MAX_ASR_JSON_BYTES = 32 * 1024 * 1024


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    """Do not let duplicate JSON keys silently replace Whisper results."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise VideoNotesError("Silnik ASR zwrócił powielone pola JSON.")
        result[key] = value
    return result


def parse_whisper_output(payload: object, *, offset_ms: int, duration_ms: int) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("transcription"), list):
        raise VideoNotesError("Silnik ASR zwrócił nieprawidłowy JSON.")
    if len(payload["transcription"]) > 100_000:
        raise VideoNotesError("Silnik ASR zwrócił za dużo segmentów.")
    segments = []
    seen: set[tuple[int, int, str]] = set()
    for entry in payload["transcription"]:
        if not isinstance(entry, dict):
            raise VideoNotesError("Nieprawidłowy segment ASR.")
        raw = entry.get("text")
        offsets = entry.get("offsets")
        if not isinstance(raw, str) or not isinstance(offsets, dict) or not raw.strip():
            if isinstance(raw, str) and not raw.strip() and isinstance(offsets, dict):
                continue
            raise VideoNotesError("Brakuje tekstu lub czasu w wyniku ASR.")
        start, end = offsets.get("from"), offsets.get("to")
        if type(start) is not int or type(end) is not int or start < 0 or end <= start or end > duration_ms + 500:
            raise VideoNotesError("Silnik ASR zwrócił nieprawidłowy czas segmentu.")
        absolute_start = offset_ms + min(start, duration_ms)
        absolute_end = offset_ms + min(end, duration_ms)
        if absolute_start >= absolute_end:
            raise VideoNotesError("Segment ASR wychodzi poza granice nagrania.")
        # Only exact same text AND time is a duplicate. Repeated speech at
        # distinct timestamps is legitimate and must not disappear.
        key = (absolute_start, absolute_end, raw.strip())
        if key in seen:
            continue
        seen.add(key)
        segments.append({"start_ms": key[0], "end_ms": key[1], "text": key[2]})
    segments.sort(key=lambda s: (s["start_ms"], s["end_ms"]))
    return segments


class WhisperCpp:
    def __init__(self, executable_path: str, model: Path):
        self.executable_path = executable(executable_path)
        self.model = Path(model).expanduser().resolve()
        if not self.model.is_file() or self.model.stat().st_size == 0:
            raise VideoNotesError("Model Whisper nie istnieje lub jest pusty. Pobierz go ręcznie zgodnie z licencją.")

    def transcribe(self, wav: Path, *, language: str, offset_ms: int, duration_ms: int) -> list[dict]:
        if language not in {"pl", "en", "auto"}:
            raise VideoNotesError("Nieobsługiwany język ASR.")
        with tempfile.TemporaryDirectory(prefix="vn-asr-") as temp:
            output = str(Path(temp) / "result")
            _run([self.executable_path, "--model", str(self.model), "--file", str(wav), "--language", language,
                  "--output-json", "--output-file", output, "--no-prints", "--no-gpu"], timeout=7200)
            try:
                file = Path(output + ".json")
                if file.is_symlink() or not file.is_file():
                    raise VideoNotesError("Silnik ASR zwrócił niedozwolony plik JSON.")
                # A growing file can bypass a stat-size check. Bound the
                # actual read and reject ambiguous duplicate JSON keys.
                with file.open("rb") as reader:
                    raw = reader.read(MAX_ASR_JSON_BYTES + 1)
                if len(raw) > MAX_ASR_JSON_BYTES or file.is_symlink():
                    raise VideoNotesError("Silnik ASR zwrócił zbyt duży JSON.")
                payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
            except (FileNotFoundError, OSError, UnicodeError, ValueError) as error:
                raise VideoNotesError("Nie można odczytać wynikowego JSON silnika ASR.") from error
        return parse_whisper_output(payload, offset_ms=offset_ms, duration_ms=duration_ms)
