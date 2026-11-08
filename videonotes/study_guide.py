"""Offline source-attributed study guide, with no generative factual synthesis.

Study guide is a *separate*, regenerated projection of completed transcript.
It never overwrites transcript.json, notes.json, note-edits or note history.
Every displayed quotation carries the original segment ID and timestamps.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .advanced_notes import _category, _clock
from .contracts import sha256_file
from .errors import VideoNotesError
from .notes import _hash, _select, _source, _tokens
from .storage import atomic_write, read_project, load_json

SCHEMA = "videonotes-study-guide-v1"
DETAIL_LIMITS = {"brief": 3, "standard": 6, "full": 12}
CATEGORIES = (
    ("mozliwa_definicja", "definition_hints"),
    ("przyklad_w_wypowiedzi", "examples"),
    ("do_sprawdzenia", "questions_or_uncertainties"),
)


def _citation(row: dict, raw: dict) -> dict:
    return {
        "segment_id": row["id"],
        "start_ms": row["start_ms"],
        "end_ms": raw["end_ms"],
        "text": row["text"],
    }


def _common_terms(rows: list[dict], *, limit: int = 4) -> list[dict]:
    """Find repeated words across different source segments, never compose claims."""
    counts: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    first_id: dict[str, str] = {}
    for row in rows:
        terms = _tokens(row["text"])
        counts.update(terms)
        for word in re.findall(r"[^\W_]+", row["text"], re.UNICODE):
            key = word.casefold()
            if (key in terms and len(word) <= 32 and
                    any(char.isalpha() for char in word)):
                spelling.setdefault(key, word)
                first_id.setdefault(key, row["id"])
    return [
        {"term": spelling[key], "mentions_in_segments": counts[key],
         "first_segment_id": first_id[key]}
        for key in sorted(
            (term for term in counts if counts[term] >= 2 and term in spelling),
            key=lambda term: -counts[term],
        )[:limit]
    ]


def build_study_guide(folder: Path, *, section_minutes: int = 5,
                      detail: str = "standard") -> dict:
    """Create an auditable, short, extractive revision plan from local speech."""
    if (type(section_minutes) is not int or not 1 <= section_minutes <= 60
            or detail not in DETAIL_LIMITS):
        raise VideoNotesError("Nieprawidłowy czas sekcji lub poziom szczegółowości.")
    project, transcript, edits = read_project(Path(folder))
    duration = project["source"]["duration_ms"]
    chunk = project["processing"]["chunk_ms"]
    expected = (duration + chunk - 1) // chunk
    if transcript["completed_chunks"] != list(range(expected)):
        raise VideoNotesError("Ukończ transkrypcję przed utworzeniem przewodnika do nauki.")
    source = _source(transcript, edits)
    if not source:
        raise VideoNotesError("Transkrypcja jest pusta. Nie można przygotować przewodnika.")
    raw = {segment["id"]: segment for segment in transcript["segments"]}
    groups: dict[int, list[dict]] = {}
    span = section_minutes * 60_000
    for row in source:
        groups.setdefault(row["start_ms"] // span, []).append(row)
    sections: list[dict] = []
    for index, rows in sorted(groups.items()):
        quotes = _select(rows, DETAIL_LIMITS[detail])
        key_quotes = [_citation(row, raw[row["id"]]) for row in quotes]
        # This is a literal, attributed source quotation, NOT a paraphrased
        # "AI summary". Never concatenate text into a new factual statement.
        overview_quote = key_quotes[0]
        examples = {}
        for tag, field in CATEGORIES:
            matches = [row for row in rows if _category(row["text"]) == tag]
            examples[field] = [_citation(row, raw[row["id"]]) for row in matches[:3]]
        terms = _common_terms(rows)
        top_words = " ".join(entry["term"] for entry in terms[:3])
        heading = (f"Część {len(sections) + 1} · {_clock(index * span)}"
                   f"–{_clock(min(duration, (index + 1) * span))}")
        if top_words:
            heading += " · " + top_words
        sections.append({
            "id": f"study-{index:06d}",
            "heading": heading,
            "overview_quote": overview_quote,
            "key_quotes": key_quotes,
            "common_terms": terms,
            **examples,
        })
    return {
        "schema": SCHEMA,
        "project_id": project["id"],
        "source_sha256": _hash(source),
        "method": "extractive-source-quote-study-v1",
        "title": "Przewodnik do nauki — cytaty i zagadnienia",
        "detail": detail,
        "section_minutes": section_minutes,
        "complete": True,
        "sections": sections,
        "limitations": [
            "Skrót to cytaty, nie semantyczne streszczenie ani weryfikacja faktów.",
            "Definicje, przykłady i pytania wykrywane są tylko heurystycznie.",
            "Pewność rozpoznawania mowy nie jest oceniana; należy sprawdzić nagranie.",
        ],
    }


def _render_quote(lines: list[str], quote: dict) -> None:
    lines.extend([
        f"Źródło {_clock(quote['start_ms'])}–{_clock(quote['end_ms'])} · {quote['segment_id']}",
        "",
    ])
    # Four spaces force Markdown to display hostile HTML/links literally.
    lines.extend("    " + line for line in quote["text"].splitlines())
    lines.append("")


def render_study_guide_markdown(guide: dict) -> str:
    if guide.get("schema") != SCHEMA:
        raise VideoNotesError("Nieobsługiwany schemat przewodnika do nauki.")
    lines = [
        "# " + guide["title"], "",
        "> Przewodnik zawiera wyłącznie dosłowne fragmenty transkrypcji.",
        "> Nagłówki oraz etykiety są wskazówkami, nie rozumowaniem AI.", "",
        "## Spis treści", "",
    ]
    for section in guide["sections"]:
        lines.append(f"{section['id']} · {section['heading']}")
    lines.append("")
    labels = [
        ("definition_hints", "Możliwe definicje w wypowiedzi"),
        ("examples", "Przykłady w wypowiedzi"),
        ("questions_or_uncertainties", "Pytania i fragmenty do sprawdzenia"),
    ]
    for section in guide["sections"]:
        lines.extend(["## " + section["heading"], "",
                      "### Krótki fragment źródłowy", ""])
        _render_quote(lines, section["overview_quote"])
        terms = section["common_terms"]
        if terms:
            lines.extend(["### Powtarzające się pojęcia (nie weryfikowane)", ""])
            for term in terms:
                lines.append(
                    f"{term['term']} · {term['mentions_in_segments']} fragmentów"
                    f" · pierwsze źródło {term['first_segment_id']}"
                )
            lines.append("")
        lines.extend(["### Kluczowe cytaty", ""])
        for quote in section["key_quotes"]:
            _render_quote(lines, quote)
        for name, heading in labels:
            if section[name]:
                lines.extend(["### " + heading, ""])
                for quote in section[name]:
                    _render_quote(lines, quote)
    lines.extend([
        "## Ograniczenia", "",
        "To zestawienie wypowiedzi źródłowych; przed nauką sprawdź poprawność ASR.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def export_study_guide(folder: Path, *, section_minutes: int = 5,
                       detail: str = "standard", include_docx: bool = False,
                       include_pdf: bool = False,
                       office: str = "libreoffice") -> tuple[Path, ...]:
    """Pre-render all formats before publishing to avoid partial export on failure.

    Multiple files still cannot be atomically replaced as a single transaction.
    """
    guide = build_study_guide(folder, section_minutes=section_minutes, detail=detail)
    folder = Path(folder)
    markdown = folder / "exports" / "notes-study.md"
    structured = folder / "exports" / "notes-study.json"
    docx = folder / "exports" / "notes-study.docx"
    pdf = folder / "exports" / "notes-study.pdf"
    md_bytes = render_study_guide_markdown(guide).encode("utf-8")
    json_bytes = (json.dumps(guide, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    docx_bytes = None
    pdf_bytes = None
    if include_docx or include_pdf:
        from .docx_export import render_study_guide_docx
        docx_bytes = render_study_guide_docx(guide)
    if include_pdf:
        from .pdf_export import render_pdf_from_docx
        pdf_bytes = render_pdf_from_docx(docx_bytes, office=office)

    atomic_write(markdown, md_bytes)
    atomic_write(structured, json_bytes)
    result = [markdown, structured]
    if include_docx:
        atomic_write(docx, docx_bytes)
        result.append(docx)
    if include_pdf:
        atomic_write(pdf, pdf_bytes)
        result.append(pdf)
    return tuple(result)


def verify_study_guide(folder: Path, *, document: Path | None = None) -> dict:
    """Verify a saved JSON document against the *current* local transcript.

    No edits, downloads, exports, network, or automatic repair. Exact
    deterministic comparison rejects invented quotes, altered labels,
    timestamps, word counts, and obsolete/source-mismatched documents.
    Markdown and DOCX are not independently signature-verified by this check.
    """
    root = Path(folder)
    candidate = Path(document) if document is not None else root / "exports" / "notes-study.json"
    if candidate.is_symlink() or not candidate.is_file():
        raise VideoNotesError("Nie znaleziono zwykłego pliku JSON przewodnika do sprawdzenia.")
    content = load_json(candidate)
    if not isinstance(content, dict) or content.get("schema") != SCHEMA:
        raise VideoNotesError("Nieobsługiwany format zapisanego przewodnika do nauki.")
    detail = content.get("detail")
    minutes = content.get("section_minutes")
    if type(minutes) is not int or not 1 <= minutes <= 60 or not isinstance(detail, str) or detail not in DETAIL_LIMITS:
        raise VideoNotesError("Niepoprawne parametry źródłowego przewodnika.")
    expected = build_study_guide(root, section_minutes=minutes, detail=detail)
    if content.get("project_id") != expected["project_id"]:
        raise VideoNotesError("Przewodnik pochodzi z innego projektu.")
    if content.get("source_sha256") != expected["source_sha256"]:
        raise VideoNotesError(
            "Przewodnik jest nieaktualny względem transkrypcji; wygeneruj nowy."
        )
    if content != expected:
        raise VideoNotesError(
            "Cytaty, czasy, klasyfikacje lub struktura przewodnika zostały zmienione; "
            "nie można potwierdzić pochodzenia."
        )
    return {
        "schema": SCHEMA,
        "verified": True,
        "project_id": expected["project_id"],
        "source_sha256": expected["source_sha256"],
        "document_sha256": sha256_file(candidate),
        "sections": len(expected["sections"]),
        "source_citations": sum(
            len(section["key_quotes"]) for section in expected["sections"]
        ),
        "private_text_in_report": False,
        "report_only_checks_json": True,
        "cryptographic_signature_verified": False,
    }
