"""Real Tk widget interactions under a disposable Linux Xvfb display.

Tests GUI state transitions without mocking widgets; messagebox confirmation
is mocked to avoid a human-operated modal window. Supports Linux Xvfb and
Windows hosted CI with Tk available, not physical Windows acceptance.
"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.gui import VideoNotesWindow
from videonotes.note_revisions import regenerate_basic_notes
from videonotes.notes import edit_note_point, generate_basic_notes, read_basic_notes
from videonotes.storage import save_json


def children(widget):
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(children(child))
    return found


@unittest.skipUnless(
    bool(os.environ.get("DISPLAY")) or sys.platform == "win32",
    "Real Tk GUI smoke requires Xvfb or a Windows desktop session",
)
class GuiNotesHeadlessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vn-gui-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        fixture(self.folder)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.gui = VideoNotesWindow(self.root)
        self.gui.project.set(str(self.folder))

    def _note_windows(self):
        return [x for x in children(self.root) if isinstance(x, tk.Toplevel)
                and x.winfo_exists() and "Notatka podstawowa" in x.title()]

    def _button(self, parent, label):
        matches = [x for x in children(parent)
                   if isinstance(x, ttk.Button) and str(x.cget("text")) == label]
        self.assertEqual(len(matches), 1, f"Expected precisely one button {label!r}")
        return matches[0]


    def test_optional_local_analysis_dialog_exposes_controls_without_auto_processing(self):
        with patch("videonotes.gui.extract_slide_ocr") as ocr, \
             patch("videonotes.gui.create_semantic_draft") as semantic:
            self.gui._show_optional_analysis()
            self.root.update()
            dialogs = [x for x in children(self.root)
                       if isinstance(x, tk.Toplevel) and x.winfo_exists()
                       and "Lokalna analiza opcjonalna" in x.title()]
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            self._button(dialog, "Wykonaj OCR slajdów")
            self._button(dialog, "Utwórz szkic AI (niezweryfikowany)")
            self._button(dialog, "Eksportuj sprawdzalne cytaty do MD")
            self._button(dialog, "Sprawdź cytaty / integralność istniejącego raportu")
            ocr.assert_not_called()
            semantic.assert_not_called()
            self.assertFalse(self.gui.optional_analysis_active)

    def test_optional_analysis_has_explicit_file_choice_and_background_completion(self):
        import time
        self.gui._show_optional_analysis()
        self.root.update()
        dialogs = [x for x in children(self.root)
                   if isinstance(x, tk.Toplevel) and x.winfo_exists()
                   and "Lokalna analiza opcjonalna" in x.title()]
        self.assertEqual(len(dialogs), 1)
        destination = str(self.folder / "ocr-report-new.json")
        with patch("videonotes.gui.filedialog.asksaveasfilename", return_value=destination), \
             patch("videonotes.gui.extract_slide_ocr", return_value={
                 "output": destination, "frames": 1, "human_reviewed": False
             }) as ocr, \
             patch("videonotes.gui.messagebox.showinfo") as notice, \
             patch("videonotes.gui.messagebox.showwarning") as warning:
            self._button(dialogs[0], "Wykonaj OCR slajdów").invoke()
            self.assertTrue(self.gui.optional_analysis_active)
            for _ in range(100):
                self.root.update()
                if not self.gui.optional_analysis_active:
                    break
                time.sleep(0.02)
            self.assertFalse(self.gui.optional_analysis_active)
            ocr.assert_called_once()
            self.assertIn("wymaga kontroli", self.gui.status.get())
            notice.assert_called_once()
            warning.assert_not_called()


    def test_finished_microphone_asr_dialog_requires_explicit_new_folder_and_preserves_existing_project(self):
        import time
        prior_project = self.gui.project.get()
        new_project = str(self.folder / "new-recording-asr-project")
        recording = str(self.folder / "finished-mic")
        result = {
            "schema": "videonotes-record-to-asr-v1", "project_id": "new-test",
            "project": new_project, "source_wav": str(self.folder / "joined.wav"),
            "recording_parts": 2, "completed_chunks": 2, "segments": 2,
            "exports": [], "original_recording_preserved": True,
        }
        btn = self._button(self.root, "Zakończone nagranie mikrofonowe → transkrypcja całej sesji")
        self.gui.model.set(str(self.folder / "model.bin"))
        with patch("videonotes.gui.filedialog.askdirectory", side_effect=[recording, new_project]), \
             patch("videonotes.gui.filedialog.asksaveasfilename",
                   return_value=str(self.folder / "joined.wav")), \
             patch("videonotes.gui.recording_status", return_value={
                 "status": "finished", "sha256_verified": True,
                 "segments": [{"name": "part-00000.wav"}, {"name": "part-00001.wav"}],
             }), \
             patch("videonotes.gui.transcribe_finished_session", return_value=result) as backend, \
             patch("videonotes.gui.messagebox.askyesno", return_value=True), \
             patch("videonotes.gui.messagebox.showwarning") as warning, \
             patch.object(self.gui, "_load", return_value=True) as load:
            btn.invoke()
            self.assertEqual(self.gui.project.get(), prior_project)
            self.assertTrue(self.gui.active)
            for _ in range(100):
                self.root.update()
                if not self.gui.active:
                    break
                time.sleep(0.02)
            self.assertFalse(self.gui.active)
            backend.assert_called_once()
            call = backend.call_args
            self.assertEqual(str(call.args[0]), recording)
            self.assertEqual(str(call.args[1]), new_project)
            self.assertTrue(call.kwargs["original_recording_preserved"] if
                            "original_recording_preserved" in call.kwargs else result["original_recording_preserved"])
            self.assertEqual(self.gui.project.get(), new_project)
            load.assert_called_once()
            warning.assert_not_called()

    def test_finished_mic_asr_refuses_existing_nonempty_project(self):
        recorded = str(self.folder / "finished-mic")
        with patch("videonotes.gui.filedialog.askdirectory", side_effect=[recorded, str(self.folder)]), \
             patch("videonotes.gui.recording_status", return_value={
                 "status": "finished", "sha256_verified": True,
                 "segments": [{"name": "part-00000.wav"}],
             }), \
             patch("videonotes.gui.transcribe_finished_session") as backend, \
             patch("videonotes.gui.messagebox.showwarning") as warning:
            self.gui.model.set(str(self.folder / "model.bin"))
            self._button(self.root, "Zakończone nagranie mikrofonowe → transkrypcja całej sesji").invoke()
            self.assertTrue(warning.called)
            backend.assert_not_called()
            self.assertFalse(self.gui.active)

    def test_version_history_button_opens_and_restores_selected_source_safe_snapshot(self):
        note = generate_basic_notes(self.folder, window_minutes=1)
        point = note["sections"][0]["points"][0]["id"]
        edit_note_point(self.folder, point, "Ważna ręczna uwaga")
        result = regenerate_basic_notes(self.folder, window_minutes=2)
        self.gui._show_notes()
        window = self._note_windows()[-1]
        self._button(window, "Historia i przywracanie wersji").invoke()
        self.root.update()
        history = [x for x in children(window) if isinstance(x, tk.Toplevel)]
        self.assertEqual(len(history), 1)
        tables = [x for x in children(history[0]) if isinstance(x, ttk.Treeview)
                  and "revision" in x.cget("columns")]
        self.assertEqual(len(tables), 1)
        self.assertIn(result["revision"], tables[0].get_children())
        tables[0].selection_set(result["revision"])
        with patch("videonotes.gui.messagebox.askyesno", return_value=True), \
             patch("videonotes.gui.messagebox.showerror") as error:
            self._button(history[0], "Przywróć wybraną wersję").invoke()
            self.root.update()
            error.assert_not_called()
        restored, manual = read_basic_notes(self.folder)
        self.assertEqual(len(restored["sections"]), 2)
        self.assertEqual(manual["edits"][point], "Ważna ręczna uwaga")
        self.assertEqual(len(self._note_windows()), 1)

    def test_interrupted_transaction_is_accepted_only_after_dialog_confirmation(self):
        generate_basic_notes(self.folder, window_minutes=1)
        original_save = save_json
        def simulated_disk_failure(path, value):
            if Path(path).name == "notes-edits.json":
                raise OSError("simulated abrupt termination")
            return original_save(path, value)
        with patch("videonotes.note_revisions.save_json", side_effect=simulated_disk_failure):
            with self.assertRaisesRegex(OSError, "abrupt"):
                regenerate_basic_notes(self.folder, window_minutes=2)
        marker = self.folder / ".notes-transaction.json"
        self.assertTrue(marker.exists())
        with patch("videonotes.gui.messagebox.askyesno", return_value=False) as denied:
            self.gui._show_notes()
            self.assertEqual(denied.call_count, 1)
        self.assertTrue(marker.exists(), "Dismissal must not recover or erase user data")
        self.assertEqual(self._note_windows(), [])
        with patch("videonotes.gui.messagebox.askyesno", return_value=True), \
             patch("videonotes.gui.messagebox.showinfo") as info, \
             patch("videonotes.gui.messagebox.showerror") as error:
            self.gui._show_notes()
            self.root.update()
            self.assertTrue(info.called)
            error.assert_not_called()
        self.assertFalse(marker.exists())
        self.assertEqual(len(self._note_windows()), 1)
        self.assertEqual(len(read_basic_notes(self.folder)[0]["sections"]), 1)

    def test_unsaved_draft_selection_change_requires_confirmation(self):
        generated = generate_basic_notes(self.folder, window_minutes=1)
        self.gui._show_notes()
        self.root.update()
        window = self._note_windows()[-1]
        table = next(x for x in children(window) if isinstance(x, ttk.Treeview)
                     and "quote" in x.cget("columns"))
        editor = next(x for x in children(window) if isinstance(x, tk.Text))
        ids = [point["id"] for section in generated["sections"] for point in section["points"]]
        self.assertGreaterEqual(len(ids), 2)
        self.assertEqual(table.selection()[0], ids[0])
        editor.insert("end", " NIEZAPISANY SZKIC")
        with patch("videonotes.gui.messagebox.askyesno", return_value=False) as dialog:
            table.selection_set(ids[1])
            self.root.update()
            self.assertTrue(dialog.called)
        self.assertEqual(table.selection()[0], ids[0])
        self.assertIn("NIEZAPISANY SZKIC", editor.get("1.0", "end-1c"))
        self.assertEqual(read_basic_notes(self.folder)[1]["edits"], {})


    def test_actual_tk_crash_salvage_warns_about_incomplete_source(self):
        self._button(
            self.root, "Odzyskaj czytelne WAV po awarii (może być niekompletne)"
        )
        previous = self.gui.source.get()
        self.gui.events.put(("mic_salvage_complete", {
            "output": str(self.folder / "recording-salvaged-INCOMPLETE.wav"),
            "copied_parts": 2,
            "truncated_or_incomplete": True,
            "not_a_complete_lecture": True,
        }))
        with patch("videonotes.gui.messagebox.showwarning") as alert:
            self.gui._drain()
            alert.assert_called_once()
        self.assertFalse(self.gui.active)
        self.assertIn("NIEKOMPLETNY", self.gui.status.get())
        self.assertIn("INCOMPLETE.wav", self.gui.source.get())
        self.assertNotEqual(self.gui.source.get(), previous)
        self.assertEqual(self.gui.project.get(), str(self.folder))

    def test_real_tk_audio_quality_report_is_numerical_and_read_only(self):
        button = self._button(
            self.root, "Sprawdź jakość nagrania WAV — cisza i przesterowanie"
        )
        self.assertIsNotNone(button)
        report = {
            "schema": "videonotes-wav-diagnostics-v1",
            "duration_ms": 6000, "part_count": 2,
            "rms_dbfs": -14.20, "peak_dbfs": -0.10,
            "clipped_sample_ratio": 0.10, "silent_ratio": 0.33,
            "longest_silence_ms": 2000, "sha256_verified": True,
            "warnings": ["Wykryto clipping"],
            "parts": [
                {"name": "part-00000.wav", "rms_dbfs": -14.2,
                 "peak_dbfs": -0.1, "silent_duration_ms": 2000},
            ],
        }
        self.gui.active = True
        self.gui.start_button.configure(state="disabled")
        self.gui.events.put(("mic_quality_complete", report))
        self.gui._drain()
        windows = [
            item for item in children(self.root) if isinstance(item, tk.Toplevel)
            and item.winfo_exists() and "Kontrola nagrania" in item.title()
        ]
        self.assertEqual(len(windows), 1)
        editor = next(x for x in children(windows[0]) if isinstance(x, tk.Text))
        rendered = editor.get("1.0", "end-1c")
        self.assertIn("RMS", rendered)
        self.assertIn("6.0 s", rendered)
        self.assertIn("clipping", rendered)
        self.assertNotIn("Wykład dotyczy", rendered)
        self.assertEqual(str(editor["state"]), "disabled")
        self.assertFalse(self.gui.active)
        self.assertEqual(str(self.gui.start_button["state"]), "normal")

    def test_mic_real_tk_pause_resume_stop_controls_and_events(self):
        """Tests real widgets on Linux Xvfb + Windows VM, not physical mic."""
        self.gui._show_mic_recorder()
        self.root.update()
        controls = self.gui.mic_controls
        self.assertTrue(controls["window"].winfo_exists())
        self.assertEqual(str(controls["pause"]["state"]), "disabled")
        self.assertEqual(str(controls["resume"]["state"]), "disabled")
        self.gui.active = True
        controls["stop"].configure(state="normal")
        self.gui.events.put(("mic_capture_state", "recording"))
        self.gui._drain()
        self.assertEqual(str(controls["pause"]["state"]), "normal")
        self._button(controls["window"], "Pauza").invoke()
        self.assertTrue(self.gui.mic_pause.is_set())
        self.assertEqual(str(controls["pause"]["state"]), "disabled")
        self.gui.events.put(("mic_capture_state", "paused"))
        self.gui._drain()
        self.assertEqual(str(controls["resume"]["state"]), "normal")
        self.assertIn("wstrzymane", controls["status"].get())
        self._button(controls["window"], "Wznów nagrywanie").invoke()
        self.assertTrue(self.gui.mic_resume.is_set())
        self.gui.events.put(("mic_capture_state", "recording"))
        self.gui._drain()
        self.assertEqual(str(controls["resume"]["state"]), "disabled")
        self.assertEqual(str(controls["pause"]["state"]), "normal")
        self._button(controls["window"], "Zatrzymaj").invoke()
        self.assertTrue(self.gui.mic_stop.is_set())
        self.gui.events.put(("mic_complete", (self.folder, {
            "status": "finished",
            "segments": [{"name": "part-00000.wav"}, {"name": "part-00001.wav"}],
        })))
        self.gui._drain()
        self.assertFalse(self.gui.active)
        self.assertEqual(str(controls["pause"]["state"]), "disabled")
        self.assertEqual(str(controls["resume"]["state"]), "disabled")

    def test_multisegment_mic_status_never_silently_selects_first_part(self):
        """Exercise actual Tk event handling with two recorded WAV pieces."""
        old_source = "previous-existing-source.wav"
        self.gui.source.set(old_source)
        self.gui.events.put(("mic_complete", (self.folder, {
            "status": "finished", "segments": [
                {"name": "part-00000.wav"}, {"name": "part-00001.wav"}
            ]
        })))
        self.gui._drain()
        self.assertEqual(self.gui.source.get(), old_source)
        self.assertIn("transkrybować CAŁE nagranie", self.gui.status.get())
        self.assertEqual(str(self.gui.start_button["state"]), "normal")

    def test_join_completion_selects_full_wav_and_clears_stale_track(self):
        old_path = self.folder / "recording-full.wav"
        self.gui.source.set("previous-file.mkv")
        self.gui.streams = {"invalid previous track": 4}
        self.gui.stream.set("invalid previous track")
        self.gui.active = True
        self.gui.events.put(("mic_join_complete", str(old_path)))
        self.gui._drain()
        self.assertEqual(self.gui.source.get(), str(old_path))
        self.assertEqual(self.gui.stream.get(), "")
        self.assertFalse(self.gui.streams)
        self.assertFalse(self.gui.active)
        self.assertIn("Połączono całe nagranie", self.gui.status.get())

    def test_basic_note_click_source_opens_corresponding_transcript_segment(self):
        self.gui._show_notes()
        self.root.update()
        window = self._note_windows()[-1]
        table = next(w for w in children(window) if isinstance(w, ttk.Treeview)
                     and "quote" in w.cget("columns"))
        first = table.get_children()[0]
        table.selection_set(first)
        self.root.update()
        expected_id = first.removeprefix("quote-")
        self._button(window, "Przejdź do źródła transkrypcji").invoke()
        self.root.update()
        self.assertEqual(self.gui._current_segment_id, expected_id)
        self.assertEqual(self.gui.segments.selection()[0], expected_id)
        self.assertIn("Wykład dotyczy", self.gui.edit_text.get("1.0", "end-1c"))
        self.assertIn(expected_id, self.gui.status.get())

    def test_jump_to_source_respects_unsaved_asr_draft_on_selection_and_reload(self):
        self.assertTrue(self.gui._load())
        ids = list(self.gui.segments.get_children())
        self.assertGreaterEqual(len(ids), 2)
        self.gui.segments.selection_set(ids[0])
        self.gui._selected()
        self.gui.edit_text.insert("end", " DRAFT NIEZAPISANY")
        with patch("videonotes.gui.messagebox.askyesno", return_value=False) as prompt:
            self.assertFalse(self.gui._jump_to_source(ids[1]))
            self.assertTrue(prompt.called)
        self.assertEqual(self.gui._current_segment_id, ids[0])
        self.assertIn("DRAFT NIEZAPISANY", self.gui.edit_text.get("1.0", "end-1c"))
        self.assertFalse(self.gui._load(silent=True))
        with patch("videonotes.gui.messagebox.askyesno", return_value=True):
            self.assertTrue(self.gui._jump_to_source(ids[1]))
        self.assertEqual(self.gui._current_segment_id, ids[1])
        self.assertNotIn("DRAFT NIEZAPISANY", self.gui.edit_text.get("1.0", "end-1c"))

    def test_advanced_and_study_guide_citations_open_actual_source_in_tk(self):
        for kind in ("advanced", "study"):
            with self.subTest(kind=kind):
                if kind == "advanced":
                    self.gui._show_advanced()
                    title_part = "Konspekt źródłowy"
                else:
                    self.gui._show_study_guide()
                    title_part = "Przewodnik do nauki"
                self.root.update()
                windows = [
                    w for w in children(self.root) if isinstance(w, tk.Toplevel)
                    and w.winfo_exists() and title_part in w.title()
                ]
                self.assertTrue(windows)
                window = windows[-1]
                trees = [
                    w for w in children(window) if isinstance(w, ttk.Treeview)
                    and tuple(w.cget("columns")) == ("time", "text")
                ]
                self.assertEqual(len(trees), 1)
                table = trees[0]
                self.assertGreaterEqual(len(table.get_children()), 2)
                target = table.get_children()[-1]
                table.selection_set(target)
                self._button(window, "Przejdź do zaznaczonego źródła").invoke()
                self.root.update()
                self.assertEqual(self.gui._current_segment_id, target)
                self.assertEqual(self.gui.segments.selection()[0], target)
                self.assertTrue(self.gui.edit_text.get("1.0", "end-1c"))
                window.destroy()

    def test_basic_note_unsaved_draft_blocks_source_navigation(self):
        self.gui._show_notes()
        self.root.update()
        window = self._note_windows()[-1]
        table = next(w for w in children(window) if isinstance(w, ttk.Treeview)
                     and "quote" in w.cget("columns"))
        table.selection_set(table.get_children()[0])
        self.root.update()
        editor = next(w for w in children(window) if isinstance(w, tk.Text))
        editor.insert("end", " NIEZAPISANA UWAGA")
        with patch("videonotes.gui.messagebox.showwarning") as dialog:
            self._button(window, "Przejdź do źródła transkrypcji").invoke()
            dialog.assert_called_once()
        self.assertIsNone(self.gui._current_segment_id)
        self.assertIn("NIEZAPISANA UWAGA", editor.get("1.0", "end-1c"))

    def test_real_advanced_template_gui_changes_content_exports_docx_and_verifies_json(self):
        self.gui._show_advanced()
        self.root.update()
        windows = [
            w for w in children(self.root) if isinstance(w, tk.Toplevel)
            and w.winfo_exists() and "Konspekt źródłowy" in w.title()
        ]
        self.assertEqual(len(windows), 1)
        panel = windows[0]
        choices = [w for w in children(panel) if isinstance(w, ttk.Combobox)]
        self.assertEqual(len(choices), 3)
        choices[0].set("Spotkanie")
        choices[1].set("Pełny")
        choices[2].set("5")
        original = (self.folder / "exports" / "notes-advanced.json").read_bytes()
        with patch("videonotes.gui.messagebox.askyesno", return_value=False) as refuse:
            self._button(panel, "Opracuj / odśwież").invoke()
            refuse.assert_called_once()
        self.assertEqual(
            (self.folder / "exports" / "notes-advanced.json").read_bytes(), original
        )
        with patch("videonotes.gui.messagebox.askyesno", return_value=True):
            self._button(panel, "Opracuj / odśwież").invoke()
        doc = __import__("json").loads(
            (self.folder / "exports" / "notes-advanced.json").read_text("utf-8")
        )
        self.assertEqual(doc["template"], "meeting")
        self.assertEqual(doc["detail"], "full")
        self.assertEqual(doc["section_minutes"], 5)
        self.assertEqual(str(next(w for w in children(panel) if isinstance(w, tk.Text))["state"]),
                         "disabled")
        with patch("videonotes.gui.messagebox.askyesno", return_value=True):
            self._button(panel, "Eksport DOCX").invoke()
        self.assertTrue((self.folder / "exports" / "notes-advanced.docx").is_file())
        with patch("videonotes.gui.messagebox.showinfo") as info:
            self._button(panel, "Sprawdź źródła").invoke()
            info.assert_called_once()
        self.assertIn("Zweryfikowano", self.gui.status.get())

    def test_real_study_guide_gui_preview_reconfigure_and_word_export(self):
        self._button(
            self.root,
            "Przewodnik do nauki — cytaty, pojęcia i pytania (VN-02/03)",
        ).invoke()
        self.root.update()
        windows = [
            window for window in children(self.root)
            if isinstance(window, tk.Toplevel) and window.winfo_exists()
            and "Przewodnik do nauki" in window.title()
        ]
        self.assertEqual(len(windows), 1)
        dialog = windows[0]
        preview = next(x for x in children(dialog) if isinstance(x, tk.Text))
        self.assertIn("Spis treści", preview.get("1.0", "end-1c"))
        self.assertIn("Źródło", preview.get("1.0", "end-1c"))
        self.assertEqual(str(preview["state"]), "disabled")
        self.assertTrue((self.folder / "exports" / "notes-study.json").is_file())
        selections = [x for x in children(dialog) if isinstance(x, ttk.Combobox)]
        self.assertEqual(len(selections), 2)
        selections[0].set("full")
        selections[1].set("10")
        self._button(dialog, "Opracuj / odśwież").invoke()
        self.root.update()
        self.assertTrue((self.folder / "exports" / "notes-study.md").is_file())
        self._button(dialog, "Eksport DOCX").invoke()
        self.root.update()
        self.assertTrue((self.folder / "exports" / "notes-study.docx").is_file())
        self.assertIn("notes-study.docx", self.gui.status.get())
        with patch("videonotes.gui.messagebox.showinfo") as info:
            self._button(dialog, "Sprawdź źródła").invoke()
            self.root.update()
            info.assert_called_once()
        self.assertIn("Potwierdzono", self.gui.status.get())
        self.assertFalse(self.gui.active)

    def test_basic_pdf_button_refuses_unsaved_draft(self):
        generate_basic_notes(self.folder)
        self.gui._show_notes()
        self.root.update()
        window = self._note_windows()[-1]
        editor = next(x for x in children(window) if isinstance(x, tk.Text))
        editor.insert("end", " JESZCZE NIE ZAPISANO")
        with patch("videonotes.gui.export_basic_notes_pdf") as pdf, \
             patch("videonotes.gui.messagebox.showwarning") as warning:
            self._button(window, "Eksportuj PDF (LibreOffice)").invoke()
            warning.assert_called_once()
            pdf.assert_not_called()
        self.assertEqual(read_basic_notes(self.folder)[1]["edits"], {})



if __name__ == "__main__":
    unittest.main()
