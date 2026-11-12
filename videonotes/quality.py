"""Offline reference comparison for ASR outputs; no recordings or text in reports.

Text-to-text metrics do NOT measure inference speed, RAM or verify which
model produced the output. The caller must run real engines separately.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import json
import re
import unicodedata
from pathlib import Path
from typing import Sequence

from .errors import VideoNotesError

MAX_WORDS = 6000
MAX_BYTES = 300_000


def _tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", unicodedata.normalize("NFC", value).casefold(), flags=re.UNICODE)


def _distance(a: Sequence[str], b: Sequence[str]) -> int:
    """Exact Levenshtein distance using Myers bit-vector algorithm.

    Python integers hold arbitrary bitsets, so both 5-minute transcripts and
    their character-level comparisons remain feasible without quadratic RAM.
    """
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(b) > len(a):
        a, b = b, a
    patterns: dict[str, int] = {}
    for index, token in enumerate(b):
        patterns[token] = patterns.get(token, 0) | (1 << index)
    positive, negative = ~0, 0
    score = len(b)
    highest = 1 << (len(b) - 1)
    for token in a:
        equal = patterns.get(token, 0)
        possible = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        plus = negative | ~(horizontal | positive)
        minus = positive & horizontal
        if plus & highest:
            score += 1
        if minus & highest:
            score -= 1
        plus = (plus << 1) | 1
        minus <<= 1
        positive = minus | ~(possible | plus)
        negative = plus & possible
    return score

def error_rates(reference: str, candidate: str) -> dict:
    """WER and CER excluding whitespace and punctuation, Unicode NFC."""
    target = _tokens(reference)
    got = _tokens(candidate)
    if not target:
        raise VideoNotesError("Pusta transkrypcja wzorcowa: WER jest nieokreślony.")
    if max(len(target), len(got)) > MAX_WORDS:
        raise VideoNotesError("Próbka benchmarku przekracza limit 6000 słów.")
    a = list("".join(target))
    b = list("".join(got))
    words = _distance(target, got)
    chars = _distance(a, b)
    return {
        "reference_words": len(target), "candidate_words": len(got),
        "word_errors": words, "wer": round(words / len(target), 6),
        "reference_chars_no_spaces": len(a), "character_errors": chars,
        "cer_no_spaces": round(chars / len(a), 6),
    }


def _read(path: Path) -> tuple[str, str]:
    try:
        file = Path(path)
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_BYTES:
            raise VideoNotesError("Plik TXT do benchmarku jest nieobecny, dowiązany lub zbyt duży.")
        # A file can grow after stat() but before read(). Never read a multi-GB
        # recording or a changing file into memory by accident.
        with file.open("rb") as reader:
            content = reader.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES or file.is_symlink():
            raise VideoNotesError("Plik TXT zmienił rozmiar lub jest dowiązaniem; pomiar przerwany.")
        return content.decode("utf-8-sig"), hashlib.sha256(content).hexdigest()
    except (OSError, UnicodeError) as error:
        raise VideoNotesError("Nie można odczytać TXT do benchmarku.") from error


def validate_reference_file(reference: Path) -> None:
    """O(n) preflight before inference; never compare a reference to itself.

    Do not return private text or include it in errors/logs. A reference is a
    human-supplied claim and validating it does not verify its alignment.
    """
    text, _hash = _read(reference)
    tokens = _tokens(text)
    if not tokens:
        raise VideoNotesError("Pusta transkrypcja wzorcowa: WER jest nieokreślony.")
    if len(tokens) > MAX_WORDS:
        raise VideoNotesError("Próbka benchmarku przekracza limit 6000 słów.")


def _publish_private_report(output: Path, payload: bytes) -> None:
    """Publish a verified report without overwriting an earlier local run.

    Benchmark input text and model results may be privately curated; an
    output path accidentally pointing at a reference file must never erase it.
    """
    target = Path(output).expanduser().absolute()
    if target.suffix.lower() != ".json" or target.exists() or target.is_symlink():
        raise VideoNotesError("Raport benchmarku wymaga nowego, nieistniejącego pliku .json.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vn-accuracy-", dir=target.parent) as tmp:
        temporary = Path(tmp) / "report.json"
        with temporary.open("wb") as writer:
            writer.write(payload)
            writer.flush()
            os.fsync(writer.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError as error:
            raise VideoNotesError("Raport powstał równolegle; nie nadpisano istniejących danych.") from error
        except OSError as error:
            raise VideoNotesError("Nie można bezpiecznie opublikować raportu benchmarku.") from error


def compare_text_files(reference: Path, candidates: dict[str, Path], *, output: Path | None = None) -> dict:
    if not 1 <= len(candidates) <= 8:
        raise VideoNotesError("Podaj 1–8 kandydatów do porównania.")
    if output is not None:
        report_path = Path(output).expanduser().absolute()
        if (report_path.suffix.lower() != ".json" or
                report_path.exists() or report_path.is_symlink()):
            raise VideoNotesError("Raport benchmarku wymaga nowego, nieistniejącego pliku .json.")
    truth, h = _read(reference)
    metrics = []
    recorded_inputs = [(Path(reference), h)]
    for label, location in sorted(candidates.items()):
        if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", label):
            raise VideoNotesError("Etykieta musi zawierać 1–32 znaki ASCII.")
        candidate, digest = _read(location)
        recorded_inputs.append((Path(location), digest))
        metrics.append({"label_supplied_by_user": label, "candidate_sha256": digest, **error_rates(truth, candidate)})
    report = {
        "schema": "videonotes-asr-accuracy-v1", "reference_sha256": h,
        "normalization": "NFC/casefold, punctuation ignored, CER without spaces",
        "input_kind": "precomputed_text_only", "engine_provenance_verified": False,
        "speed_measured": False, "peak_ram_measured": False, "results": metrics,
    }
    # Reject results for a reference or candidate changed while scoring
    # another file; published hashes must describe the compared contents.
    for location, digest in recorded_inputs:
        if _read(location)[1] != digest:
            raise VideoNotesError("Pliki wejściowe zmieniły się podczas pomiaru WER/CER.")
    if output is not None:
        payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _publish_private_report(output, payload)
    return report
