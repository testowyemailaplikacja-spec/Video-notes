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
from .microphone import record_microphone, recording_status, list_microphone_devices, join_finished_recording
from .audio_diagnostics import analyze_finished_recording
from .notes import generate_basic_notes, edit_note_point, export_basic_notes, export_basic_notes_text, export_basic_notes_docx
from .advanced_notes import export_advanced_outline
from .study_guide import export_study_guide, verify_study_guide
from .pdf_export import export_basic_notes_pdf
from .note_revisions import regenerate_basic_notes, list_note_versions, restore_note_version, recover_interrupted_note_update, notes_lock_status, recover_stale_notes_lock
from .quality import compare_text_files
from .asr_lab import run_real_benchmark
from .backup import create_backup, restore_backup, relink_backup
from .bundle import create_internal_bundle, verify_internal_bundle
from .installer import build_internal_installer
from .pipeline import create_project, transcribe_project, transcription_lock_status, recover_stale_transcription_lock
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
    lock_status = sub.add_parser("lock-status", help="Sprawdź, czy blokada transkrypcji jest aktywna, czy osierocona")
    lock_status.add_argument("project", type=Path)
    lock_recover = sub.add_parser("lock-recover", help="Usuń tylko potwierdzoną osieroconą blokadę po awarii")
    lock_recover.add_argument("project", type=Path)
    lock_recover.add_argument("--confirm", action="store_true", help="Jawnie potwierdź bezpieczne odzyskiwanie")
    exports = sub.add_parser("export", help="Zapisz TXT/SRT/VTT/JSON bez zmiany surowego tekstu")
    exports.add_argument("project", type=Path)
    edit = sub.add_parser("edit", help="Zapisz poprawkę segmentu, zachowując surową transkrypcję")
    edit.add_argument("project", type=Path)
    edit.add_argument("--segment", required=True)
    edit.add_argument("--text", required=True)
    status = sub.add_parser("status", help="Pokaż postęp i identyfikatory segmentów")
    status.add_argument("project", type=Path)
    notes = sub.add_parser("notes", help="Utwórz źródłowe, ekstrakcyjne notatki podstawowe (VN-02)")
    notes.add_argument("project", type=Path)
    notes.add_argument("--window-minutes", type=int, default=5)
    notes.add_argument("--points", type=int, default=6)
    note_edit = sub.add_parser("notes-edit", help="Popraw punkt notatki bez modyfikacji cytatu źródłowego")
    note_edit.add_argument("project", type=Path)
    note_edit.add_argument("--point", required=True)
    note_edit.add_argument("--text", required=True)
    regen = sub.add_parser("notes-regenerate", help="Odbuduj cytaty z aktualnej transkrypcji, zachowując ręczne poprawki i historię")
    regen.add_argument("project", type=Path)
    regen.add_argument("--window-minutes", type=int, default=5)
    regen.add_argument("--points", type=int, default=6)
    versions = sub.add_parser("notes-history", help="Pokaż zapisane wersje lokalne bez treści notatek")
    versions.add_argument("project", type=Path)
    revert = sub.add_parser("notes-restore", help="Przywróć zgodną ze źródłem wersję notatek")
    revert.add_argument("project", type=Path)
    revert.add_argument("--revision", required=True)
    recover = sub.add_parser("notes-recover", help="Sprawdź i bezpiecznie dokończ kontrolę przerwanej aktualizacji notatek")
    recover.add_argument("project", type=Path)
    recover.add_argument("--confirm", action="store_true", help="Wymagane potwierdzenie przed przywróceniem wcześniejszej wersji")
    notes_lock = sub.add_parser("notes-lock-status", help="Pokaż status PID blokady notatek po awarii")
    notes_lock.add_argument("project", type=Path)
    notes_lock_recover = sub.add_parser("notes-lock-recover", help="Usuń tylko sprawdzoną osieroconą blokadę notatek")
    notes_lock_recover.add_argument("project", type=Path)
    notes_lock_recover.add_argument("--confirm", action="store_true", help="Wymagana odrębna zgoda")
    note_export = sub.add_parser("notes-export", help="Zapisz lokalny notes-basic.md")
    note_export.add_argument("project", type=Path)
    note_export.add_argument("--txt", action="store_true", help="Dodatkowo zapisz notes-basic.txt, bez zmian w źródle")
    note_export.add_argument("--docx", action="store_true", help="Dodatkowo zapisz offline notes-basic.docx z cytatami i poprawkami")
    note_export.add_argument("--pdf", action="store_true", help="Opcjonalny lokalny PDF z zainstalowanym LibreOffice")
    note_export.add_argument("--office", default="libreoffice", help="Ścieżka do lokalnego libreoffice/soffice.exe (tylko PDF)")
    advanced = sub.add_parser("advanced-notes", help="Źródłowy konspekt wielopoziomowy bez dopisywania faktów (VN-03)")
    advanced.add_argument("project", type=Path)
    advanced.add_argument("--template", choices=["lecture", "tutorial", "meeting", "study"], default="lecture")
    advanced.add_argument("--detail", choices=["brief", "standard", "full"], default="standard")
    advanced.add_argument("--section-minutes", type=int, default=10)
    advanced.add_argument("--docx", action="store_true", help="Dodatkowo zapisz lokalny DOCX z cytatami (bez sieci)")
    advanced.add_argument("--pdf", action="store_true", help="Opcjonalny lokalny PDF z zainstalowanym LibreOffice")
    advanced.add_argument("--office", default="libreoffice", help="Ścieżka do lokalnego libreoffice/soffice.exe (tylko PDF)")
    study = sub.add_parser("study-guide", help="Przewodnik do nauki: cytaty, powtarzane pojęcia, przykłady i pytania ze źródeł")
    study.add_argument("project", type=Path)
    study.add_argument("--section-minutes", type=int, default=5)
    study.add_argument("--detail", choices=["brief", "standard", "full"], default="standard")
    study.add_argument("--docx", action="store_true", help="Dodatkowo lokalny DOCX ze źródłami")
    study.add_argument("--pdf", action="store_true", help="Opcjonalny PDF przy lokalnym LibreOffice")
    study.add_argument("--office", default="libreoffice", help="Lokalne LibreOffice (tylko PDF)")
    study_check = sub.add_parser("study-verify", help="Sprawdź cytaty zapisanej notatki przeciw aktualnej transkrypcji, bez modyfikowania danych")
    study_check.add_argument("project", type=Path)
    study_check.add_argument("--file", type=Path, help="Opcjonalny lokalny plik przewodnika JSON")
    real = sub.add_parser("benchmark-real", help="Uruchom lokalne whisper.cpp i faster-whisper na tym samym audio OBS (bez chmury)")
    real.add_argument("source", type=Path)
    real.add_argument("--reference", type=Path, required=True, help="Ręcznie sprawdzona transkrypcja wybranego fragmentu")
    real.add_argument("--cpp-executable", required=True)
    real.add_argument("--cpp-model", type=Path, required=True)
    real.add_argument("--faster-model-dir", type=Path, required=True)
    real.add_argument("--language", default="pl", choices=["pl", "en", "auto"])
    real.add_argument("--threads", type=int, default=4)
    real.add_argument("--stream", type=int)
    real.add_argument("--start-seconds", type=int, default=0)
    real.add_argument("--duration-seconds", type=int, default=120)
    real.add_argument("--ffmpeg", default="ffmpeg")
    real.add_argument("--ffprobe", default="ffprobe")
    real.add_argument("--output", type=Path, required=True)
    benchmark = sub.add_parser("benchmark", help="Porównaj WER/CER gotowych plików TXT, bez nagrywania lub wysyłki danych")
    benchmark.add_argument("--reference", required=True, type=Path)
    benchmark.add_argument("--candidate", required=True, action="append", help="etykieta=plik.txt; wymaga prawdziwych wyników ASR")
    benchmark.add_argument("--output", type=Path)
    backup = sub.add_parser("backup", help="Utwórz lokalną kopię projektu bez audio i modelu")
    backup.add_argument("project", type=Path)
    backup.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore", help="Przywróć projekt z bezpiecznego archiwum do nowego katalogu")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--project", type=Path, required=True)
    relink = sub.add_parser("relink", help="Po odtworzeniu podłącz lokalne pliki o tych samych SHA-256")
    relink.add_argument("project", type=Path)
    relink.add_argument("--source", type=Path, required=True)
    relink.add_argument("--model", type=Path, required=True)
    relink.add_argument("--whisper-cli", required=True)
    relink.add_argument("--ffprobe", default="ffprobe")
    devices = sub.add_parser("record-devices", help="Wypisz lokalne urządzenia mikrofonowe Windows")
    devices.add_argument("--ffmpeg", default="ffmpeg")
    mic = sub.add_parser("record-mic", help="Nagraj lokalny mikrofon Windows jako WAV")
    mic.add_argument("--device", required=True, help="Dokładna nazwa urządzenia DirectShow")
    mic.add_argument("--output", required=True, type=Path, help="Nowy katalog nagrania; istniejące są chronione")
    mic.add_argument("--consent", required=True, action="store_true", help="Potwierdź świadome włączenie mikrofonu")
    mic.add_argument("--system-device", help="Opcjonalne urządzenie dźwięku systemowego/loopback DirectShow")
    mic.add_argument("--consent-system", action="store_true", help="Osobna zgoda na nagrywanie dźwięku systemowego")
    mic.add_argument("--max-minutes", type=int, help="Opcjonalny limit 1–1440 minut")
    mic.add_argument("--ffmpeg", default="ffmpeg")
    mic_status = sub.add_parser("record-status", help="Sprawdź lokalne pliki nagrania i dziennik sesji")
    mic_status.add_argument("folder", type=Path)
    mic_analyze = sub.add_parser("record-analyze", help="Sprawdź lokalnie głośność, ciszę i przesterowanie ukończonego WAV")
    mic_analyze.add_argument("folder", type=Path, help="Katalog ukończonej sesji mikrofonowej")
    mic_join = sub.add_parser("record-join", help="Połącz ukończoną sesję z wielu części WAV bez nadpisywania")
    mic_join.add_argument("folder", type=Path, help="Katalog zakończonego nagrania z recording.json")
    mic_join.add_argument("--output", required=True, type=Path, help="Nowy wynikowy WAV; wymaga dodatkowego wolnego miejsca")
    bundle = sub.add_parser("bundle-dev", help="Złóż prywatny pakiet Windows z własnych binariów i modelu (nie wydanie)")
    for flag in ("app", "ffmpeg", "ffprobe", "whisper", "model", "output"):
        bundle.add_argument("--" + flag, required=True, type=Path)
    bundle.add_argument("--internal-only", required=True, action="store_true", help="Potwierdź, że nie rozpowszechniasz niezweryfikowanego pakietu")
    setup = sub.add_parser("installer-dev", help="Zbuduj prywatny pełny offline instalator EXE z wcześniej sprawdzonego pakietu")
    setup.add_argument("--bundle", required=True, type=Path, help="Lokalny pakiet bundle-dev zawierający model i narzędzia")
    setup.add_argument("--iscc", required=True, type=Path, help="Ścieżka do zainstalowanego Inno Setup ISCC.exe")
    setup.add_argument("--output", required=True, type=Path, help="Nowy plik Windows setup .exe")
    setup.add_argument("--internal-only", required=True, action="store_true", help="Wymagana zgoda na prywatny test bez redystrybucji")
    check_bundle = sub.add_parser("bundle-verify", help="Sprawdź lokalne SHA-256 przed uruchomieniem prywatnego pakietu Windows")
    check_bundle.add_argument("folder", type=Path)
    sub.add_parser("gui", help="Uruchom prosty interfejs Windows/Tkinter")
    return cmd


