"""Fail-closed, append-only user decisions on individual local AI draft claims.

This records what a user DECLARES they reviewed, not proof of human identity
or factual accuracy. Draft, transcript and previous decisions stay immutable.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .contracts import sha256_file
from .errors import VideoNotesError
from .semantic_draft import verify_semantic_draft
from .storage import load_json

SCHEMA = "videonotes-semantic-claim-review-v1"
DECISION_SCHEMA = "videonotes-semantic-claim-decision-v1"
CLAIM_ID = re.compile(r"claim-[0-9]{6}-[0-9]{3}\Z", re.ASCII)
SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
MAX_CLAIMS = 240


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _new_file(path: Path, payload: bytes) -> None:
    """Publish once via a hard link on the same disk; never overwrite."""
    if path.exists() or path.is_symlink():
        raise VideoNotesError("Plik już istnieje; nie wolno nadpisać istniejącej decyzji.")
    with tempfile.TemporaryDirectory(prefix=".vn-new-review-", dir=path.parent) as temp:
        staging = Path(temp) / "new.json"
        with staging.open("wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(staging, path)
        except FileExistsError as error:
            raise VideoNotesError("Ktoś zapisał decyzję równolegle; nie nadpisuję.") from error
        except OSError as error:
            raise VideoNotesError("Nie udało się bezpiecznie zapisać nowej decyzji.") from error


def _draft(folder: Path, draft: Path) -> tuple[dict, dict, dict]:
    evidence = verify_semantic_draft(folder, draft)
    data = load_json(draft)
    claims = {}
    for section in data["sections"]:
        for claim in section["claims"]:
            ident = claim["id"]
            if not CLAIM_ID.fullmatch(ident) or ident in claims:
                raise VideoNotesError("Szkic zawiera nieprawidłowy lub powtórzony identyfikator.")
            claims[ident] = {"sha256": _hash_json(claim), "section_id": section["id"]}
    if not 1 <= len(claims) <= MAX_CLAIMS:
        raise VideoNotesError("Niewłaściwa liczba twierdzeń w szkicu.")
    return evidence, data, claims


def _report_folder(value: Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_symlink() or not path.is_dir():
        raise VideoNotesError("Katalog recenzji nie istnieje lub jest dowiązaniem symbolicznym.")
    decisions = path / "decisions"
    if decisions.is_symlink() or not decisions.is_dir():
        raise VideoNotesError("Nieprawidłowy folder decyzji.")
    return path


def init_semantic_review(folder: Path, draft: Path, review: Path) -> dict:
    """Create a new, empty review journal; no decisions are synthesized."""
    target = Path(review).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise VideoNotesError("Katalog recenzji już istnieje. Wybierz nowy.")
    evidence, data, claims = _draft(Path(folder), Path(draft))
    if len(str(target)) > 1200:
        raise VideoNotesError("Ścieżka katalogu recenzji jest zbyt długa.")
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": SCHEMA,
        "project_id": data["project_id"], "source_sha256": data["source_sha256"],
        "draft_sha256": evidence["document_sha256"], "claims": claims,
        "human_identity_independently_verified": False,
        "source_claims_factually_verified_by_software": False,
        "review_decisions": "locally-user-declared-one-time-per-claim",
    }
    # Refuse if either input changed while preparing the journal.
    if _draft(Path(folder), Path(draft))[0]["document_sha256"] != evidence["document_sha256"]:
        raise VideoNotesError("Szkic zmienił się podczas inicjalizacji oceny.")
    try:
        target.mkdir()
    except FileExistsError as error:
        raise VideoNotesError("Recenzję utworzono równolegle; nie nadpisuję.") from error
    (target / "decisions").mkdir()
    _new_file(target / "review.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return {"review": str(target), "claim_count": len(claims),
            "pending": len(claims), "user_decisions": 0,
            "human_review_independently_verified": False}


def _checked_review(folder: Path, draft: Path, review: Path) -> tuple[dict, dict, dict, dict, dict]:
    evidence, data, claims = _draft(Path(folder), Path(draft))
    directory = _report_folder(review)
    manifest_path = directory / "review.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise VideoNotesError("Nie znaleziono właściwego manifestu oceny.")
    manifest = load_json(manifest_path)
    if (not isinstance(manifest, dict) or set(manifest) != {
            "schema", "project_id", "source_sha256", "draft_sha256", "claims",
            "human_identity_independently_verified", "source_claims_factually_verified_by_software",
            "review_decisions"
        } or manifest["schema"] != SCHEMA or
            manifest["project_id"] != data["project_id"] or
            manifest["source_sha256"] != data["source_sha256"] or
            manifest["draft_sha256"] != evidence["document_sha256"] or
            manifest["claims"] != claims or
            manifest["human_identity_independently_verified"] is not False or
            manifest["source_claims_factually_verified_by_software"] is not False or
            manifest["review_decisions"] != "locally-user-declared-one-time-per-claim"):
        raise VideoNotesError("Manifest oceny jest obcy, zmieniony lub nieaktualny.")
    decisions: dict[str, dict] = {}
    for decision_file in (directory / "decisions").iterdir():
        name = decision_file.name
        if (decision_file.is_symlink() or not decision_file.is_file() or
                not name.endswith(".json") or name[:-5] not in claims):
            raise VideoNotesError("Katalog zawiera obcy plik lub dowiązanie; nie akceptuję oceny.")
        decision = load_json(decision_file)
        claim_id = name[:-5]
        if (not isinstance(decision, dict) or set(decision) != {
                "schema", "claim_id", "decision", "claim_sha256", "draft_sha256",
                "reviewer_label_user_supplied", "note", "user_confirmed",
                "identity_independently_verified", "factual_correctness_verified_by_software"
            } or decision["schema"] != DECISION_SCHEMA or
                decision["claim_id"] != claim_id or
                decision["decision"] not in ("approve", "reject") or
                decision["claim_sha256"] != claims[claim_id]["sha256"] or
                decision["draft_sha256"] != manifest["draft_sha256"] or
                not isinstance(decision["reviewer_label_user_supplied"], str) or
                not 1 <= len(decision["reviewer_label_user_supplied"].strip()) <= 60 or
                not isinstance(decision["note"], str) or
                len(decision["note"]) > 500 or "\x00" in decision["note"] or
                decision["user_confirmed"] is not True or
                decision["identity_independently_verified"] is not False or
                decision["factual_correctness_verified_by_software"] is not False):
            raise VideoNotesError("Zapis decyzji jest nieprawidłowy.")
        decisions[claim_id] = decision
    return evidence, data, claims, manifest, decisions


def mark_semantic_claim(folder: Path, draft: Path, review: Path, *,
                        claim_id: str, decision: str, reviewer: str,
                        note: str = "", confirm: bool = False) -> dict:
    """A conscious user action, immutable for this review directory."""
    if confirm is not True:
        raise VideoNotesError("Potwierdzenie decyzji wymaga wyraźnego --confirm.")
    if (not isinstance(claim_id, str) or not CLAIM_ID.fullmatch(claim_id) or
            decision not in ("approve", "reject") or not isinstance(reviewer, str) or
            not 1 <= len(reviewer.strip()) <= 60 or "\x00" in reviewer or
            not isinstance(note, str) or len(note) > 500 or "\x00" in note):
        raise VideoNotesError("Nieprawidłowy numer, decyzja, etykieta recenzenta lub notatka.")
    evidence, _, claims, manifest, decisions = _checked_review(folder, draft, review)
    if claim_id not in claims or claim_id in decisions:
        raise VideoNotesError("Nieznane lub wcześniej ocenione twierdzenie; nie nadpisuję decyzji.")
    record = {
        "schema": DECISION_SCHEMA, "claim_id": claim_id,
        "decision": decision, "claim_sha256": claims[claim_id]["sha256"],
        "draft_sha256": evidence["document_sha256"],
        "reviewer_label_user_supplied": reviewer.strip(), "note": note,
        "user_confirmed": True, "identity_independently_verified": False,
        "factual_correctness_verified_by_software": False,
    }
    path = _report_folder(review) / "decisions" / (claim_id + ".json")
    _new_file(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return {"claim_id": claim_id, "decision": decision, "saved": True,
            "human_review_independently_verified": False,
            "facts_verified_by_software": False}


def semantic_review_status(folder: Path, draft: Path, review: Path) -> dict:
    evidence, _, claims, _, decisions = _checked_review(folder, draft, review)
    approved = sum(d["decision"] == "approve" for d in decisions.values())
    rejected = len(decisions) - approved
    return {
        "schema": SCHEMA, "project_id": evidence["project_id"],
        "source_sha256": evidence["source_sha256"],
        "draft_sha256": evidence["document_sha256"],
        "total": len(claims), "approved_by_user": approved,
        "rejected_by_user": rejected, "pending": len(claims) - len(decisions),
        "all_claims_decided": len(claims) == len(decisions),
        "human_review_independently_verified": False,
        "facts_verified_by_software": False,
    }


def export_reviewed_semantic_markdown(folder: Path, draft: Path, review: Path,
                                      output: Path) -> dict:
    """Export approved claims only, only after *every* claim is decided."""
    status = semantic_review_status(folder, draft, review)
    if status["pending"]:
        raise VideoNotesError("Dokończ decyzje dla wszystkich twierdzeń przed eksportem.")
    if not status["approved_by_user"]:
        raise VideoNotesError("Brak zatwierdzonych twierdzeń do eksportu.")
    _, data, _, _, decisions = _checked_review(folder, draft, review)
    lines = [
        "# Lokalna notatka po ręcznym oznaczeniu twierdzeń", "",
        "> Użytkownik deklaruje ocenę cytatów. Aplikacja nie weryfikuje",
        "> tożsamości recenzenta ani prawdziwości parafraz.", "",
    ]
    for section in data["sections"]:
        accepted = [claim for claim in section["claims"]
                    if decisions[claim["id"]]["decision"] == "approve"]
        if not accepted:
            continue
        lines.extend(["## Fragment " + str(section["window_index"]), ""])
        for claim in accepted:
            lines.extend(["### Twierdzenie zatwierdzone przez użytkownika", ""])
            for part in claim["text"].splitlines():
                lines.append("    " + part)
            lines.append("")
            for citation in claim["citations"]:
                lines.append("Źródło " + citation["segment_id"] + " · " +
                             str(citation["start_ms"]) + "–" + str(citation["end_ms"]) + " ms")
                lines.append("")
                for part in citation["text"].splitlines():
                    lines.append("    " + part)
                lines.append("")
    content = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    # Refuse to export if any decision, source or draft has changed.
    if semantic_review_status(folder, draft, review) != status:
        raise VideoNotesError("Decyzje lub źródło zmieniły się podczas eksportu.")
    target = Path(output).expanduser().absolute()
    if target.suffix.lower() != ".md" or target.exists() or target.is_symlink():
        raise VideoNotesError("Wybierz nowy plik .md bez nadpisywania.")
    target.parent.mkdir(parents=True, exist_ok=True)
    _new_file(target, content)
    return {"output": str(target), "approved_by_user": status["approved_by_user"],
            "rejected_by_user": status["rejected_by_user"],
            "human_review_independently_verified": False,
            "facts_verified_by_software": False}
