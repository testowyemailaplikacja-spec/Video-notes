"""Verify a PRIVATE Inno setup installed exact synthetic fixture bytes.

The installed folder contains an Inno uninstaller, so it is not identical to
the bare bundle directory and verify_internal_bundle() is not appropriate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from videonotes.bundle import BUNDLE_FILES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("installed", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.bundle / "bundle-manifest.json").read_text("utf-8"))
    assert manifest["distribution"] == "internal-only"
    assert set(manifest["files"]) == BUNDLE_FILES
    for relative in sorted(BUNDLE_FILES):
        installed = args.installed / relative
        assert installed.is_file() and not installed.is_symlink()
        expected = manifest["files"][relative]
        data = installed.read_bytes()
        assert len(data) == expected["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]
    for helper in ("INTERNAL-ONLY.txt", "START-VIDEO-NOTES.cmd",
                   "bundle-manifest.json"):
        assert (args.bundle / helper).read_bytes() == (args.installed / helper).read_bytes()
    assert (args.installed / "unins000.exe").is_file()
    print("PASS: genuine Inno installed all 5 exact synthetic payload files + private warning and uninstaller")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
