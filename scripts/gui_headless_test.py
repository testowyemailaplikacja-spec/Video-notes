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
        self.assertIn("Wstrzymane", controls["status"].get())
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