def _progress(done: int, total: int) -> None:
    print(f"Zapisane fragmenty: {done}/{total}", file=sys.stderr, flush=True)


def _configure_console_unicode() -> None:
    """Avoid Windows legacy cp1252 crashes when CLI prints Polish text."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_console_unicode()
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
        elif args.action == "lock-status":
            read_project(args.project)
            print(json.dumps(transcription_lock_status(args.project), ensure_ascii=False))
        elif args.action == "lock-recover":
            print(json.dumps(recover_stale_transcription_lock(args.project, confirm=args.confirm), ensure_ascii=False))
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
        elif args.action == "notes":
            note = generate_basic_notes(args.project, window_minutes=args.window_minutes, points_per_section=args.points)
            result = export_basic_notes(args.project)
            print(f"Utworzono {len(note['sections'])} sekcji z cytatami: {result}")
        elif args.action == "notes-edit":
            edit_note_point(args.project, args.point, args.text)
            print(f"Zaktualizowano {export_basic_notes(args.project)}")
        elif args.action == "notes-regenerate":
            report = regenerate_basic_notes(args.project, window_minutes=args.window_minutes, points_per_section=args.points)
            path = export_basic_notes(args.project)
            print(json.dumps({**report, "notes_export": str(path)}, ensure_ascii=False, indent=2))
        elif args.action == "notes-history":
            print(json.dumps(list_note_versions(args.project), ensure_ascii=False, indent=2))
        elif args.action == "notes-restore":
            previous = restore_note_version(args.project, args.revision)
            print(json.dumps({"previous_version_backup": previous, "notes_export": str(export_basic_notes(args.project))}, ensure_ascii=False))
        elif args.action == "notes-recover":
            print(json.dumps(recover_interrupted_note_update(args.project, confirm=args.confirm), ensure_ascii=False))
        elif args.action == "notes-lock-status":
            read_project(args.project)
            print(json.dumps(notes_lock_status(args.project), ensure_ascii=False))
        elif args.action == "notes-lock-recover":
            print(json.dumps(recover_stale_notes_lock(args.project, confirm=args.confirm), ensure_ascii=False))
        elif args.action == "notes-export":
            # PDF is pre-rendered in a private temporary folder; missing optional
            # LibreOffice leaves all other existing exports unchanged.
            if args.pdf:
                print(export_basic_notes_pdf(args.project, office=args.office))
            if args.docx:
                print(export_basic_notes_docx(args.project))
            if args.txt:
                print(export_basic_notes_text(args.project))
            print(export_basic_notes(args.project))
        elif args.action == "advanced-notes":
            for path in export_advanced_outline(args.project, template=args.template, detail=args.detail, section_minutes=args.section_minutes,
                                                include_docx=args.docx, include_pdf=args.pdf, office=args.office):
                print(path)
        elif args.action == "study-guide":
            for path in export_study_guide(
                args.project, section_minutes=args.section_minutes,
                detail=args.detail, include_docx=args.docx,
                include_pdf=args.pdf, office=args.office,
            ):
                print(path)
        elif args.action == "study-verify":
            print(json.dumps(verify_study_guide(args.project, document=args.file),
                             ensure_ascii=False, indent=2))
        elif args.action == "benchmark-real":
            report = run_real_benchmark(args.source, args.reference, cpp_executable=args.cpp_executable,
                                        cpp_model=args.cpp_model, faster_model_dir=args.faster_model_dir,
                                        language=args.language, threads=args.threads, stream=args.stream,
                                        start_seconds=args.start_seconds, duration_seconds=args.duration_seconds,
                                        ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, output=args.output)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.action == "benchmark":
            candidates = {}
            for item in args.candidate:
                if "=" not in item:
                    raise VideoNotesError("Użyj --candidate etykieta=plik.txt")
                label, filename = item.split("=", 1)
                if not filename or label in candidates:
                    raise VideoNotesError("Pusta ścieżka lub powielona etykieta benchmarku.")
                candidates[label] = Path(filename)
            print(json.dumps(compare_text_files(args.reference, candidates, output=args.output), ensure_ascii=False, indent=2))
        elif args.action == "backup":
            print(create_backup(args.project, args.output))
            print("Kopia nie zawiera nagrań ani modelu. Zachowaj pliki źródłowe osobno.", file=sys.stderr)
        elif args.action == "restore":
            print(restore_backup(args.archive, args.project))
            print("Projekt przywrócony. Przed wznowieniem ASR użyj relink.", file=sys.stderr)
        elif args.action == "relink":
            relink_backup(args.project, args.source, args.model, whisper_cli=args.whisper_cli, ffprobe=args.ffprobe)
            print("Potwierdzono SHA-256 nagrania i modelu; projekt jest podłączony lokalnie.")
        elif args.action == "record-devices":
            print(json.dumps(list_microphone_devices(args.ffmpeg), ensure_ascii=False, indent=2))
        elif args.action == "record-mic":
            if args.max_minutes is not None and not 1 <= args.max_minutes <= 1440:
                raise VideoNotesError("Limit nagrywania musi wynosić 1–1440 minut.")
            result = record_microphone(args.device, args.output, consent=args.consent,
                                       ffmpeg=args.ffmpeg, max_seconds=args.max_minutes * 60 if args.max_minutes is not None else None,
                                       system_device=args.system_device, system_consent=args.consent_system)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.action == "record-status":
            print(json.dumps(recording_status(args.folder), ensure_ascii=False, indent=2))
        elif args.action == "record-analyze":
            print(json.dumps(analyze_finished_recording(args.folder), ensure_ascii=False, indent=2))
        elif args.action == "record-join":
            print(join_finished_recording(args.folder, args.output))
        elif args.action == "bundle-dev":
            report = create_internal_bundle(app=args.app, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
                                            whisper=args.whisper, model=args.model, output=args.output,
                                            internal_only=args.internal_only)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.action == "installer-dev":
            print(json.dumps(build_internal_installer(
                bundle=args.bundle, iscc=args.iscc, output=args.output,
                internal_only=args.internal_only
            ), ensure_ascii=False, indent=2))
        elif args.action == "bundle-verify":
            print(json.dumps(verify_internal_bundle(args.folder), ensure_ascii=False, indent=2))
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
