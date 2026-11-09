"""Optional Tk review of offline semantic drafts, using the same CLI audit backend.

No automatic approval, file uploads, network calls, or background Tk mutations.
All decisions are user-confirmed and permanently source-bound on disk.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .errors import VideoNotesError
from .semantic_draft import verify_semantic_draft
from .semantic_review import (
    export_reviewed_semantic_markdown, init_semantic_review,
    mark_semantic_claim, semantic_review_status,
)
from .storage import load_json


class SemanticReviewWindow:
    def __init__(self, parent: tk.Misc, project: Path,
                 *, guard: Callable[[], bool] = lambda: False):
        self.project = Path(project)
        self.guard = guard
        self.top = tk.Toplevel(parent)
        self.top.title("KWN — ręczna kontrola szkicu AI (bez automatycznej akceptacji)")
        self.top.geometry("940x720")
        self.top.minsize(800, 590)
        self.draft_path = tk.StringVar(master=self.top)
        self.review_path = tk.StringVar(master=self.top)
        self.reviewer = tk.StringVar(master=self.top)
        self.message = tk.StringVar(master=self.top, value="Wskaż szkic JSON, następnie nowy lub istniejący katalog oceny.")
        self.claims: dict[str, dict] = {}

        main = ttk.Frame(self.top, padding=12)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Szkic AI nie jest źródłem prawdy. Porównaj KAŻDE twierdzenie z oryginalnym nagraniem.",
                  wraplength=865).pack(anchor="w", pady=(0, 8))
        files = ttk.LabelFrame(main, text="Lokalne pliki i tożsamość deklarowana przez użytkownika", padding=8)
        files.pack(fill="x", pady=4)
        self._field(files, "Szkic .json:", self.draft_path, self._browse_draft)
        self._field(files, "Katalog recenzji:", self.review_path, self._browse_review)
        self._field(files, "Etykieta recenzenta:", self.reviewer, None)

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=8)
        self.buttons = {}
        for title, action in (
            ("Wczytaj szkic", self.reload),
            ("Utwórz nową recenzję", self.start_review),
            ("Zatwierdź", lambda: self.mark("approve")),
            ("Odrzuć", lambda: self.mark("reject")),
            ("Sprawdź stan", self.reload),
            ("Eksportuj zaakceptowane MD", self.export),
        ):
            button = ttk.Button(actions, text=title, command=action)
            button.pack(side="left", padx=2)
            self.buttons[title] = button

        split = ttk.PanedWindow(main, orient="vertical")
        split.pack(fill="both", expand=True)
        upper = ttk.Frame(split, padding=4)
        split.add(upper, weight=1)
        columns = ("decision", "sources")
        self.tree = ttk.Treeview(upper, columns=columns, show=("tree", "headings"),
                                 selectmode="browse", height=8)
        self.tree.heading("#0", text="ID twierdzenia")
        self.tree.heading("decision", text="Decyzja użytkownika")
        self.tree.heading("sources", text="Źródła")
        self.tree.column("#0", width=235, stretch=True)
        self.tree.column("decision", width=185, stretch=True)
        self.tree.column("sources", width=95, stretch=False)
        scroll = ttk.Scrollbar(upper, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        lower = ttk.Frame(split, padding=4)
        split.add(lower, weight=2)
        ttk.Label(lower, text="Treść twierdzenia i cytaty z poprawionej transkrypcji:").pack(anchor="w")
        self.details = tk.Text(lower, wrap="word", height=12, state="disabled")
        self.details.pack(fill="both", expand=True)
        ttk.Label(main, textvariable=self.message, wraplength=880).pack(anchor="w", pady=6)
        ttk.Label(main, text="Weryfikacja programu dotyczy źródła i integralności, nie prawdziwości faktów ani tożsamości recenzenta.",
                  wraplength=880).pack(anchor="w")

    def _field(self, parent, title: str, variable: tk.StringVar,
               browse: Callable[[], None] | None) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=title, width=23).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=5)
        if browse:
            ttk.Button(row, text="Wybierz", command=browse).pack(side="right")

    def _browse_draft(self) -> None:
        value = filedialog.askopenfilename(parent=self.top, title="Wybierz szkic AI JSON",
                                           filetypes=[("JSON", "*.json")])
        if value:
            self.draft_path.set(value)
            self.reload()

    def _browse_review(self) -> None:
        value = filedialog.askdirectory(parent=self.top, title="Wybierz istniejący katalog recenzji")
        if value:
            self.review_path.set(value)
            self.reload()

    def _ready(self) -> bool:
        if self.guard():
            messagebox.showwarning("Ocena szkicu", "Zapisz poprawkę transkrypcji albo zakończ trwającą operację.",
                                   parent=self.top)
            return False
        return True

    def _paths(self) -> tuple[Path, Path]:
        draft_name = self.draft_path.get().strip()
        if not draft_name:
            raise VideoNotesError("Wskaż lokalny, wcześniej utworzony szkic semantyczny JSON.")
        draft = Path(draft_name)
        review_name = self.review_path.get().strip()
        if not review_name:
            review_name = str(draft.with_suffix("")) + "-recenzja-001"
            self.review_path.set(review_name)
        return draft, Path(review_name)

    def _display_error(self, error: Exception) -> None:
        # Backend errors are intended to be path/claim agnostic and contain no
        # recordings, model output or access tokens.
        messagebox.showerror("Ocena szkicu", str(error) if isinstance(error, VideoNotesError)
                             else "Nie udało się odczytać lub zapisać lokalnej oceny.",
                             parent=self.top)

    def reload(self) -> None:
        if not self._ready():
            return
        try:
            draft, review = self._paths()
            verify_semantic_draft(self.project, draft)
            data = load_json(draft)
            claims = {}
            for section in data["sections"]:
                for claim in section["claims"]:
                    claims[claim["id"]] = claim
            decisions = {}
            if review.is_dir() or review.is_symlink():
                counts = semantic_review_status(self.project, draft, review)
                decisions = {
                    cid: load_json(review / "decisions" / (cid + ".json"))["decision"]
                    for cid in claims if (review / "decisions" / (cid + ".json")).exists()
                }
                self.message.set(
                    "Decyzje użytkownika: zatwierdzone " + str(counts["approved_by_user"]) +
                    ", odrzucone " + str(counts["rejected_by_user"]) +
                    ", pozostałe " + str(counts["pending"]) +
                    ". Żaden wynik nie ma niezależnej weryfikacji faktów."
                )
            else:
                self.message.set("Szkic wczytany. Nie ma jeszcze recenzji. Wybierz 'Utwórz nową recenzję'.")
            self.claims = claims
            self.tree.delete(*self.tree.get_children())
            for cid, claim in claims.items():
                label = {"approve": "Zatwierdzone przez użytkownika",
                         "reject": "Odrzucone"}.get(decisions.get(cid), "Nieocenione")
                self.tree.insert("", "end", iid=cid, text=cid,
                                 values=(label, len(claim["citations"])))
            if claims:
                self.tree.selection_set(next(iter(claims)))
                self._show_selected()
        except (VideoNotesError, OSError, KeyError, TypeError, ValueError) as error:
            self._display_error(error)

    def _show_selected(self, event=None) -> None:
        chosen = self.tree.selection()
        if not chosen or chosen[0] not in self.claims:
            return
        claim = self.claims[chosen[0]]
        parts = [
            "TWIERDZENIE: " + chosen[0], "",
            claim["text"], "",
            "CYTATY — porównaj z nagraniem:", "",
        ]
        for source in claim["citations"]:
            parts.append(
                f"{source['segment_id']} · {source['start_ms']}–{source['end_ms']} ms"
            )
            parts.extend([source["text"], ""])
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(parts))
        self.details.configure(state="disabled")

    def start_review(self) -> None:
        if not self._ready():
            return
        try:
            draft, review = self._paths()
            init_semantic_review(self.project, draft, review)
            self.reload()
        except (VideoNotesError, OSError, KeyError, TypeError, ValueError) as error:
            self._display_error(error)

    def mark(self, decision: str) -> None:
        if not self._ready():
            return
        chosen = self.tree.selection()
        if not chosen or chosen[0] not in self.claims:
            messagebox.showwarning("Ocena szkicu", "Zaznacz jedno twierdzenie przed wydaniem decyzji.",
                                   parent=self.top)
            return
        reviewer = self.reviewer.get().strip()
        if not reviewer:
            messagebox.showwarning("Ocena szkicu", "Podaj etykietę recenzenta.",
                                   parent=self.top)
            return
        verb = "zatwierdzić" if decision == "approve" else "odrzucić"
        confirmed = messagebox.askyesno(
            "Świadoma decyzja",
            "Czy po porównaniu z nagraniem chcesz " + verb +
            " twierdzenie " + chosen[0] + "?\n"
            "Decyzja w tym katalogu jest nieodwracalna. Pomyłka wymaga nowej recenzji.",
            parent=self.top,
        )
        if not confirmed:
            return
        try:
            draft, review = self._paths()
            mark_semantic_claim(
                self.project, draft, review, claim_id=chosen[0],
                decision=decision, reviewer=reviewer, confirm=True,
            )
            previously = chosen[0]
            self.reload()
            if previously in self.claims:
                self.tree.selection_set(previously)
                self._show_selected()
        except (VideoNotesError, OSError, KeyError, TypeError, ValueError) as error:
            self._display_error(error)

    def export(self) -> None:
        if not self._ready():
            return
        try:
            draft, review = self._paths()
            state = semantic_review_status(self.project, draft, review)
            if state["pending"]:
                raise VideoNotesError("Nie można eksportować, dopóki nie oceniono wszystkich twierdzeń.")
            if not state["approved_by_user"]:
                raise VideoNotesError("Nie ma zaakceptowanych twierdzeń do eksportu.")
            output = filedialog.asksaveasfilename(
                parent=self.top, title="Zapisz NOWĄ notatkę po ręcznej ocenie",
                defaultextension=".md", filetypes=[("Markdown", "*.md")],
            )
            if not output:
                return
            export_reviewed_semantic_markdown(self.project, draft, review, Path(output))
            self.message.set("Eksport zapisano lokalnie. Program nie potwierdza prawdziwości treści.")
        except (VideoNotesError, OSError, KeyError, TypeError, ValueError) as error:
            self._display_error(error)
