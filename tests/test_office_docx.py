"""Headless real LibreOffice integration for offline, source-linked DOCX.

Not a physical Windows/Word/manual typography acceptance. Runs on entirely
synthetic local notes; no recording, model, network API or npm dependency.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_notes import fixture
from videonotes.advanced_notes import export_advanced_outline
from videonotes.notes import generate_basic_notes, edit_note_point, export_basic_notes_docx

OFFICE = shutil.which("libreoffice") or shutil.which("soffice")
PDTO = shutil.which("pdftotext")
PDF_RENDER = shutil.which("pdftoppm")


@unittest.skipUnless(OFFICE and PDTO and PDF_RENDER,
                     "Requires real LibreOffice, pdftotext and pdftoppm")
class LibreOfficeDocxIntegrationTest(unittest.TestCase):
    def test_basic_and_advanced_docx_render_to_pdf_with_real_polish_text(self):
        with tempfile.TemporaryDirectory(prefix="vn-docx-office-") as temporary:
            root = Path(temporary)
            folder = root / "project"
            fixture(folder)
            generated = generate_basic_notes(folder, window_minutes=1)
            edit_note_point(folder, generated["sections"][0]["points"][0]["id"],
                            "Zażółć gęślą jaźń <script>dosłowny tekst</script>")
            basic = export_basic_notes_docx(folder)
            advanced = export_advanced_outline(folder, template="lecture",
                                               detail="full", section_minutes=1,
                                               include_docx=True)[2]

            output = root / "rendered"
            output.mkdir()
            expectations = {
                basic: ("Notatka podstawowa", "Zażółć", "poprawka użytkownika"),
                advanced: ("Konspekt wykładu", "Wykład", "Źródło"),
            }
            for docx, required_words in expectations.items():
                with self.subTest(document=docx.name):
                    profile = root / ("profile-" + docx.stem)
                    command = [OFFICE, "-env:UserInstallation=" + profile.as_uri(),
                               "--headless", "--convert-to", "pdf:writer_pdf_Export",
                               "--outdir", str(output), str(docx)]
                    run = subprocess.run(command, check=True, timeout=120,
                                         stdin=subprocess.DEVNULL, capture_output=True,
                                         text=True, encoding="utf-8", errors="replace")
                    pdf = output / (docx.stem + ".pdf")
                    self.assertTrue(pdf.is_file(),
                                    f"LibreOffice did not create {pdf.name}: "
                                    f"stdout={run.stdout[-1200:]!r}, stderr={run.stderr[-1200:]!r}, "
                                    f"folder={[item.name for item in output.iterdir()]}")
                    self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
                    extracted = subprocess.run([PDTO, "-layout", "-enc", "UTF-8",
                                                str(pdf), "-"],
                                               check=True, capture_output=True,
                                               text=True, encoding="utf-8",
                                               errors="replace", timeout=30).stdout
                    for word in required_words:
                        self.assertIn(word, extracted)
                    if docx == basic:
                        self.assertIn("<script>dosłowny tekst</script>", extracted)
                    png = root / ("rendered-" + docx.stem)
                    subprocess.run([PDF_RENDER, "-f", "1", "-l", "1",
                                    "-r", "72", "-png", "-singlefile",
                                    str(pdf), str(png)],
                                   check=True, stdin=subprocess.DEVNULL,
                                   capture_output=True, timeout=60)
                    image = png.with_suffix(".png").read_bytes()
                    self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
                    width, height = struct.unpack(">II", image[16:24])
                    self.assertGreater(width, 400)
                    self.assertGreater(height, 400)
                    self.assertGreater(len(image), 2000)


if __name__ == "__main__":
    unittest.main()
