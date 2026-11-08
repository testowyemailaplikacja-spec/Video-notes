"""Private GitHub Windows CI: build a real Inno installer with fake binaries.

This fixture is deliberately NOT a usable app/model and is never published.
It exercises installer generation only, not offline ASR or code signing.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from videonotes.bundle import create_internal_bundle, verify_internal_bundle
from videonotes.installer import build_internal_installer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for key in ("app", "ffmpeg", "ffprobe", "whisper", "model"):
        path = root / (key + (".bin" if key == "model" else ".exe"))
        path.write_bytes(b"VN-INTERNAL-SYNTHETIC-CI-NOT-A-REAL-BINARY:" + key.encode("ascii"))
        files[key] = path
    bundle = root / "verified-bundle"
    create_internal_bundle(**files, output=bundle, internal_only=True)
    assert verify_internal_bundle(bundle)["verified"]
    installer = root / "VideoNotes-INTERNAL-Setup.exe"
    report = build_internal_installer(
        bundle=bundle, iscc=args.iscc, output=installer, internal_only=True
    )
    assert report["offline_payload_included"] is True
    assert report["release_ready"] is False and report["signed"] is False
    assert installer.is_file() and installer.stat().st_size > 1024
    print(json.dumps({
        "synthetic_installer_compiled": True,
        "file_size_bytes": installer.stat().st_size,
        "private_bundle_files": 5,
        "release_ready": False,
        "signed": False,
        "model_genuine": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
