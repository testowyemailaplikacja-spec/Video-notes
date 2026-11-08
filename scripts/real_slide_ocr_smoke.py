"""Actual local FFmpeg+Tesseract smoke on synthetic original title slide.

No downloads during runtime, no user media, and no human acceptance claim.
CI installs independently packaged FFmpeg and Tesseract before this test.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from videonotes.contracts import sha256_file
from videonotes.media import probe
from videonotes.slide_ocr import extract_slide_ocr, verify_slide_ocr
from videonotes.storage import save_json


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vn-slide-ocr-real-") as name:
        root = Path(name)
        video = root / "synthetic-title.mkv"
        title_font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        if not title_font.is_file():
            raise RuntimeError("Required bundled DejaVu font not found on CI runner")
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=white:s=1280x720:r=2:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=3",
            "-vf", "drawtext=fontfile=" + str(title_font) +
                   ":text='ROUTER DHCP':fontcolor=black:fontsize=94:x=80:y=200",
            "-t", "3", "-c:v", "mpeg4", "-q:v", "2", "-c:a", "pcm_s16le",
            str(video)
        ], check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        source = probe(video)
        audio = source["audio_streams"][0]["index"]
        project = root / "project"
        project.mkdir()
        save_json(project / "project.json", {
            "schema": "videonotes-project-v1", "id": "original-synthetic-slide-ci",
            "source": {"path": str(video), "size_bytes": video.stat().st_size,
                       "sha256": sha256_file(video), "duration_ms": source["duration_ms"],
                       "stream_index": audio},
            "processing": {"engine": "whisper.cpp", "language": "en",
                           "chunk_ms": 120000, "model_path": "not-used-in-ocr",
                           "model_sha256": "a" * 64, "whisper_cli": "not-used"},
        })
        save_json(project / "transcript.json", {
            "schema": "videonotes-transcript-v1", "project_id": "original-synthetic-slide-ci",
            "completed_chunks": [0], "segments": [],
        })
        output = root / "slide-ocr.json"
        details = extract_slide_ocr(project, output, language="eng", interval_seconds=10,
                                    max_frames=1)
        report = json.loads(output.read_text(encoding="utf-8"))
        if not report["frames"] or "ROUTER" not in report["frames"][0]["ocr_text"].upper():
            raise RuntimeError("Real Tesseract did not recover the visual slide text")
        verified = verify_slide_ocr(project, output)
        if not verified["verified_source"] or verified["ocr_accuracy_verified"] is not False:
            raise RuntimeError("Slide source integrity or uncertainty flags failed")
        print(json.dumps({
            "schema": "videonotes-real-slide-ocr-smoke-v1",
            "original_generated_video": True,
            "real_ffmpeg": True, "real_tesseract": True,
            "language": "eng",
            "frames": details["frames"], "human_reviewed": False,
            "physical_windows_tested": False, "real_user_slides_tested": False,
            "source_preserved": True,
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
