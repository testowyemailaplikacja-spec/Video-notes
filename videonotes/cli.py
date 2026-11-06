"""Offline CLI for media discovery, transcription/resume, edits, and exports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import VideoNotesError
from .exports import edit_segment, export_project
from .media import probe
from .pipeline import create_project, transcribe_project
from .storage import read_project


def parser() -> argparse.ArgumentParser:
    cmd = argparse.ArgumentParser(prog="videonotes", description="Video Notes: lokalna transkrypcja nagrań OBS, bez konta i chmury")
    cmd.add_argument("--version", action="version", version=f"Video Notes {__version__}")
    sub = cmd.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("inspect", help="Pokaż rzeczywiste ścieżki audio FFprobe")
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--ffprobe", default="ffprobe")
    trans = sub.add_parser("transcribe", help="Utwórz lokalny projekt i przetwarzaj fragmentami")
    trans.add_argument("source", type=Path)
    trans.add_argument("--project", required=True, type=Path)
    trans.add_argument("--model", required=True, type=Path, help="Lokalny, uprzednio pobrany model .bin")
    trans.add_argument("--whisper-cli", default="whisper-cli", help="Lokalny plik wykonywalny whisper.cpp")
    trans.add_argument("--stream", type=int, help="Globalny indeks strumienia z inspect; wymagany dla wielu ścieżek")
    trans.add_argument("--language", default="pl", choices=["pl", "en", "auto"])
    trans.add_argument("--chunk-seconds", type=int, default=30)
    trans.add_argument("--ffmpeg", default="ffmpeg")
    trans.add_argument("--ffprobe", default="ffprobe")
    resume = sub.add_parser("resume", help="Kontynuuj tylko niezapisane fragmenty")
    resume.add_argument("project", type=Path)
    resume.add_argument("--ffmpeg", default="ffmpeg")
    resume.add_argument("--ffprobe", default="ffprobe")
    exports = sub.add_parser("export", help="Zapisz TXT/SRT/VTT/JSON bez zmiany surowego tekstu")
    exports.add_argument("project", type=Path)
    edit = sub.add_parser("edit", help="Zapisz poprawkę segmentu, zachowując surową transkrypcję")
    edit.add_argument("project", type=Path)
    edit.add_argument("--segment", required=True)
    edit.add_argument("--text", required=True)
    status = sub.add_parser("status", help="Pokaż postęp i identyfikatory segmentów")
    status.add_argument("project", type=Path)
    sub.add_parser("gui", help="Uruchom prosty interfejs Windows/Tkinter")
    return cmd


def _progress(done: int, total: int) -> None:
    print(f"Zapisane fragmenty: {done}/{total}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "inspect":
            print(json.dumps(probe(args.source, args.ffprobe), ensure_ascii=False, indent=2))
        elif args.action == "transcribe":
            create_project(args.source, args.project, model=args.model, whisper_cli=args.whisper_cli, language=args.language,
                           stream=args.stream, chunk_ms=args.chunk_seconds * 1000, ffprobe=args.ffprobe)
            transcribe_project(args.project, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, progress=_progress)
            export_project(args.project)
            print(f"Transkrypcja zakończona: {args.project}")
        elif args.action == "resume":
            transcribe_project(args.project, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, progress=_progress)
            export_project(args.project)
            print(f"Wznowiono i zapisano: {args.project}")
        elif args.action == "edit":
            edit_segment(args.project, args.segment, args.text)
            export_project(args.project)
            print("Poprawka zapisana oddzielnie od surowego wyniku ASR.")
        elif args.action == "export":
            for target in export_project(args.project):
                print(target)
        elif args.action == "status":
            project, transcript, edits = read_project(args.project)
            total = (project["source"]["duration_ms"] + project["processing"]["chunk_ms"] - 1) // project["processing"]["chunk_ms"]
            print(json.dumps({"project_id": project["id"], "completed_chunks": len(transcript["completed_chunks"]),
                              "total_chunks": total, "segment_count": len(transcript["segments"]),
                              "edited_segments": len(edits["edits"]), "segments": transcript["segments"]}, ensure_ascii=False, indent=2))
        elif args.action == "gui":
            from .gui import launch
            launch()
        return 0
    except VideoNotesError as error:
        print(f"Video Notes: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Video Notes: przerwano. Użyj resume do kontynuowania.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
