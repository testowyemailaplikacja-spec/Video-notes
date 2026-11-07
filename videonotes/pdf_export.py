"""Optional offline DOCX -> PDF conversion via user-installed LibreOffice Writer.

No Internet service is used by application code. LibreOffice is optional and
NOT bundled with the development executable; the user must provide a local
installation. Render the complete PDF in a private temporary directory before
publishing any output so a failed conversion cannot replace reviewed files.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .errors import VideoNotesError
from .media import executable
from .storage import atomic_write

MAX_DOCX_BYTES = 64 * 1024 * 1024
MAX_PDF_BYTES = 64 * 1024 * 1024


def render_pdf_from_docx(docx: bytes, *, office: str = "libreoffice") -> bytes:
    """Pre-render a verified PDF without exposing source text in process logs."""
    if not isinstance(docx, bytes) or not 100 <= len(docx) <= MAX_DOCX_BYTES or not docx.startswith(b"PK\x03\x04"):
        raise VideoNotesError("Nieprawidłowy dokument DOCX do eksportu PDF.")
    office_bin = executable(office)
    with tempfile.TemporaryDirectory(prefix="vn-offline-pdf-") as work:
        root = Path(work)
        source = root / "document.docx"
        destination = root / "out"
        destination.mkdir()
        source.write_bytes(docx)
        profile = root / "office-profile"
        command = [
            office_bin, "-env:UserInstallation=" + profile.as_uri(),
            "--headless", "--convert-to", "pdf:writer_pdf_Export",
            "--outdir", str(destination), str(source),
        ]
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, check=False, timeout=300, shell=False)
        except (subprocess.TimeoutExpired, OSError) as error:
            raise VideoNotesError("Lokalny LibreOffice nie wykonał konwersji PDF.") from error
        target = destination / "document.pdf"
        if result.returncode != 0 or not target.is_file():
            raise VideoNotesError("Nie udało się otworzyć DOCX w lokalnym LibreOffice. Starsze pliki pozostają zachowane.")
        try:
            if not 10 <= target.stat().st_size <= MAX_PDF_BYTES:
                raise VideoNotesError("Wygenerowany PDF ma nieprawidłowy rozmiar.")
            output = target.read_bytes()
        except OSError as error:
            raise VideoNotesError("Nie można odczytać lokalnego wyniku PDF.") from error
        if not output.startswith(b"%PDF-") or b"%%EOF" not in output[-1024:]:
            raise VideoNotesError("LibreOffice zwrócił niekompletny dokument PDF.")
        return output


def export_basic_notes_pdf(folder: Path, *, office: str = "libreoffice") -> Path:
    """Export basic notes only after all citations and manual edits are valid."""
    from .docx_export import render_basic_docx
    from .notes import read_basic_notes
    notes, changes = read_basic_notes(folder)
    content = render_pdf_from_docx(render_basic_docx(notes, changes), office=office)
    target = Path(folder) / "exports" / "notes-basic.pdf"
    atomic_write(target, content)
    return target
