"""Read-only crash review and explicit, non-destructive salvage of local WAV.

Never mark a failed microphone session as finished. Incomplete RIFF chunks,
numbering gaps, collisions and interrupted takes must not silently become
complete lectures. Only the validated *contiguous* audio prefix can be copied
to a separately named WAV after the user confirms the recording has stopped.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import wave
from pathlib import Path

from .contracts import sha256_file
from .errors import VideoNotesError
from .microphone import PATTERN, SCHEMA, _inspect_single_wav
from .storage import load_json

TAKE = re.compile(r"^\.vn-take-[0-9a-f]{32}$")
MAX_PARTS = 100_000
MAX_WAV_BYTES = 2**32 - 1


def _inspect_recovery(folder: Path) -> tuple[dict, list[Path]]:
    root = Path(folder).expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise VideoNotesError("Wskaż zwykły katalog lokalnej sesji WAV (bez symlinków).")
    journal_path = root / "recording.json"
    if journal_path.is_symlink():
        raise VideoNotesError("Dziennik nagrania jest dowiązaniem symbolicznym.")
    journal = load_json(journal_path)
    if not isinstance(journal, dict) or journal.get("schema") != SCHEMA:
        raise VideoNotesError("Nieobsługiwana struktura dziennika nagrania.")
    state = journal.get("status")
    if state not in {"recording", "paused", "needs_review", "finished"}:
        raise VideoNotesError("Nieobsługiwany stan nagrania.")
    if journal.get("hash_policy") not in (None, "sha256-v1"):
        raise VideoNotesError("Nieznana polityka integralności WAV.")
    hashes = journal.get("segment_sha256")
    if hashes is not None and (not isinstance(hashes, dict) or any(
        not isinstance(k, str) or not PATTERN.fullmatch(k) or
        not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
        for k, v in hashes.items()
    )):
        raise VideoNotesError("Dziennik zawiera niepoprawne sumy SHA-256.")

    by_index: dict[int, list[tuple[str, Path]]] = {}
    issues: list[str] = []
    pending = 0
    # No directory tree recursion. Recording folders are flat except for
    # well-known .vn-take-UUID staging dirs, produced by this app.
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("part-"):
            if not PATTERN.fullmatch(entry.name):
                issues.append("Niezrozumiała nazwa pliku nagrania: " + entry.name[:100])
                continue
            by_index.setdefault(int(entry.name[5:10]), []).append(("committed", entry))
        elif entry.name.startswith(".vn-take-"):
            pending += 1
            if entry.is_symlink() or not entry.is_dir() or not TAKE.fullmatch(entry.name):
                issues.append("Nieprawidłowy katalog roboczy: " + entry.name[:100])
                continue
            for part in sorted(entry.iterdir()):
                if part.is_symlink() or not part.is_file() or not PATTERN.fullmatch(part.name):
                    issues.append("Nieprawidłowy plik roboczy: " + entry.name[:60] + "/" + part.name[:60])
                    continue
                by_index.setdefault(int(part.name[5:10]), []).append(("pending", part))

    if len(by_index) > MAX_PARTS:
        raise VideoNotesError("Zbyt wiele części WAV do odzyskania.")
    selected_paths: list[Path] = []
    selected: list[dict] = []
    max_index = max(by_index, default=-1)
    # One bad frame/gap terminates the prefix; never jump ahead and invent a
    # continuous timeline. All later files are preserved in original folders.
    for index in range(max_index + 1):
        variants = by_index.get(index)
        if not variants:
            issues.append(f"Brak fragmentu part-{index:05d}.wav; kolejne fragmenty pominięte.")
            break
        valid: list[tuple[str, Path, dict, str]] = []
        failed = False
        for source_type, source in variants:
            try:
                stat = _inspect_single_wav(source)
                digest = sha256_file(source)
                if (source_type == "committed" and isinstance(hashes, dict) and
                        source.name in hashes and digest != hashes[source.name]):
                    raise VideoNotesError("Niezgodny SHA-256 istniejącej części.")
                valid.append((source_type, source, stat, digest))
            except (VideoNotesError, OSError, wave.Error):
                issues.append(f"Nieczytelna albo zmieniona część part-{index:05d}.wav ({source_type}).")
                failed = True
        if failed or not valid:
            break
        if len({item[3] for item in valid}) != 1:
            issues.append(f"Konflikt różnych wersji part-{index:05d}.wav; odzysk kończy się wcześniej.")
            break
        # Favor canonical published file over a duplicate staged hardlink.
        valid.sort(key=lambda row: row[0] != "committed")
        kind, source, stat, digest = valid[0]
        selected_paths.append(source)
        selected.append({
            "index": index, "name": source.name, "source": kind,
            "duration_ms": stat["duration_ms"],
            "size_bytes": stat["size_bytes"], "sha256": digest,
            "original_journal_hash_verified": (
                kind == "committed" and isinstance(hashes, dict) and source.name in hashes
            ),
        })
    return {
        "schema": "videonotes-recording-recovery-v1",
        "session_status": state,
        "eligible_to_export": state == "needs_review" and bool(selected),
        "candidate_parts": selected,
        "candidate_count": len(selected),
        "pending_take_directories": pending,
        "issues": issues,
        "truncated_or_incomplete": True,
        "original_recording_preserved": True,
        "not_a_complete_lecture": True,
    }, selected_paths


def inspect_recoverable_recording(folder: Path) -> dict:
    """Return a privacy-safe preview; never modify original WAV or journal."""
    return _inspect_recovery(Path(folder))[0]


def salvage_recording(folder: Path, output: Path, *, confirm_stopped: bool = False) -> dict:
    """Explicitly export only a verified contiguous WAV prefix, never finish session.

    This is a COPY for use in the normal ASR pipeline, not a recovery of lost
    audio. The original recording and abandoned takes are left byte-identical.
    """
    if confirm_stopped is not True:
        raise VideoNotesError("Wymagane potwierdzenie --confirm-stopped, że FFmpeg nie nagrywa.")
    root = Path(folder).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if (output.suffix.lower() != ".wav" or output.is_symlink() or
            output.exists() or PATTERN.fullmatch(output.name)):
        raise VideoNotesError("Wybierz nowy plik WAV poza numeracją części nagrania.")
    report, paths = _inspect_recovery(root)
    if not report["eligible_to_export"]:
        raise VideoNotesError(
            "Można odzyskać wyłącznie czytelny początek sesji needs_review; "
            "sesja recording/paused/finished lub brak zdrowych WAV."
        )
    if not paths:
        raise VideoNotesError("Nie ma żadnych poprawnych próbek do odzyskania.")
    # Prevent writing inside a staging folder that might still belong to FFmpeg.
    if any(path.name.startswith(".vn-take-") for path in output.parents):
        raise VideoNotesError("Nie zapisuj odzyskanego WAV wewnątrz katalogu roboczego FFmpeg.")
    total_frames = 0
    for path in paths:
        if path.is_symlink():
            raise VideoNotesError("Źródło WAV zmieniono na dowiązanie.")
        with wave.open(str(path), "rb") as sound:
            total_frames += sound.getnframes()
    expected_size = 44 + total_frames * 2
    if expected_size >= MAX_WAV_BYTES:
        raise VideoNotesError("Odzykiwane audio przekracza limit WAV 4 GB; wymagany eksport częściami.")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if shutil.disk_usage(output.parent).free < expected_size:
            raise VideoNotesError("Za mało wolnego miejsca na kopię odzyskiwanego WAV.")
    except OSError as error:
        raise VideoNotesError("Nie można sprawdzić miejsca na dysku.") from error
    tempname: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".vn-salvage-",
            suffix=".wav.tmp", delete=False,
        ) as staged:
            tempname = staged.name
        with wave.open(tempname, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(16_000)
            target.setnframes(total_frames)
            for info, source in zip(report["candidate_parts"], paths):
                if source.is_symlink():
                    raise VideoNotesError("Źródło WAV zmieniło się podczas odzyskiwania.")
                with wave.open(str(source), "rb") as reader:
                    if (reader.getnchannels(), reader.getsampwidth(),
                            reader.getframerate()) != (1, 2, 16_000):
                        raise VideoNotesError("Nieprawidłowy format WAV podczas odzyskiwania.")
                    rest = reader.getnframes()
                    while rest:
                        amount = min(rest, 65_536)
                        frames = reader.readframes(amount)
                        if len(frames) != amount * 2:
                            raise VideoNotesError("Uszkodzona próbka podczas odzyskiwania WAV.")
                        target.writeframesraw(frames)
                        rest -= amount
                if sha256_file(source) != info["sha256"]:
                    raise VideoNotesError("Plik WAV został zmieniony w czasie odzyskiwania.")
        _inspect_single_wav(Path(tempname))
        # Verify the complete source selection and the recording journal AGAIN
        # after all copying. A previously read take might change while another
        # take is being copied, and the journal might be finalized externally.
        # Never present a stale/changed prefix as a safe salvage result.
        latest, latest_paths = _inspect_recovery(root)
        if latest != report or latest_paths != paths:
            raise VideoNotesError(
                "Pliki WAV lub dziennik nagrania zmieniły się podczas odzyskiwania; "
                "wyniku nie opublikowano."
            )
        try:
            os.link(tempname, output)
        except FileExistsError as error:
            raise VideoNotesError("Wynik WAV powstał równolegle; nie nadpisuję go.") from error
        except OSError as error:
            raise VideoNotesError("Nie udało się bezpiecznie udostępnić WAV bez nadpisania.") from error
    except (OSError, wave.Error) as error:
        raise VideoNotesError("Nie udało się odzyskać WAV, oryginały pozostają bez zmian.") from error
    finally:
        if tempname:
            Path(tempname).unlink(missing_ok=True)
    return {
        "schema": report["schema"],
        "output": str(output),
        "output_sha256": sha256_file(output),
        "duration_ms": total_frames * 1000 // 16_000,
        "copied_parts": report["candidate_count"],
        "issues": report["issues"],
        "original_recording_preserved": True,
        "source_session_status_unchanged": True,
        "truncated_or_incomplete": True,
        "not_a_complete_lecture": True,
        "requires_user_review": True,
    }
