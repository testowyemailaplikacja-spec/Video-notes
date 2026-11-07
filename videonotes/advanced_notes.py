"""Deterministic offline source-linked outline; not semantic AI."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import VideoNotesError
from .notes import _hash, _select, _source
from .storage import atomic_write, read_project

SCHEMA = "videonotes-source-outline-v1"
TEMPLATES = {
    "lecture": "Konspekt wykładu",
    "tutorial": "Konspekt instruktażu",
    "meeting": "Konspekt spotkania",
    "study": "Materiał do nauki",
}
DETAIL_POINTS = {"brief": 4, "standard": 10, "full": 24}
UNCERTAIN = re.compile(r"\b(?:chyba|prawdopodobnie|nie wiem|być może|maybe|probably|not sure)\b", re.I)
EXAMPLE = re.compile(r"\b(?:na przykład|przykładowo|for example|for instance)\b", re.I)
DEFINITION = re.compile(r"\b(?:definicja|oznacza|nazywamy|to jest|is defined as|means)\b", re.I)


def _clock(ms: int) -> str:
    hours, rem = divmod(ms // 1000, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _category(text: str) -> str:
    if "?" in text or UNCERTAIN.search(text):
        return "do_sprawdzenia"
    if EXAMPLE.search(text):
        return "przyklad_w_wypowiedzi"
    if DEFINITION.search(text):
        return "mozliwa_definicja"
    return "wypowiedz"


def build_advanced_outline(folder: Path, *, template: str = "lecture", detail: str = "standard",
                           section_minutes: int = 10) -> dict:
    """Make a multi-level time-based outline from completed corrected transcript."""
    if template not in TEMPLATES or detail not in DETAIL_POINTS or type(section_minutes) is not int or not 1 <= section_minutes <= 60:
        raise VideoNotesError("Nieprawidłowy szablon, szczegółowość lub czas sekcji.")
    project, transcript, edits = read_project(Path(folder))
    duration = project["source"]["duration_ms"]
    chunk = project["processing"]["chunk_ms"]
    total = (duration + chunk - 1) // chunk
    if len(transcript["completed_chunks"]) != total:
        raise VideoNotesError("Ukończ transkrypcję przed tworzeniem konspektu.")
    source = _source(transcript, edits)
    if not source:
        raise VideoNotesError("Transkrypcja jest pusta. Nie można utworzyć konspektu.")
    source_by_id = {item["id"]: item for item in transcript["segments"]}
    span = section_minutes * 60_000
    groups: dict[int, list[dict]] = {}
    for item in source:
        groups.setdefault(item["start_ms"] // span, []).append(item)
    sections = []
    for index, rows in sorted(groups.items()):
        selected = _select(rows, DETAIL_POINTS[detail])
        topics = []
        for offset in range(0, len(selected), 4):
            citations = []
            for row in selected[offset:offset + 4]:
                original = source_by_id[row["id"]]
                citations.append({
                    "segment_id": row["id"], "start_ms": row["start_ms"],
                    "end_ms": original["end_ms"], "text": row["text"],
                    "label": _category(row["text"]),
                })
            topics.append({
                "id": f"topic-{index:06d}-{offset // 4:03d}",
                "heading": f"Zagadnienie {offset // 4 + 1}",
                "citations": citations,
            })
        sections.append({
            "id": f"section-{index:06d}",
            "heading": f"Część {len(sections) + 1} · {_clock(index * span)}–{_clock(min(duration, (index + 1) * span))}",
            "topics": topics,
        })
    return {
        "schema": SCHEMA, "project_id": project["id"], "source_sha256": _hash(source),
        "method": "source-linked-extractive-outline-v1", "template": template,
        "detail": detail, "section_minutes": section_minutes,
        "title": TEMPLATES[template], "complete": True, "sections": sections,
        "limitations": [
            "To grupowanie cytatów w czasie, nie streszczenie semantyczne.",
            "Etykiety definicji i przykładów są heurystyczne; wymagają kontroli człowieka.",
            "Niska pewność ASR nie jest mierzona; pytanie nie oznacza błędu ASR.",
        ],
    }


def render_advanced_markdown(outline: dict) -> str:
    """Untrusted source text appears in indented Markdown code blocks."""
    if outline.get("schema") != SCHEMA:
        raise VideoNotesError("Nieobsługiwany format konspektu.")
    lines = [
        "# " + outline["title"], "",
        "> Konspekt źródłowy, nie opracowanie AI. Cytaty sprawdź z nagraniem.",
        "> Etykiety definicji/przykładów są wyłącznie wskazówkami.", "",
    ]
    labels = {"do_sprawdzenia": "pytanie / do sprawdzenia",
              "przyklad_w_wypowiedzi": "wzmianka o przykładzie",
              "mozliwa_definicja": "możliwa definicja",
              "wypowiedz": "cytat źródłowy"}
    for section in outline["sections"]:
        lines.extend(["## " + section["heading"], ""])
        for topic in section["topics"]:
            lines.extend(["### " + topic["heading"], ""])
            for item in topic["citations"]:
                lines.extend([f"Źródło {_clock(item['start_ms'])}–{_clock(item['end_ms'])} · {item['segment_id']} · {labels[item['label']]}", ""])
                lines.extend("    " + line for line in item["text"].splitlines())
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_advanced_outline(folder: Path, *, template: str = "lecture", detail: str = "standard",
                            section_minutes: int = 10, include_docx: bool = False) -> tuple[Path, ...]:
    folder = Path(folder)
    outline = build_advanced_outline(folder, template=template, detail=detail, section_minutes=section_minutes)
    markdown = folder / "exports" / "notes-advanced.md"
    structured = folder / "exports" / "notes-advanced.json"
    atomic_write(markdown, render_advanced_markdown(outline).encode("utf-8"))
    atomic_write(structured, (json.dumps(outline, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if include_docx:
        from .docx_export import render_advanced_docx
        docx = folder / "exports" / "notes-advanced.docx"
        atomic_write(docx, render_advanced_docx(outline))
        return markdown, structured, docx
    return markdown, structured
