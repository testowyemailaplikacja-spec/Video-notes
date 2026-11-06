"""Simple real offline Windows UI. Packaging and hardware acceptance remain VN-06."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import VideoNotesError
from .exports import edit_segment, export_project
from .media import probe
from .pipeline import create_project, transcribe_project
from .storage import read_project


class VideoNotesWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Video Notes — lokalna transkrypcja (wersja rozwojowa)")
        root.minsize(740, 540)
        self.source = tk.StringVar()
        self.project = tk.StringVar()
        self.model = tk.StringVar()
        self.engine = tk.StringVar(value="whisper-cli")
        self.language = tk.StringVar(value="pl")
        self.stream = tk.StringVar()
        self.streams: dict[str, int] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel = threading.Event()
        self.active = False
        self._rows: dict[str, dict] = {}
        self._build()
        self.root.after(100, self._drain)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Video Notes", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Nagrania i transkrypcje pozostają na tym komputerze. Żadne pliki nie są wysyłane do chmury.", wraplength=700).pack(anchor="w", pady=(0, 12))
        config = ttk.LabelFrame(outer, text="Źródło i lokalny model", padding=10)
        config.pack(fill="x")
        self._line(config, "Nagranie OBS", self.source, self._browse_source)
        self._line(config, "Katalog projektu", self.project, self._browse_project)
        self._line(config, "Model Whisper .bin", self.model, lambda: self._select_file(self.model, [("Model bin", "*.bin"), ("Wszystkie", "*.*")]))
        self._line(config, "whisper-cli (.exe)", self.engine, lambda: self._select_file(self.engine, [("Program", "*.exe"), ("Wszystkie", "*.*")]))
        row = ttk.Frame(config)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Ścieżka audio", width=20).pack(side="left")
        self.stream_box = ttk.Combobox(row, textvariable=self.stream, state="readonly", width=44)
        self.stream_box.pack(side="left", padx=5)
        ttk.Button(row, text="Wykryj ścieżki", command=self._inspect).pack(side="left")
        ttk.Label(row, text="Język:").pack(side="left", padx=(18, 5))
        ttk.Combobox(row, textvariable=self.language, state="readonly", values=["pl", "en", "auto"], width=7).pack(side="left")
        commands = ttk.Frame(outer)
        commands.pack(fill="x", pady=12)
        self.start_button = ttk.Button(commands, text="Rozpocznij", command=lambda: self._work(resume=False))
        self.start_button.pack(side="left", padx=(0, 8))
        self.resume_button = ttk.Button(commands, text="Wznów projekt", command=lambda: self._work(resume=True))
        self.resume_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ttk.Button(commands, text="Przerwij po fragmencie", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 8))
        ttk.Button(commands, text="Otwórz projekt", command=self._load).pack(side="left")
        self.status = tk.StringVar(value="Gotowe. Wybierz plik i lokalny model.")
        ttk.Label(outer, textvariable=self.status, wraplength=700).pack(anchor="w", pady=4)
        self.progress = ttk.Progressbar(outer, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=4)
        sections = ttk.PanedWindow(outer, orient="horizontal")
        sections.pack(fill="both", expand=True, pady=(8, 0))
        left = ttk.LabelFrame(sections, text="Segmenty transkrypcji")
        right = ttk.LabelFrame(sections, text="Poprawka zaznaczonego segmentu")
        sections.add(left, weight=3)
        sections.add(right, weight=2)
        self.segments = ttk.Treeview(left, columns=("time", "content"), show="headings", selectmode="browse")
        self.segments.heading("time", text="Czas (s)")
        self.segments.heading("content", text="Tekst")
        self.segments.column("time", width=95, stretch=False)
        self.segments.column("content", width=320)
        self.segments.pack(fill="both", expand=True)
        self.segments.bind("<<TreeviewSelect>>", self._selected)
        self.edit_text = tk.Text(right, wrap="word", height=9, undo=True)
        self.edit_text.pack(fill="both", expand=True)
        ttk.Button(right, text="Zapisz poprawkę i eksport", command=self._save_edit).pack(anchor="e", pady=6)
        ttk.Label(right, text="Oryginalny wynik ASR pozostaje nietknięty.", wraplength=245).pack(anchor="w")

    def _line(self, parent: ttk.LabelFrame, title: str, value: tk.StringVar, callback) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=title, width=20).pack(side="left")
        ttk.Entry(row, textvariable=value).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row, text="Wybierz", command=callback).pack(side="left")

    def _select_file(self, var: tk.StringVar, types) -> None:
        filename = filedialog.askopenfilename(filetypes=types)
        if filename:
            var.set(filename)

    def _browse_source(self) -> None:
        self._select_file(self.source, [("OBS / audio", "*.mp4 *.mkv *.webm *.wav"), ("Wszystkie", "*.*")])
        if self.source.get():
            self._inspect()

    def _browse_project(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.project.set(folder)

    def _inspect(self) -> None:
        try:
            details = probe(Path(self.source.get()))
            self.streams = {f"{s['index']}: {s['codec']} · {s['channels']} kanały · {s['language'] or 'bez języka'}": s["index"] for s in details["audio_streams"]}
            labels = list(self.streams)
            self.stream_box.configure(values=labels)
            self.stream.set(labels[0] if len(labels) == 1 else "")
            self.status.set(f"Źródło ma {len(labels)} ścieżek audio; wybierz jedną. Czas: {details['duration_ms']/1000:.1f} s.")
        except VideoNotesError as error:
            messagebox.showerror("Video Notes", str(error))

    def _work(self, *, resume: bool) -> None:
        if self.active:
            return
        project_path = self.project.get().strip()
        if not project_path:
            messagebox.showwarning("Video Notes", "Wybierz katalog projektu.")
            return
        if not resume and (not self.source.get().strip() or not self.model.get().strip()):
            messagebox.showwarning("Video Notes", "Wskaż źródło i lokalny model.")
            return
        if not resume and self.stream.get() not in self.streams:
            messagebox.showwarning("Video Notes", "Wykryj i wybierz właściwą ścieżkę audio.")
            return
        self.cancel.clear()
        self.active = True
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        def worker() -> None:
            try:
                if not resume:
                    create_project(Path(self.source.get()), Path(project_path), model=Path(self.model.get()), whisper_cli=self.engine.get(),
                                   stream=self.streams[self.stream.get()], language=self.language.get())
                transcribe_project(Path(project_path), progress=lambda done, total: self.events.put(("progress", (done, total))), cancel=self.cancel.is_set)
                export_project(Path(project_path))
                self.events.put(("done", "Transkrypcja i eksport zakończone."))
            except VideoNotesError as error:
                self.events.put(("error", str(error)))
            except Exception:
                self.events.put(("error", "Wewnętrzny błąd. Projekt zachowany; sprawdź log testowy przed wznowieniem."))
        threading.Thread(target=worker, name="vn-transcribe", daemon=True).start()

    def _drain(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "progress":
                    done, total = data
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = done
                    self.status.set(f"Zapisano {done} z {total} fragmentów. Można wznowić później.")
                elif kind in {"error", "done"}:
                    self.active = False
                    self.start_button.configure(state="normal")
                    self.resume_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status.set(str(data))
                    self._load(silent=True)
                    if kind == "error":
                        messagebox.showwarning("Video Notes", str(data))
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _load(self, silent: bool = False) -> None:
        try:
            _project, transcript, edits = read_project(Path(self.project.get()))
            self.segments.delete(*self.segments.get_children())
            self._rows.clear()
            for item in transcript["segments"]:
                value = edits["edits"].get(item["id"], item["text"])
                self._rows[item["id"]] = item
                self.segments.insert("", "end", iid=item["id"], values=(f"{item['start_ms']/1000:.2f}", value.replace("\n", " ")))
            self.status.set(f"Załadowano {len(transcript['segments'])} segmentów. Poprawki są zapisywane oddzielnie.")
        except VideoNotesError as error:
            if not silent:
                messagebox.showerror("Video Notes", str(error))

    def _selected(self, _event=None) -> None:
        selection = self.segments.selection()
        if selection:
            _project, _transcript, edits = read_project(Path(self.project.get()))
            item = self._rows[selection[0]]
            self.edit_text.delete("1.0", "end")
            self.edit_text.insert("1.0", edits["edits"].get(item["id"], item["text"]))

    def _save_edit(self) -> None:
        if self.active:
            messagebox.showwarning("Video Notes", "Zakończ przetwarzanie przed ręczną edycją.")
            return
        selection = self.segments.selection()
        if not selection:
            messagebox.showinfo("Video Notes", "Zaznacz segment.")
            return
        try:
            edit_segment(Path(self.project.get()), selection[0], self.edit_text.get("1.0", "end-1c"))
            export_project(Path(self.project.get()))
            self._load(silent=True)
            self.status.set("Poprawkę i eksport zapisano lokalnie.")
        except VideoNotesError as error:
            messagebox.showerror("Video Notes", str(error))


def launch() -> None:
    root = tk.Tk()
    VideoNotesWindow(root)
    root.mainloop()
