"""Standalone offline FFmpeg build-flag review preflight (no legal approval)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videonotes.errors import VideoNotesError
from videonotes.ffmpeg_license import inspect_ffmpeg_build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    try:
        result = inspect_ffmpeg_build(args.ffmpeg)
    except VideoNotesError as error:
        print("Local FFmpeg preflight failed: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
