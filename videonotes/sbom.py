"""Offline SPDX 2.3 file inventory for a verified INTERNAL bundle.

This records component hashes and explicitly unknown licenses; it is not a
legal opinion, authenticity attestation or permission to publish a bundle.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .bundle import BUNDLE_FILES, verify_internal_bundle
from .errors import VideoNotesError


def create_internal_sbom(bundle: Path, output: Path) -> dict:
    root, destination = Path(bundle).expanduser(), Path(output).expanduser().absolute()
    verified = verify_internal_bundle(root)
    if verified["distribution"] != "internal-only":
        raise VideoNotesError("SBOM dotyczy wyłącznie zweryfikowanego pakietu wewnętrznego.")
    if destination.suffix.lower() != ".json":
        raise VideoNotesError("Raport inwentarza musi być plikiem JSON.")
    if destination.exists() or destination.is_symlink():
        raise VideoNotesError("Raport SBOM już istnieje. Nie nadpisuję go.")
    try:
        destination.resolve().relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise VideoNotesError("Raport SBOM trzeba zapisać poza chronionym katalogiem pakietu.")

    manifest = json.loads((root / "bundle-manifest.json").read_text(encoding="utf-8"))
    files = []
    relations = []
    for index, name in enumerate(sorted(BUNDLE_FILES), 1):
        spec = manifest["files"][name]
        spdx_id = f"SPDXRef-File-{index}"
        files.append({
            "SPDXID": spdx_id, "fileName": "./" + name,
            "checksums": [{"algorithm": "SHA256", "checksumValue": spec["sha256"]}],
            "fileTypes": ["BINARY"],
            "licenseConcluded": "NOASSERTION", "licenseInfoInFiles": ["NOASSERTION"],
            "copyrightText": "NOASSERTION",
            "comment": "Private test component; license and origin are NOT verified.",
        })
        relations.append({
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relatedSpdxElement": spdx_id,
            "relationshipType": "DESCRIBES",
        })
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()
    report = {
        "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "Video Notes internal test bundle file inventory",
        "documentNamespace": "https://example.invalid/spdx/videonotes-internal/" + fingerprint,
        "creationInfo": {
            "creators": ["Tool: videonotes-local"],
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "comment": "Automatically calculated hashes. No license, security or redistribution clearance.",
        },
        "files": files, "relationships": relations,
        "annotations": [{
            "annotationDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "annotationType": "OTHER", "annotator": "Tool: videonotes-local",
            "comment": "INTERNAL ONLY; NOASSERTION for all component licenses; unsigned, no hardware acceptance.",
        }],
    }
    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    # Reject changed or corrupted binaries immediately before publication.
    verify_internal_bundle(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".vn-sbom-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)  # Never replace an existing report.
        except FileExistsError as error:
            raise VideoNotesError("Raport SBOM powstał równolegle; niczego nie nadpisano.") from error
        except OSError as error:
            raise VideoNotesError("System plików nie pozwala bezpiecznie zapisać nowego SBOM.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "output": str(destination), "spdxVersion": "SPDX-2.3",
        "file_count": len(files), "sha256": hashlib.sha256(payload).hexdigest(),
        "distribution": "internal-only", "license_verified": False,
        "signature_verified": False, "release_ready": False,
    }
