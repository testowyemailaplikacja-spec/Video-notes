"""Dependency-free, offline DOCX export of source-linked outlines (VN-03).

All transcript text is inserted as literal Word text, not markup or hyperlinks.
The OOXML package deliberately contains no external relationships, macros or media.
"""
from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .errors import VideoNotesError

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

ET.register_namespace("w", W)

_LABELS = {
    "wypowiedz": "cytat źródłowy",
    "mozliwa_definicja": "możliwa definicja",
    "przyklad_w_wypowiedzi": "wzmianka o przykładzie",
    "do_sprawdzenia": "pytanie / do sprawdzenia",
}


def _w(parent: ET.Element, tag: str, **attrs: str) -> ET.Element:
    return ET.SubElement(parent, "{" + W + "}" + tag,
                         {"{" + W + "}" + key: value for key, value in attrs.items()})


def _xml(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _safe_text(text: str) -> str:
    """Remove invalid XML 1.0 characters without interpreting source markup."""
    if not isinstance(text, str):
        raise VideoNotesError("Konspekt zawiera nieprawidłowy tekst.")
    return "".join(
        c if ord(c) in (9, 10, 13) or
        0x20 <= ord(c) <= 0xD7FF or
        0xE000 <= ord(c) <= 0xFFFD or
        0x10000 <= ord(c) <= 0x10FFFF else "\uFFFD"
        for c in text
    )


def _paragraph(body: ET.Element, text: str, style: str = "Normal") -> None:
    paragraph = _w(body, "p")
    properties = _w(paragraph, "pPr")
    _w(properties, "pStyle", val=style)
    run = _w(paragraph, "r")
    for index, line in enumerate(_safe_text(text).split("\n")):
        if index:
            _w(run, "br")
        element = _w(run, "t")
        element.set(XML_SPACE, "preserve")
        element.text = line


def _styles() -> bytes:
    styles = ET.Element("{" + W + "}styles")
    for identifier, name, size, bold, level in (
        ("Normal", "Normal", "22", False, None),
        ("Title", "Title", "34", True, None),
        ("Heading1", "heading 1", "28", True, "0"),
        ("Heading2", "heading 2", "24", True, "1"),
        ("Caption", "Caption", "18", False, None),
        ("Quote", "Quote", "21", False, None),
    ):
        attrs = {"type": "paragraph", "styleId": identifier}
        if identifier == "Normal":
            attrs["default"] = "1"
        style = _w(styles, "style", **attrs)
        _w(style, "name", val=name)
        if identifier != "Normal":
            _w(style, "basedOn", val="Normal")
        if level is not None:
            _w(_w(style, "pPr"), "outlineLvl", val=level)
        run = _w(style, "rPr")
        _w(run, "rFonts", ascii="Calibri", hAnsi="Calibri")
        _w(run, "sz", val=size)
        if bold:
            _w(run, "b")
    return _xml(styles)


def _relationships(document: bool) -> bytes:
    root = ET.Element("{" + PKG + "}Relationships")
    ET.SubElement(root, "{" + PKG + "}Relationship", {
        "Id": "rId1",
        "Type": ("http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
                 + ("styles" if document else "officeDocument")),
        "Target": "styles.xml" if document else "word/document.xml",
    })
    return _xml(root)


def _content_types() -> bytes:
    root = ET.Element("{" + CT + "}Types")
    for extension, mime in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        ET.SubElement(root, "{" + CT + "}Default", {"Extension": extension, "ContentType": mime})
    for name, mime in (
        ("/word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"),
        ("/word/styles.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"),
    ):
        ET.SubElement(root, "{" + CT + "}Override", {"PartName": name, "ContentType": mime})
    return _xml(root)


def _clock(ms: int) -> str:
    hours, rest = divmod(ms // 1000, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def render_advanced_docx(outline: dict) -> bytes:
    """Return a local, Word-compatible DOCX without uploading transcript content."""
    if not isinstance(outline, dict) or outline.get("schema") != "videonotes-source-outline-v1":
        raise VideoNotesError("Nieobsługiwany format konspektu DOCX.")
    document = ET.Element("{" + W + "}document")
    body = _w(document, "body")
    _paragraph(body, outline["title"], "Title")
    _paragraph(body, "Konspekt źródłowy, nie opracowanie AI. Cytaty wymagają kontroli z nagraniem.")
    for section in outline["sections"]:
        _paragraph(body, section["heading"], "Heading1")
        for topic in section["topics"]:
            _paragraph(body, topic["heading"], "Heading2")
            for citation in topic["citations"]:
                label = _LABELS.get(citation["label"], "cytat źródłowy")
                _paragraph(body, "Źródło " + _clock(citation["start_ms"]) + "–" +
                           _clock(citation["end_ms"]) + " · " + citation["segment_id"] +
                           " · " + label, "Caption")
                _paragraph(body, citation["text"], "Quote")
    _paragraph(body, "Ograniczenia: źródłowa ekstrakcja cytatów, bez oceny pewności ASR.")
    section = _w(body, "sectPr")
    _w(section, "pgSz", w="11906", h="16838")
    _w(section, "pgMar", top="1200", right="1300", bottom="1200", left="1300",
       header="500", footer="500", gutter="0")

    return _package_document(document)


def _package_document(document: ET.Element) -> bytes:
    """Package standard OOXML parts with reproducible ZIP metadata and no links."""
    parts = {
        "[Content_Types].xml": _content_types(),
        "_rels/.rels": _relationships(False),
        "word/document.xml": _xml(document),
        "word/_rels/document.xml.rels": _relationships(True),
        "word/styles.xml": _styles(),
    }
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in parts.items():
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)
    return output.getvalue()


def render_basic_docx(notes: dict, changes: dict) -> bytes:
    """Offline DOCX for validated source-bound basic notes and manual edits.

    The caller must first run read_basic_notes() to verify the current
    transcript digest and every source citation before producing this file.
    No external links, fonts, media, macros or network APIs are involved.
    """
    if (not isinstance(notes, dict) or notes.get("schema") != "videonotes-basic-notes-v1" or
            not isinstance(changes, dict) or changes.get("schema") != "videonotes-note-edits-v1" or
            not isinstance(changes.get("edits"), dict)):
        raise VideoNotesError("Nieobsługiwana notatka podstawowa DOCX.")
    edits = changes["edits"]
    document = ET.Element("{" + W + "}document")
    body = _w(document, "body")
    _paragraph(body, notes["title"], "Title")
    _paragraph(body, "Notatka ekstrakcyjna — wypowiedzi z transkrypcji. Sprawdź treść z nagraniem.")
    for section in notes["sections"]:
        _paragraph(body, section["heading"], "Heading1")
        for point in section["points"]:
            is_manual = point["id"] in edits
            text = (edits[point["id"]] if is_manual else point["text"]).strip()
            if not text:
                continue
            suffix = " · poprawka użytkownika" if is_manual else " · cytat źródłowy"
            _paragraph(body, "Źródło " + _clock(point["start_ms"]) +
                       " · " + point["segment_id"] + suffix, "Caption")
            _paragraph(body, text, "Quote")
    _paragraph(body, "Materiał zawiera wybrane fragmenty, nie automatyczne streszczenie semantyczne.")
    section = _w(body, "sectPr")
    _w(section, "pgSz", w="11906", h="16838")
    _w(section, "pgMar", top="1200", right="1300", bottom="1200", left="1300",
       header="500", footer="500", gutter="0")
    return _package_document(document)
