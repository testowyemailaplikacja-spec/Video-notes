from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
from videonotes.note_revisions import (_begin_transaction, _load_snapshot, list_note_versions,
                                       regenerate_basic_notes, restore_note_version,
                                       recover_interrupted_note_update)
from videonotes.notes import (generate_basic_notes, edit_note_point, read_basic_notes,
                              render_basic_markdown)
from videonotes.storage import read_project, save_json


class NotesVersionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        fixture(self.folder)
        self.notes = generate_basic_notes(self.folder, window_minutes=1, points_per_section=2)
        self.point = self.notes["sections"][0]["points"][0]["id"]

    def test_regenerate_after_transcription_edit_retains_manual_work(self):
        edit_note_point(self.folder, self.point, "Moja poprawka na temat routera")
        raw_before = (self.folder / "transcript.json").read_bytes()
        changes = {"schema": "videonotes-edits-v1",
                   "edits": {"c0000000-s00000": "Nowa, poprawiona treść wypowiedzi o sieciach."}}
        save_json(self.folder / "edits.json", changes)
        with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
            read_basic_notes(self.folder)
        result = regenerate_basic_notes(self.folder, window_minutes=1, points_per_section=2)
        self.assertTrue(result["changed"])
        self.assertEqual(result["kept_edits"], 1)
        self.assertEqual(result["unmatched_edits"], 0)
        self.assertEqual(len(list_note_versions(self.folder)), 1)
        refreshed, overrides = read_basic_notes(self.folder)
        self.assertEqual(refreshed["sections"][0]["points"][0]["text"], "Nowa, poprawiona treść wypowiedzi o sieciach.")
        self.assertEqual(overrides["edits"][self.point], "Moja poprawka na temat routera")
        self.assertIn("Moja poprawka", render_basic_markdown(self.folder))
        self.assertEqual((self.folder / "transcript.json").read_bytes(), raw_before)
        self.assertEqual(regenerate_basic_notes(self.folder, window_minutes=1, points_per_section=2)["changed"], False)

    def test_restore_previous_version_when_source_matches(self):
        edit_note_point(self.folder, self.point, "Ręczna poprawka 1")
        a = regenerate_basic_notes(self.folder, window_minutes=2, points_per_section=2)
        self.assertTrue(a["changed"])
        self.assertEqual(len(read_basic_notes(self.folder)[0]["sections"]), 1)
        undo_snapshot = restore_note_version(self.folder, a["revision"])
        self.assertEqual(len(read_basic_notes(self.folder)[0]["sections"]), 2)
        self.assertEqual(read_basic_notes(self.folder)[1]["edits"][self.point], "Ręczna poprawka 1")
        self.assertNotEqual(undo_snapshot, a["revision"])
        self.assertEqual(len(list_note_versions(self.folder)), 2)

    def test_snapshot_reader_keeps_two_item_api_for_backup(self):
        result = regenerate_basic_notes(self.folder, window_minutes=2)
        original_notes, original_edits = _load_snapshot(self.folder, result["revision"])
        self.assertEqual(original_notes["project_id"], self.notes["project_id"])
        self.assertEqual(original_edits["edits"], {})
        metadata = _load_snapshot(self.folder, result["revision"], include_created_at=True)
        self.assertEqual(len(metadata), 3)
        self.assertEqual(metadata[:2], (original_notes, original_edits))

    def test_history_has_created_at_and_is_ordered_newest_first(self):
        first = regenerate_basic_notes(self.folder, window_minutes=2, points_per_section=2)
        second = regenerate_basic_notes(self.folder, window_minutes=1, points_per_section=2)
        self.assertTrue(first["changed"] and second["changed"])
        versions = list_note_versions(self.folder)
        self.assertEqual([item["revision"] for item in versions],
                         [second["revision"], first["revision"]])
        for version in versions:
            moment = datetime.fromisoformat(version["created_at"])
            self.assertIsNotNone(moment.tzinfo)
            self.assertEqual(moment.utcoffset().total_seconds(), 0)
            self.assertEqual(version["manual_edits"], 0)

    def test_history_symlink_directory_refused_before_snapshots_or_restore(self):
        outside = self.folder / "other-directory"
        outside.mkdir()
        link = self.folder / "notes-history"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Konto testowe nie obsługuje symlinków")
        with self.assertRaisesRegex(VideoNotesError, "dowiązaniem"):
            list_note_versions(self.folder)
        with self.assertRaisesRegex(VideoNotesError, "dowiązaniem"):
            regenerate_basic_notes(self.folder, window_minutes=2)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.folder / ".notes.lock").exists())

    def test_tampered_history_timestamp_refused_without_overwrite(self):
        result = regenerate_basic_notes(self.folder, window_minutes=2)
        history_file = self.folder / "notes-history" / (result["revision"] + ".json")
        snapshot = json.loads(history_file.read_text("utf-8"))
        snapshot["created_at"] = "this-is-not-a-time"
        save_json(history_file, snapshot)
        before = (self.folder / "notes.json").read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "datę"):
            list_note_versions(self.folder)
        with self.assertRaisesRegex(VideoNotesError, "datę"):
            restore_note_version(self.folder, result["revision"])
        self.assertEqual((self.folder / "notes.json").read_bytes(), before)

    def test_stale_version_cannot_be_restored_over_new_transcription(self):
        old = regenerate_basic_notes(self.folder, window_minutes=2)
        save_json(self.folder / "edits.json",
                  {"schema": "videonotes-edits-v1", "edits": {"c0000000-s00000": "Zmiana tekstu 123"}})
        regenerated = regenerate_basic_notes(self.folder, window_minutes=1)
        before = (self.folder / "notes.json").read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "nie odpowiada"):
            restore_note_version(self.folder, old["revision"])
        self.assertEqual((self.folder / "notes.json").read_bytes(), before)
        self.assertTrue((self.folder / "notes-history" / (old["revision"] + ".json")).exists())
        self.assertTrue((self.folder / "notes-history" / (regenerated["revision"] + ".json")).exists())

    def test_invalid_version_path_and_tampering_fails_closed(self):
        result = regenerate_basic_notes(self.folder, window_minutes=2)
        for identifier in ("../secret", "", "a" * 31, "not-an-uuid"):
            with self.subTest(identifier=identifier), self.assertRaises(VideoNotesError):
                restore_note_version(self.folder, identifier)
        snap = self.folder / "notes-history" / (result["revision"] + ".json")
        snapshot = json.loads(snap.read_text(encoding="utf-8"))
        snapshot["edits"]["edits"][self.point] = "Injected change"
        save_json(snap, snapshot)
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            restore_note_version(self.folder, result["revision"])

    def test_edited_quotes_pinned_when_selection_window_changes(self):
        # Add 12 segments in a single time-window so one edited quote is outside
        # the default 2 most-important picks after regeneration.
        _, transcript, _ = read_project(self.folder)
        new_segments = []
        for index in range(12):
            new_segments.append({"id": f"c0000000-s{index:05d}", "chunk_index": 0,
                                 "start_ms": index * 4_000, "end_ms": index * 4_000 + 1_000,
                                 "text": f"Wypowiedź numer {index} o serwerze i pamięci.",
                                 "status": "raw"})
        transcript["segments"] = new_segments + [seg for seg in transcript["segments"] if seg["chunk_index"] == 1]
        save_json(self.folder / "transcript.json", transcript)
        # The previous version is now stale. Old edited quote survives by stable ID.
        edit_path = self.folder / "notes-edits.json"
        save_json(edit_path, {"schema": "videonotes-note-edits-v1",
                              "edits": {"quote-c0000000-s00001": "Ważny wniosek od użytkownika"}})
        new = regenerate_basic_notes(self.folder, window_minutes=2, points_per_section=2)
        _, manual = read_basic_notes(self.folder)
        self.assertEqual(new["kept_edits"], 1)
        self.assertIn("quote-c0000000-s00001", manual["edits"])
        ids = [point["id"] for section in read_basic_notes(self.folder)[0]["sections"] for point in section["points"]]
        self.assertIn("quote-c0000000-s00001", ids)

    def test_missing_source_segment_retains_snapshot_but_reports_unmatched(self):
        edit_note_point(self.folder, self.point, "Ważna notatka, nie wolno jej zgubić")
        transcript = read_project(self.folder)[1]
        transcript["segments"] = transcript["segments"][1:]
        save_json(self.folder / "transcript.json", transcript)
        data = regenerate_basic_notes(self.folder, window_minutes=1)
        self.assertEqual(data["unmatched_edits"], 1)
        self.assertEqual(data["kept_edits"], 0)
        historical = list_note_versions(self.folder)
        self.assertEqual(historical[0]["manual_edits"], 1)

    def _simulate_note_crash(self):
        """Interrupt exactly after notes.json committed but before note edits."""
        real_save_json = save_json
        def interrupted(path, payload):
            if Path(path).name == "notes-edits.json":
                raise OSError("Test crash: simulated disk failure between note files")
            return real_save_json(path, payload)
        with patch("videonotes.note_revisions.save_json", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "simulated disk failure"):
                regenerate_basic_notes(self.folder, window_minutes=2, points_per_section=2)

    def test_interrupted_regeneration_keeps_manual_work_and_explicitly_recovers(self):
        edit_note_point(self.folder, self.point, "Prywatna ręczna poprawka; zachowaj mnie")
        old_notes = (self.folder / "notes.json").read_bytes()
        old_edits = (self.folder / "notes-edits.json").read_bytes()
        # The edited segment no longer appears in the source: regeneration
        # will archive that user edit, not copy it to the new live note.
        transcript = read_project(self.folder)[1]
        transcript["segments"] = [
            row for row in transcript["segments"] if row["id"] != self.point.removeprefix("quote-")
        ]
        save_json(self.folder / "transcript.json", transcript)
        self._simulate_note_crash()
        self.assertTrue((self.folder / ".notes-transaction.json").is_file())
        self.assertFalse((self.folder / ".notes.lock").exists())
        self.assertNotEqual((self.folder / "notes.json").read_bytes(), old_notes)
        self.assertEqual((self.folder / "notes-edits.json").read_bytes(), old_edits)
        for blocked in (
            lambda: read_basic_notes(self.folder),
            lambda: edit_note_point(self.folder, self.point, "Do not overwrite me"),
            lambda: regenerate_basic_notes(self.folder),
        ):
            with self.assertRaisesRegex(VideoNotesError, "notes-recover"):
                blocked()
        with self.assertRaisesRegex(VideoNotesError, "Potwierdź"):
            recover_interrupted_note_update(self.folder)
        restored = recover_interrupted_note_update(self.folder, confirm=True)
        self.assertEqual(restored["status"], "restored_previous_version")
        self.assertEqual((self.folder / "notes.json").read_bytes(), old_notes)
        self.assertEqual((self.folder / "notes-edits.json").read_bytes(), old_edits)
        self.assertFalse((self.folder / ".notes-transaction.json").exists())
        self.assertEqual(json.loads(old_edits)["edits"][self.point],
                         "Prywatna ręczna poprawka; zachowaj mnie")
        self.assertEqual(recover_interrupted_note_update(self.folder, confirm=True)["status"],
                         "no_pending_update")
        refreshed = regenerate_basic_notes(self.folder, window_minutes=2)
        self.assertTrue(refreshed["changed"])
        self.assertEqual(refreshed["unmatched_edits"], 1)
        self.assertEqual(read_basic_notes(self.folder)[1]["edits"], {})

    def test_crash_after_note_write_with_identical_edits_counts_as_complete(self):
        edit_note_point(self.folder, self.point, "Nadal moja ręczna poprawka")
        self._simulate_note_crash()
        result = recover_interrupted_note_update(self.folder, confirm=True)
        self.assertEqual(result["status"], "completed_before_crash")
        notes, edits = read_basic_notes(self.folder)
        self.assertEqual(len(notes["sections"]), 1)
        self.assertEqual(edits["edits"][self.point], "Nadal moja ręczna poprawka")

    def test_user_changes_after_interrupted_revision_refuse_overwrite(self):
        edit_note_point(self.folder, self.point, "Początkowy tekst użytkownika")
        transcript = read_project(self.folder)[1]
        transcript["segments"] = [
            row for row in transcript["segments"] if row["id"] != self.point.removeprefix("quote-")
        ]
        save_json(self.folder / "transcript.json", transcript)
        self._simulate_note_crash()
        journal = self.folder / ".notes-transaction.json"
        preserved = (self.folder / "notes-edits.json")
        edits = json.loads(preserved.read_text("utf-8"))
        edits["edits"][self.point] = "Nowsza edycja wykonana poza aplikacją"
        save_json(preserved, edits)
        bytes_before = ((self.folder / "notes.json").read_bytes(), preserved.read_bytes(),
                        journal.read_bytes())
        with self.assertRaisesRegex(VideoNotesError, "Nie nadpisuję zmian"):
            recover_interrupted_note_update(self.folder, confirm=True)
        self.assertEqual(bytes_before, ((self.folder / "notes.json").read_bytes(),
                                        preserved.read_bytes(), journal.read_bytes()))
        self.assertFalse((self.folder / ".notes.lock").exists())

    def test_completed_writes_with_residual_intent_are_only_marked_complete(self):
        old = json.loads((self.folder / "notes.json").read_text("utf-8"))
        manual = json.loads((self.folder / "notes-edits.json").read_text("utf-8"))
        changed = regenerate_basic_notes(self.folder, window_minutes=2)
        current_note_bytes = (self.folder / "notes.json").read_bytes()
        current_edit_bytes = (self.folder / "notes-edits.json").read_bytes()
        current_note = json.loads(current_note_bytes)
        current_edit = json.loads(current_edit_bytes)
        _begin_transaction(self.folder, self.notes["project_id"], changed["revision"],
                           old, manual, current_note, current_edit)
        report = recover_interrupted_note_update(self.folder, confirm=True)
        self.assertEqual(report["status"], "completed_before_crash")
        self.assertFalse(report["changed"])
        self.assertEqual((self.folder / "notes.json").read_bytes(), current_note_bytes)
        self.assertEqual((self.folder / "notes-edits.json").read_bytes(), current_edit_bytes)
        self.assertFalse((self.folder / ".notes-transaction.json").exists())

    def test_manual_note_edit_respects_revision_lock(self):
        lock = self.folder / ".notes.lock"
        lock.write_text("other writer", encoding="utf-8")
        old = (self.folder / "notes-edits.json").read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "Inna operacja"):
            edit_note_point(self.folder, self.point, "Nowsza poprawka")
        self.assertEqual(old, (self.folder / "notes-edits.json").read_bytes())
        self.assertTrue(lock.exists())

    def test_restore_transaction_interruption_can_restore_previous_active_pair(self):
        edit_note_point(self.folder, self.point, "Nie utracę mojej poprawki")
        result = regenerate_basic_notes(self.folder, window_minutes=2)
        edit_note_point(self.folder, self.point, "Późniejsza poprawka, inna niż w zapisanej wersji")
        before = ((self.folder / "notes.json").read_bytes(),
                  (self.folder / "notes-edits.json").read_bytes())
        real_save_json = save_json
        def interrupt_second(path, payload):
            if Path(path).name == "notes-edits.json":
                raise OSError("Test crash during history restore")
            return real_save_json(path, payload)
        with patch("videonotes.note_revisions.save_json", side_effect=interrupt_second):
            with self.assertRaisesRegex(OSError, "history restore"):
                restore_note_version(self.folder, result["revision"])
        receipt = recover_interrupted_note_update(self.folder, confirm=True)
        self.assertEqual(receipt["status"], "restored_previous_version")
        self.assertEqual((self.folder / "notes.json").read_bytes(), before[0])
        self.assertEqual((self.folder / "notes-edits.json").read_bytes(), before[1])
        self.assertEqual(read_basic_notes(self.folder)[1]["edits"][self.point],
                         "Późniejsza poprawka, inna niż w zapisanej wersji")

    def test_concurrent_lock_prevents_overwriting_history(self):
        (self.folder / ".notes.lock").write_text("other writer", encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "zablokowany"):
            regenerate_basic_notes(self.folder, window_minutes=2)
        self.assertEqual(list_note_versions(self.folder), [])
        self.assertTrue((self.folder / ".notes.lock").exists())

    def test_partial_project_refused(self):
        folder = self.folder / "partial"
        fixture(folder, complete=False)
        with self.assertRaisesRegex(VideoNotesError, "Ukończ"):
            regenerate_basic_notes(folder)

if __name__ == "__main__":
    unittest.main()
