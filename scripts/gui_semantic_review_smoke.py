"""Actual Tk widget smoke for optional semantic review, Linux Xvfb and hosted Windows.

Test responses are synthetic, decisions are scripted and not real human QA.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tkinter import ttk
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.gui import VideoNotesWindow
from videonotes.semantic_draft import create_semantic_draft
from videonotes.semantic_review import semantic_review_status
from videonotes.semantic_review_gui import SemanticReviewWindow


@unittest.skipUnless(bool(os.environ.get("DISPLAY")) or sys.platform == "win32",
                     "Tk interactive smoke needs Xvfb or Windows desktop")
class SemanticReviewRealTkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vn-review-tk-")
        self.addCleanup(self.tmp.cleanup)
        self.root_path = Path(self.tmp.name)
        self.project = self.root_path / "project"
        fixture(self.project)
        model = self.root_path / "fake-unit.gguf"
        model.write_bytes(b"NOT REAL AI")
        self.draft = self.root_path / "source-draft.json"
        self.review = self.root_path / "review-1"
        self.output = self.root_path / "accepted.md"

        def fake_model(args, **kwargs):
            prompt = Path(args[args.index("-f") + 1]).read_text("utf-8")
            source_id = "c0000001-s00000" if "Adres IP" in prompt else "c0000000-s00000"
            kwargs["stdout"].write(json.dumps({
                "heading": "Konspekt", "claims": [{
                    "text": "Zdanie testowe do weryfikacji.", "source_ids": [source_id]
                }]
            }).encode("utf-8"))
            return CompletedProcess(args, 0)

        create_semantic_draft(self.project, self.draft, model=model,
                              llama_cli=sys.executable, section_minutes=1, runner=fake_model)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_real_review_window_load_review_mark_and_export(self):
        panel = SemanticReviewWindow(self.root, self.project)
        self.root.update()
        panel.draft_path.set(str(self.draft))
        panel.review_path.set(str(self.review))
        panel.reviewer.set("Test reviewer (user-declared)")
        panel.reload()
        self.root.update()
        claims = list(panel.tree.get_children())
        self.assertEqual(len(claims), 2)
        self.assertIn("Wykład dotyczy", panel.details.get("1.0", "end"))
        self.assertFalse(self.review.exists())

        with patch("videonotes.semantic_review_gui.messagebox.showerror") as errors:
            panel.start_review()
            self.assertFalse(errors.called)
        self.assertTrue((self.review / "review.json").is_file())
        self.assertEqual(semantic_review_status(self.project, self.draft, self.review)["pending"], 2)

        with patch("videonotes.semantic_review_gui.messagebox.askyesno", return_value=False) as ask:
            panel.tree.selection_set(claims[0])
            panel.mark("approve")
            ask.assert_called_once()
        self.assertEqual(semantic_review_status(self.project, self.draft, self.review)["approved_by_user"], 0)

        with patch("videonotes.semantic_review_gui.messagebox.askyesno", return_value=True) as ask:
            panel.tree.selection_set(claims[0])
            panel.mark("approve")
            panel.tree.selection_set(claims[1])
            panel.mark("reject")
            self.assertEqual(ask.call_count, 2)
        after = semantic_review_status(self.project, self.draft, self.review)
        self.assertEqual((after["approved_by_user"], after["rejected_by_user"], after["pending"]), (1, 1, 0))
        self.assertFalse(after["facts_verified_by_software"])

        with patch("videonotes.semantic_review_gui.filedialog.asksaveasfilename",
                   return_value=str(self.output)), \
             patch("videonotes.semantic_review_gui.messagebox.showerror") as errors:
            panel.export()
            errors.assert_not_called()
        self.assertTrue(self.output.is_file())
        markdown = self.output.read_text("utf-8")
        self.assertIn(claims[0], markdown)
        self.assertNotIn(claims[1], markdown)
        self.assertIn("nie weryfikuje", markdown)

    def test_guard_prevents_changes_with_unsaved_transcript(self):
        guard = {"blocked": True}
        panel = SemanticReviewWindow(self.root, self.project,
                                     guard=lambda: guard["blocked"])
        panel.draft_path.set(str(self.draft))
        panel.review_path.set(str(self.review))
        with patch("videonotes.semantic_review_gui.messagebox.showwarning") as warning:
            panel.start_review()
            warning.assert_called_once()
        self.assertFalse(self.review.exists())
        guard["blocked"] = False
        panel.reload()
        self.assertEqual(len(panel.tree.get_children()), 2)
        panel.reviewer.set("Local")
        with patch("videonotes.semantic_review_gui.messagebox.askyesno", return_value=True), \
             patch("videonotes.semantic_review_gui.messagebox.showerror") as error:
            panel.mark("approve")
            error.assert_called_once()  # no review manifest exists
        self.assertFalse(self.review.exists())

    def test_existing_main_gui_button_opens_separate_review_window(self):
        gui = VideoNotesWindow(self.root)
        gui.project.set(str(self.project))
        gui._show_optional_analysis()
        self.root.update()
        panels = [child for child in self.root.winfo_children()
                  if isinstance(child, tk.Toplevel) and
                  "Lokalna analiza opcjonalna" in child.title()]
        self.assertEqual(len(panels), 1)
        def descendants(widget):
            result = []
            for child in widget.winfo_children():
                result.append(child)
                result.extend(descendants(child))
            return result
        controls = [child for child in descendants(panels[0])
                    if isinstance(child, ttk.Button) and child.cget("text") == "Oceń szkic AI"]
        self.assertEqual(len(controls), 1)
        controls[0].invoke()
        self.root.update()
        reviews = [child for child in self.root.winfo_children()
                   if isinstance(child, tk.Toplevel) and
                   "ręczna kontrola szkicu AI" in child.title()]
        self.assertEqual(len(reviews), 1)
        self.assertFalse(self.review.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
