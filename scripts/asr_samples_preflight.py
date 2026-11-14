"""Local PL/EN reference input probe; never uploads or outputs recordings."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videonotes.asr_sample_manifest import inspect_asr_samples
from videonotes.errors import VideoNotesError


def main() -> int:
    parser = argparse.ArgumentParser()
    for lang in ("pl", "en"):
        parser.add_argument("--" + lang + "-media", required=True, type=Path)
        parser.add_argument("--" + lang + "-reference", required=True, type=Path)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    try:
        report = inspect_asr_samples({
            "pl": (args.pl_media, args.pl_reference),
            "en": (args.en_media, args.en_reference),
        }, ffprobe=args.ffprobe)
    except (VideoNotesError, OSError, TypeError, ValueError):
        print("Private ASR input preflight failed; inspect files locally.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
