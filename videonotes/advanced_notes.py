"""Deterministic offline source-linked outline; not semantic AI."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .errors import VideoNotesError
from .contracts import sha256_file
from .notes import STOPWORDS, _hash, _select, _source
from .storage import atomic_write, checked_export_paths, read_project, load_json

SCHEMA = "videonotes-source-outline-v1"
TEMPLATES = {
    "lecture": "Konspekt wykładu",
    "tutorial": "Konspekt instruktażu",
    "meeting": "Konspekt spotkania",
    "study": "Materiał do nauki",
}
DETAIL_POINTS = {"brief": 4, "standard": 10, "full": 24}


# These are keyword HINTS for selecting exact spoken quotations, not factual
# extraction, entity recognition or a generative summary. Pattern labels must
# never turn into claims unless a human checks the corresponding recording.
TEMPLATE_SIGNALS = {
    "lecture": [
        ("definition_hints", "Możliwe definicje", re.compile(
            r"\b(?:oznacza|definicja|definiujemy|nazywamy|means|is defined as)\b", re.I)),
        ("examples", "Przykłady podane w wypowiedzi", re.compile(
            r"\b(?:na przykład|przykładowo|for example|for instance)\b", re.I)),
        ("uncertain", "Wypowiedzi wymagające sprawdzenia", re.compile(
            r"\b(?:chyba|prawdopodobnie|być może|nie wiem|probably|maybe|not sure)\b", re.I)),
    ],
    "tutorial": [
        ("procedures", "Wypowiedziane kroki i polecenia", re.compile(
            r"\b(?:krok|najpierw|następnie|potem|kliknij|uruchom|wpisz|wybierz|"
            r"skonfiguruj|zapisz|first|next|then|click|run|enter|configure)\b", re.I)),
        ("checks", "Wskazówki sprawdzenia wyniku", re.compile(
            r"\b(?:sprawdź|zweryfikuj|upewnij|testuj|verify|check|confirm|test)\b", re.I)),
        ("warnings", "Wypowiedziane ostrzeżenia", re.compile(
            r"\b(?:uwaga|nie wolno|ostrożnie|błąd|niebezpieczne|warning|caution|error)\b", re.I)),
    ],
    "meeting": [
        ("decisions", "Wypowiedzi o decyzjach", re.compile(
            r"\b(?:ustalono|postanowiono|zdecydowano|decyzja|decydujemy|"
            r"agreed|decided|decision)\b", re.I)),
        ("tasks", "Wypowiedzi o zadaniach", re.compile(
            r"\b(?:zadanie|do zrobienia|termin|odpowiedzialny|wyślij|"
            r"action item|todo|to.do|deadline|assigned)\b", re.I)),
        ("unclear", "Pytania i sprawy otwarte", re.compile(
            r"\b(?:nie wiem|do wyjaśnienia|brakuje|open question|not sure)\b", re.I)),
    ],
    "study": [
        ("definitions", "Pojęcia i możliwe definicje", re.compile(
            r"\b(?:definicja|oznacza|nazywamy|to jest|means|is defined as)\b", re.I)),
        ("examples", "Przykłady do powtórzenia", re.compile(
            r"\b(?:na przykład|przykładowo|for example|for instance)\b", re.I)),
        ("uncertain", "Pytania i fragmenty do powtórzenia", re.compile(
            r"\b(?:chyba|prawdopodobnie|być może|nie wiem|maybe|not sure)\b", re.I)),
    ],
}


def _template_focus(rows: list[dict], originals: dict[str, dict],
                    template: str, detail: str) -> list[dict]:
    """Return exact citations across the WHOLE interval, not merely top N."""
    focus = []
    quota = {"brief": 2, "standard": 4, "full": 8}[detail]
    for code, title, pattern in TEMPLATE_SIGNALS[template]:
        matches = []
        for row in rows:
            if not (pattern.search(row["text"]) or (
                code in ("unclear", "uncertain") and "?" in row["text"]
            )):
                continue
            src = originals[row["id"]]
            matches.append({
                "segment_id": row["id"],
                "start_ms": row["start_ms"],
                "end_ms": src["end_ms"],
                "text": row["text"],
                "label": _category(row["text"]),
            })
            if len(matches) >= quota:
                break
        if matches:
            focus.append({"id": code, "heading": title, "citations": matches})
    return focus
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
            "template_focus": _template_focus(rows, source_by_id, template, detail),
        })
    return {
        "schema": SCHEMA, "project_id": project["id"], "source_sha256": _hash(source),
        "method": "source-linked-extractive-outline-v1", "template": template,
        "template_feature": "source-only-highlight-categories-v1",
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
        for focus in section.get("template_focus", []):
            lines.extend(["### " + focus["heading"] + " (cytaty, bez interpretacji)", ""])
            for item in focus["citations"]:
                lines.extend([
                    f"Źródło {_clock(item['start_ms'])}–{_clock(item['end_ms'])} · {item['segment_id']}",
                    "",
                ])
                lines.extend("    " + line for line in item["text"].splitlines())
                lines.append("")
        for topic in section["topics"]:
            lines.extend(["### " + topic["heading"], ""])
            for item in topic["citations"]:
                lines.extend([f"Źródło {_clock(item['start_ms'])}–{_clock(item['end_ms'])} · {item['segment_id']} · {labels[item['label']]}", ""])
                lines.extend("    " + line for line in item["text"].splitlines())
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_advanced_outline(folder: Path, *, template: str = "lecture", detail: str = "standard",
                            section_minutes: int = 10, include_docx: bool = False,
                            include_pdf: bool = False, office: str = "libreoffice") -> tuple[Path, ...]:
    folder = Path(folder)
    outline = build_advanced_outline(folder, template=template, detail=detail, section_minutes=section_minutes)
    # Paths are checked again after rendering, before the first write.
    markdown = folder / "exports" / "notes-advanced.md"
    structured = folder / "exports" / "notes-advanced.json"
    # Pre-render/validate every requested format before replacing ANY older
    # output. A missing optional LibreOffice must never erase approved notes.
    markdown_content = render_advanced_markdown(outline).encode("utf-8")
    json_content = (json.dumps(outline, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    docx = folder / "exports" / "notes-advanced.docx"
    pdf = folder / "exports" / "notes-advanced.pdf"
    docx_content = None
    if include_docx or include_pdf:
        from .docx_export import render_advanced_docx
        docx_content = render_advanced_docx(outline)
    pdf_content = None
    if include_pdf:
        from .pdf_export import render_pdf_from_docx
        pdf_content = render_pdf_from_docx(docx_content, office=office)
    # Refuse old extractive citations if manual transcript edits landed during
    # DOCX/PDF preparation; preserve all earlier exports on that failure.
    if build_advanced_outline(folder, template=template, detail=detail,
                              section_minutes=section_minutes) != outline:
        raise VideoNotesError(
            "Transkrypcja lub poprawki zmieniły się podczas tworzenia konspektu; "
            "nie nadpisano wcześniejszych plików."
        )
    required = ["notes-advanced.md", "notes-advanced.json"]
    if include_docx:
        required.append("notes-advanced.docx")
    if pdf_content is not None:
        required.append("notes-advanced.pdf")
    checked_export_paths(folder, required)
    atomic_write(markdown, markdown_content)
    atomic_write(structured, json_content)
    paths = [markdown, structured]
    if include_docx:
        atomic_write(docx, docx_content)
        paths.append(docx)
    if pdf_content is not None:
        atomic_write(pdf, pdf_content)
        paths.append(pdf)
    return tuple(paths)

def verify_advanced_outline(folder: Path, *, document: Path | None = None) -> dict:
    """Read-only full JSON recheck against current corrected local transcript.

    A correct quotation is NOT automatically a correct ASR recognition/fact.
    The method never writes, interprets audio, or invokes any remote model.
    """
    root = Path(folder)
    candidate = Path(document) if document is not None else root / "exports" / "notes-advanced.json"
    if candidate.is_symlink() or not candidate.is_file():
        raise VideoNotesError("Nie znaleziono zwykłego pliku JSON konspektu do weryfikacji.")
    saved = load_json(candidate)
    if not isinstance(saved, dict) or saved.get("schema") != SCHEMA:
        raise VideoNotesError("Nieobsługiwany format konspektu.")
    template, detail, section = saved.get("template"), saved.get("detail"), saved.get("section_minutes")
    if (type(template) is not str or template not in TEMPLATES or
            type(detail) is not str or detail not in DETAIL_POINTS or
            type(section) is not int or not 1 <= section <= 60):
        raise VideoNotesError("Nieprawidłowe parametry zapisanego konspektu.")
    expected = build_advanced_outline(root, template=template, detail=detail, section_minutes=section)
    if saved.get("project_id") != expected["project_id"]:
        raise VideoNotesError("Konspekt pochodzi z innego projektu.")
    if saved.get("source_sha256") != expected["source_sha256"]:
        raise VideoNotesError("Konspekt jest nieaktualny wobec poprawionej transkrypcji.")
    if saved != expected:
        raise VideoNotesError("Zapisany konspekt zawiera zmienione cytaty, czasy, etykiety lub sekcje.")
    return {
        "schema": SCHEMA,
        "verified": True,
        "project_id": expected["project_id"],
        "source_sha256": expected["source_sha256"],
        "document_sha256": sha256_file(candidate),
        "template": expected["template"],
        "sections": len(expected["sections"]),
        "topic_citations": sum(len(t["citations"]) for sec in expected["sections"] for t in sec["topics"]),
        "template_focus_citations": sum(len(g["citations"]) for sec in expected["sections"] for g in sec["template_focus"]),
        "report_contains_private_text": False,
        "cryptographic_signature_verified": False,
        "semantic_truth_verified": False,
    }

