"""Deterministic offline source-linked outline; not semantic AI."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .errors import VideoNotesError
from .notes import STOPWORDS, _hash, _select, _source
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



def _topic_heading(citations: list[dict], number: int) -> str:
    """Use only literal words found in the selected citations as topic hints.

    Repeated terms across distinct source segments outrank the opening excerpt;
    this is not semantic summarization or fact verification. Strip punctuation
    from the *heading only* to avoid promoting untrusted text to Markdown markup.
    """
    if not citations:
        return f"Zagadnienie {number}"
    counts: Counter[str] = Counter()
    first_spelling: dict[str, str] = {}
    for citation in citations:
        seen = set()
        for word in re.findall(r"[^\W_]+", citation["text"], re.UNICODE):
            normalized = word.casefold()
            if len(word) < 3 or normalized in STOPWORDS or len(word) > 40:
                continue
            first_spelling.setdefault(normalized, word)
            seen.add(normalized)
        counts.update(seen)
    repeated = [term for term, count in counts.items() if count >= 2]
    if repeated:
        first_rank = {term: index for index, term in enumerate(first_spelling)}
        ranked = sorted(repeated, key=lambda term: (-counts[term], first_rank[term]))
    else:
        ranked = list(first_spelling)
    fragments = []
    for term in ranked:
        item = first_spelling[term]
        if len(" ".join(fragments + [item])) > 60 or len(fragments) == 6:
            break
        fragments.append(item)
    return f"Zagadnienie {number} · {' '.join(fragments)}" if fragments else f"Zagadnienie {number}"


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
                "heading": _topic_heading(citations, offset // 4 + 1),
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
    # Pre-render and validate *all* requested formats before replacing any
    # existing output. If optional DOCX encoding fails, the user's older
    # Markdown and JSON exports must remain byte-for-byte unchanged.
    markdown_content = render_advanced_markdown(outline).encode("utf-8")
    json_content = (json.dumps(outline, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    docx = folder / "exports" / "notes-advanced.docx"
    docx_content = None
    if include_docx:
        from .docx_export import render_advanced_docx
        docx_content = render_advanced_docx(outline)
    atomic_write(markdown, markdown_content)
    atomic_write(structured, json_content)
    if docx_content is not None:
        atomic_write(docx, docx_content)
        return markdown, structured, docx
    return markdown, structured
