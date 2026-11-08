"""Simple real offline Windows UI. Packaging and hardware acceptance remain VN-06."""
from __future__ import annotations

import os
import queue
import threading
import uuid
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import VideoNotesError
from .exports import edit_segment, export_project
from .media import probe
from .microphone import record_microphone, list_microphone_devices, join_finished_recording
from .audio_diagnostics import analyze_finished_recording
from .notes import generate_basic_notes, read_basic_notes, edit_note_point, export_basic_notes, export_basic_notes_docx
from .advanced_notes import export_advanced_outline
from .study_guide import export_study_guide, verify_study_guide
from .pdf_export import export_basic_notes_pdf
from .note_revisions import regenerate_basic_notes, list_note_versions, restore_note_version, recover_interrupted_note_update
from .pipeline import create_project, transcribe_project
from .storage import read_project


class VideoNotesWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Video Notes — lokalna transkrypcja (wersja rozwojowa)")
        root.minsize(740, 540)
        self.source = tk.StringVar()
        self.project = tk.StringVar()
        self.model = tk.StringVar(value=os.environ.get("VIDEO_NOTES_MODEL", ""))
        self.engine = tk.StringVar(value="whisper-cli")
        self.language = tk.StringVar(value="pl")
        self.stream = tk.StringVar()
        self.streams: dict[str, int] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel = threading.Event()
        self.active = False
        self.mic_stop = threading.Event()
        self.mic_pause = threading.Event()
        self.mic_resume = threading.Event()
        self.mic_controls: dict = {}
        self._rows: dict[str, dict] = {}
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self.root.after(100, self._drain)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Video Notes", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Nagrania i transkrypcje pozostają na tym komputerze. Żadne pliki nie są wysyłane do chmury.", wraplength=700).pack(anchor="w", pady=(0, 12))
        config = ttk.LabelFrame(outer, text="Źródło i lokalny model", padding=10)
        config.pack(fill="x")
        self._line(config, "Nagranie lub audio", self.source, self._browse_source)
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
        ttk.Button(outer, text="Notatka podstawowa — wybrane cytaty z transkrypcji", command=self._show_notes).pack(anchor="w", pady=(0, 7))
        ttk.Button(outer, text="Konspekt źródłowy — rozdziały i cytaty (VN-03)", command=self._show_advanced).pack(anchor="w", pady=(0, 7))
        ttk.Button(outer, text="Przewodnik do nauki — cytaty, pojęcia i pytania (VN-02/03)", command=self._show_study_guide).pack(anchor="w", pady=(0, 7))
        ttk.Button(outer, text="Nagraj mikrofon — nowa sesja WAV (Windows)", command=self._show_mic_recorder).pack(anchor="w", pady=(0, 7))
        ttk.Button(outer, text="Połącz części ukończonego nagrania WAV do transkrypcji", command=self._join_finished_recording_dialog).pack(anchor="w", pady=(0, 7))
        ttk.Button(outer, text="Sprawdź jakość nagrania WAV — cisza i przesterowanie", command=self._inspect_recording_quality).pack(anchor="w", pady=(0, 7))
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

    def _on_app_close(self) -> None:
        """Do not orphan a live FFmpeg subprocess when the GUI closes."""
        if self.active:
            if self.mic_controls and self.mic_controls["window"].winfo_exists():
                self.mic_stop.set()
                messagebox.showwarning("Video Notes",
                    "Polecono zatrzymanie mikrofonu. Zamknij program dopiero po zapisaniu nagrania.")
            else:
                self.cancel.set()
                messagebox.showwarning("Video Notes",
                    "Polecono przerwanie transkrypcji. Zaczekaj na zapis ostatniego ukończonego fragmentu.")
            return
        self.root.destroy()

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
        self._select_file(self.source, [("OBS / audio", "*.mp4 *.mkv *.webm *.mov *.wav *.mp3 *.m4a *.flac *.ogg *.opus"), ("Wszystkie", "*.*")])
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

    def _inspect_recording_quality(self) -> None:
        """Read only numerical audio quality, without showing or uploading speech."""
        if self.active:
            messagebox.showwarning("Video Notes", "Poczekaj na zakończenie innej operacji.")
            return
        selected = filedialog.askdirectory(title="Wybierz ukończoną sesję WAV do analizy jakości")
        if not selected:
            return
        folder = Path(selected)
        self.active = True
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.status.set("Lokalna analiza poziomu dźwięku i ciszy — bez wysyłki danych...")
        def work() -> None:
            try:
                result = analyze_finished_recording(folder)
                self.events.put(("mic_quality_complete", result))
            except VideoNotesError as error:
                self.events.put(("mic_quality_failure", str(error)))
            except Exception:
                self.events.put(("mic_quality_failure",
                                 "Nie udało się sprawdzić WAV; nagranie pozostawiono bez zmian."))
        threading.Thread(target=work, daemon=True, name="vn-wav-quality").start()

    def _show_recording_quality_report(self, result: dict) -> None:
        """Present private numeric findings in real Windows/Tk widgets."""
        if result.get("schema") != "videonotes-wav-diagnostics-v1":
            raise VideoNotesError("Niepoprawny raport diagnostyki WAV.")
        window = tk.Toplevel(self.root)
        window.title("Kontrola nagrania — głośność, cisza i clipping")
        window.geometry("740x530")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Analiza sygnału, nie odsłuch. Wynik nie potwierdza jakości mowy ani poprawności ASR.",
                  wraplength=700).pack(anchor="w")
        details = tk.Text(frame, wrap="word")
        details.pack(fill="both", expand=True, pady=8)
        lines = [
            "Czas nagrania: {:.1f} s".format(result["duration_ms"] / 1000),
            f"Liczba plików WAV: {result['part_count']}",
            f"Średni poziom (RMS): {result['rms_dbfs']} dBFS",
            f"Szczyt sygnału (peak): {result['peak_dbfs']} dBFS",
            f"Próbki bliskie przesterowaniu: {result['clipped_sample_ratio'] * 100:.2f}%",
            f"Cisza / bardzo niski poziom: {result['silent_ratio'] * 100:.2f}%",
            f"Najdłuższy wykryty cichy fragment: {result['longest_silence_ms']/1000:.1f} s",
            f"SHA-256 zweryfikowano: {'tak' if result['sha256_verified'] else 'nie — starsza sesja'}",
            "",
            "Ostrzeżenia:",
        ]
        lines.extend(result["warnings"] or ["Nie wykryto oczywistych problemów z poziomem; odsłuch jest nadal potrzebny."])
        lines.extend(["", "Pierwsze części nagrania:"])
        for part in result["parts"][:100]:
            lines.append(
                f"{part['name']}: RMS {part['rms_dbfs']} dBFS · peak {part['peak_dbfs']} dBFS"
                f" · cisza {part['silent_duration_ms']/1000:.1f} s"
            )
        if len(result["parts"]) > 100:
            lines.append("Pozostałe części pominięto w podglądzie; pełny raport dostępny w CLI.")
        details.insert("1.0", "\n".join(lines))
        details.configure(state="disabled")
        ttk.Button(frame, text="Zamknij", command=window.destroy).pack(anchor="e")

    def _join_finished_recording_dialog(self) -> None:
        """Opt-in lossless assembly: do not silently transcribe only first 2h."""
        if self.active:
            messagebox.showwarning("Video Notes", "Najpierw zakończ nagrywanie lub transkrypcję.")
            return
        selected = filedialog.askdirectory(title="Wybierz katalog ukończonej sesji z recording.json")
        if not selected:
            return
        folder = Path(selected)
        output = folder / "recording-full.wav"
        if output.exists() or output.is_symlink():
            messagebox.showwarning("Połącz WAV", "Plik recording-full.wav już istnieje. Nie nadpisuję go.")
            return
        if not messagebox.askyesno(
            "Połącz nagranie",
            "Złączyć wszystkie ukończone części WAV do nowego pliku recording-full.wav? "
            "Operacja działa wyłącznie lokalnie i wymaga dodatkowego miejsca na dysku. "
            "Oryginalne pliki pozostaną bez zmian."
        ):
            return
        self.active = True
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.status.set("Sprawdzanie i łączenie części WAV w tle...")
        def work() -> None:
            try:
                joined = join_finished_recording(folder, output)
                self.events.put(("mic_join_complete", str(joined)))
            except VideoNotesError as error:
                self.events.put(("mic_join_failure", str(error)))
            except Exception:
                self.events.put(("mic_join_failure", "Nie udało się połączyć WAV. Części oryginalne pozostały bez zmian."))
        threading.Thread(target=work, daemon=True, name="vn-join-mic-parts").start()

    def _show_mic_recorder(self) -> None:
        """Manual, consent-gated microphone capture in a separate dialog."""
        if self.mic_controls and self.mic_controls["window"].winfo_exists():
            self.mic_controls["window"].lift()
            return
        window = tk.Toplevel(self.root)
        window.title("Video Notes — mikrofon Windows")
        window.geometry("760x430")
        panel = ttk.Frame(window, padding=14)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Dźwięk pozostaje lokalny. Wybierz urządzenie i katalog nowych nagrań.",
                  wraplength=600).pack(anchor="w")
        device = tk.StringVar()
        system_device = tk.StringVar()
        system_agreed = tk.BooleanVar(value=False)
        parent = tk.StringVar()
        status = tk.StringVar(value="Wykryj mikrofony Windows albo wpisz dokładną nazwę DirectShow.")
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="Mikrofon", width=14).pack(side="left")
        device_box = ttk.Combobox(row, textvariable=device, width=44)
        device_box.pack(side="left", fill="x", expand=True)
        def discover() -> None:
            def work() -> None:
                try:
                    self.events.put(("mic_devices", list_microphone_devices()))
                except VideoNotesError as error:
                    self.events.put(("mic_devices_error", str(error)))
            status.set("Odczytywanie lokalnych urządzeń FFmpeg...")
            threading.Thread(target=work, daemon=True, name="vn-list-mics").start()
        ttk.Button(row, text="Wykryj", command=discover).pack(side="left", padx=5)
        second = ttk.Frame(panel)
        second.pack(fill="x", pady=4)
        ttk.Label(second, text="System audio", width=14).pack(side="left")
        system_box = ttk.Combobox(second, textvariable=system_device, width=44)
        system_box.pack(side="left", fill="x", expand=True)
        ttk.Label(second, text="Opcjonalne wejście loopback", wraplength=170).pack(side="left", padx=5)
        ttk.Checkbutton(panel, text="Wyrażam osobną zgodę na nagrywanie dźwięku komputera",
                        variable=system_agreed).pack(anchor="w")
        pathrow = ttk.Frame(panel)
        pathrow.pack(fill="x", pady=8)
        ttk.Label(pathrow, text="Katalog bazowy", width=14).pack(side="left")
        ttk.Entry(pathrow, textvariable=parent).pack(side="left", fill="x", expand=True)
        def browse_parent() -> None:
            chosen = filedialog.askdirectory()
            if chosen:
                parent.set(chosen)
        ttk.Button(pathrow, text="Wybierz", command=browse_parent).pack(side="left", padx=5)
        ttk.Label(panel, text="Nagrania dzielone są co 2 godziny. Pauza zamyka WAV; Wznów tworzy nową część. Cisza podczas pauzy nie trafia do pliku.",
                  wraplength=600).pack(anchor="w")
        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=12)
        def begin() -> None:
            if self.active:
                messagebox.showwarning("Video Notes", "Zakończ inne przetwarzanie przed nagrywaniem.")
                return
            selected = device.get().strip()
            folder = Path(parent.get().strip())
            if not selected or not parent.get().strip() or not folder.is_dir():
                messagebox.showwarning("Video Notes", "Wybierz mikrofon oraz istniejący katalog bazowy.")
                return
            if not messagebox.askyesno("Potwierdź nagrywanie",
                    "Czy chcesz rozpocząć lokalne nagrywanie wskazanego mikrofonu?"):
                return
            selected_system = system_device.get().strip()
            if selected_system and not system_agreed.get():
                messagebox.showwarning("Dźwięk systemowy", "Zaznacz osobną zgodę na nagrywanie komputera.")
                return
            if selected_system and selected_system == selected:
                messagebox.showwarning("Dźwięk systemowy", "Wybierz dwa różne urządzenia.")
                return
            system_consent = bool(selected_system and system_agreed.get())
            target = folder / ("mic-" + uuid.uuid4().hex[:12])
            self.mic_stop.clear()
            self.mic_pause.clear()
            self.mic_resume.clear()
            self.active = True
            start.configure(state="disabled")
            stop.configure(state="normal")
            pause_button.configure(state="normal")
            resume_button.configure(state="disabled")
            self.start_button.configure(state="disabled")
            self.resume_button.configure(state="disabled")
            status.set("Trwa nagrywanie. Aby zakończyć, kliknij Zatrzymaj.")
            def work() -> None:
                try:
                    result = record_microphone(selected, target, consent=True, stop=self.mic_stop,
                                               pause=self.mic_pause, resume=self.mic_resume,
                                               on_state=lambda state: self.events.put(("mic_capture_state", state)),
                                               system_device=selected_system or None,
                                               system_consent=system_consent)
                    self.events.put(("mic_complete", (target, result)))
                except VideoNotesError as error:
                    self.events.put(("mic_failure", str(error)))
                except Exception:
                    self.events.put(("mic_failure", "Nieoczekiwany błąd nagrywania. Sprawdź lokalny dziennik sesji."))
            threading.Thread(target=work, daemon=True, name="vn-mic-capture").start()
        start = ttk.Button(actions, text="Rozpocznij nagrywanie", command=begin)
        start.pack(side="left", padx=(0, 10))
        def request_stop() -> None:
            self.mic_stop.set()
            status.set("Kończenie nagrywania i zapisywanie segmentu WAV...")
        def request_pause() -> None:
            if self.active:
                self.mic_pause.set()
                pause_button.configure(state="disabled")
                status.set("Zamykanie części WAV przed pauzą...")

        def request_resume() -> None:
            if self.active and self.mic_pause.is_set():
                self.mic_resume.set()
                resume_button.configure(state="disabled")
                status.set("Wznawianie — nowa część WAV, bez nadpisania starszych...")

        pause_button = ttk.Button(actions, text="Pauza", command=request_pause, state="disabled")
        pause_button.pack(side="left", padx=5)
        resume_button = ttk.Button(actions, text="Wznów nagrywanie", command=request_resume, state="disabled")
        resume_button.pack(side="left", padx=5)
        stop = ttk.Button(actions, text="Zatrzymaj", command=request_stop, state="disabled")
        stop.pack(side="left", padx=5)
        ttk.Label(panel, textvariable=status, wraplength=600).pack(anchor="w", pady=4)
        self.mic_controls = {"window": window, "devices": device_box,
                             "system_devices": system_box,
                             "status": status, "start": start, "stop": stop,
                             "pause": pause_button, "resume": resume_button}
        def on_close() -> None:
            if self.active and str(stop["state"]) == "normal":
                messagebox.showwarning("Video Notes", "Najpierw zatrzymaj nagrywanie i poczekaj na zamknięcie pliku.")
                return
            self.mic_controls = {}
            window.destroy()
        window.protocol("WM_DELETE_WINDOW", on_close)

    def _drain(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "mic_devices":
                    if self.mic_controls and self.mic_controls["window"].winfo_exists():
                        self.mic_controls["devices"].configure(values=list(data))
                        self.mic_controls["system_devices"].configure(values=[""] + list(data))
                        self.mic_controls["status"].set(f"Wykryto {len(data)} lokalnych urządzeń audio. Wybierz właściwe.")
                elif kind == "mic_devices_error":
                    if self.mic_controls and self.mic_controls["window"].winfo_exists():
                        self.mic_controls["status"].set(str(data))
                    messagebox.showwarning("Mikrofony Windows", str(data))
                elif kind == "mic_capture_state":
                    if self.mic_controls and self.mic_controls["window"].winfo_exists() and self.active:
                        controls = self.mic_controls
                        if data == "paused":
                            controls["pause"].configure(state="disabled")
                            controls["resume"].configure(state="normal")
                            controls["status"].set("Nagrywanie wstrzymane; wszystkie poprzednie WAV są zamknięte. Wznów lub Zatrzymaj.")
                        elif data == "recording":
                            controls["pause"].configure(state="normal")
                            controls["resume"].configure(state="disabled")
                            controls["status"].set("Trwa nagrywanie lokalne. Pauza zamyka aktualny WAV.")
                elif kind in {"mic_complete", "mic_failure"}:
                    self.active = False
                    self.start_button.configure(state="normal")
                    self.resume_button.configure(state="normal")
                    if self.mic_controls and self.mic_controls["window"].winfo_exists():
                        self.mic_controls["start"].configure(state="normal")
                        self.mic_controls["stop"].configure(state="disabled")
                        self.mic_controls["pause"].configure(state="disabled")
                        self.mic_controls["resume"].configure(state="disabled")
                    if kind == "mic_complete":
                        folder, report = data
                        count = len(report["segments"])
                        message = f"Zapisano {count} części WAV w {folder}."
                        part = Path(folder) / "part-00000.wav"
                        if count == 1 and part.is_file():
                            self.source.set(str(part))
                            self.stream.set("")
                            self.streams.clear()
                            self.stream_box.configure(values=[])
                        elif count > 1:
                            message += " Aby transkrybować CAŁE nagranie, użyj przycisku 'Połącz części ukończonego nagrania WAV'."
                        self.status.set(message)
                    else:
                        message = str(data)
                        self.status.set(message)
                        messagebox.showwarning("Nagrywanie mikrofonu", message)
                    if self.mic_controls and self.mic_controls["window"].winfo_exists():
                        self.mic_controls["status"].set(message)
                elif kind in {"mic_quality_complete", "mic_quality_failure"}:
                    self.active = False
                    self.start_button.configure(state="normal")
                    self.resume_button.configure(state="normal")
                    if kind == "mic_quality_complete":
                        summary = (f"Kontrola WAV: RMS {data['rms_dbfs']} dBFS, "
                                   f"peak {data['peak_dbfs']} dBFS, "
                                   f"cisza {data['silent_ratio'] * 100:.1f}%")
                        self.status.set(summary)
                        self._show_recording_quality_report(data)
                    else:
                        self.status.set(str(data))
                        messagebox.showwarning("Kontrola nagrania WAV", str(data))
                elif kind in {"mic_join_complete", "mic_join_failure"}:
                    self.active = False
                    self.start_button.configure(state="normal")
                    self.resume_button.configure(state="normal")
                    if kind == "mic_join_complete":
                        self.source.set(str(data))
                        self.stream.set("")
                        self.streams.clear()
                        self.stream_box.configure(values=[])
                        self.status.set("Połączono całe nagranie. Wykryj ścieżki WAV i rozpocznij transkrypcję: " + str(data))
                    else:
                        self.status.set(str(data))
                        messagebox.showwarning("Połącz WAV", str(data))
                elif kind == "progress":
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


    def _show_study_guide(self) -> None:
        """Explicit local study-guide preview and optional offline exports."""
        if self.active:
            messagebox.showwarning("Video Notes", "Zakończ nagrywanie lub transkrypcję przed opracowaniem notatek.")
            return
        if not self.project.get().strip():
            messagebox.showwarning("Video Notes", "Najpierw wskaż lokalny katalog ukończonego projektu.")
            return
        folder = Path(self.project.get())
        window = tk.Toplevel(self.root)
        window.title("Przewodnik do nauki — tylko informacje z transkrypcji")
        window.geometry("940x650")
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Wyłącznie dosłowne cytaty ze źródła. Etykiety nie stanowią weryfikacji faktów ani podsumowania AI.",
                  wraplength=880).pack(anchor="w")
        tools = ttk.Frame(body)
        tools.pack(fill="x", pady=8)
        detail = tk.StringVar(value="standard")
        minutes = tk.StringVar(value="5")
        ttk.Label(tools, text="Szczegółowość").pack(side="left")
        ttk.Combobox(tools, textvariable=detail, values=["brief", "standard", "full"],
                     state="readonly", width=10).pack(side="left", padx=6)
        ttk.Label(tools, text="Minut na część").pack(side="left")
        ttk.Combobox(tools, textvariable=minutes, values=["5", "10", "15", "30"],
                     state="readonly", width=5).pack(side="left", padx=6)
        preview = tk.Text(body, wrap="word")
        preview.pack(fill="both", expand=True)
        preview.configure(state="disabled")

        def generate(*, docx: bool = False, pdf: bool = False) -> None:
            if self.active:
                messagebox.showwarning("Video Notes", "Inna operacja trwa. Zachowaj aktualny dokument.")
                return
            try:
                targets = export_study_guide(
                    folder, section_minutes=int(minutes.get()),
                    detail=detail.get(), include_docx=docx,
                    include_pdf=pdf,
                )
                content = targets[0].read_text(encoding="utf-8")
            except (ValueError, VideoNotesError, OSError) as error:
                messagebox.showerror("Przewodnik do nauki", str(error))
                return
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", content)
            preview.configure(state="disabled")
            self.status.set("Zapisano lokalny przewodnik: " + ", ".join(str(p) for p in targets))

        def check_source() -> None:
            if self.active:
                messagebox.showwarning("Video Notes", "Poczekaj na zakończenie innej operacji.")
                return
            try:
                report = verify_study_guide(folder)
            except VideoNotesError as error:
                messagebox.showerror("Weryfikacja przewodnika", str(error))
                return
            self.status.set(
                f"Potwierdzono {report['source_citations']} cytatów w "
                f"{report['sections']} częściach względem lokalnej transkrypcji."
            )
            messagebox.showinfo(
                "Weryfikacja przewodnika",
                "Cytaty, znaczniki czasu i treść JSON zgadzają się z aktualną transkrypcją. "
                "Nie jest to podpis cyfrowy ani ocena poprawności ASR."
            )
        ttk.Button(tools, text="Opracuj / odśwież", command=generate).pack(side="left", padx=4)
        ttk.Button(tools, text="Eksport DOCX", command=lambda: generate(docx=True)).pack(side="left", padx=4)
        ttk.Button(tools, text="Sprawdź źródła", command=check_source).pack(side="left", padx=4)
        ttk.Button(tools, text="Eksport PDF", command=lambda: generate(pdf=True)).pack(side="left", padx=4)
        generate()

    def _show_advanced(self) -> None:
        """Read-only local Markdown preview, without cloud processing."""
        if self.active:
            messagebox.showwarning("Video Notes", "Zakończ transkrypcję przed tworzeniem konspektu.")
            return
        if not self.project.get().strip():
            messagebox.showwarning("Video Notes", "Wskaż katalog projektu.")
            return
        try:
            markdown, structured = export_advanced_outline(Path(self.project.get()))
        except VideoNotesError as error:
            messagebox.showerror("Konspekt źródłowy", str(error))
            return
        preview = tk.Toplevel(self.root)
        preview.title("Konspekt źródłowy — wersja ekstrakcyjna")
        preview.geometry("900x620")
        body = ttk.Frame(preview, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Cytaty podzielone na rozdziały czasowe, nie streszczenie AI.",
                  wraplength=850).pack(anchor="w")
        content = tk.Text(body, wrap="word")
        content.pack(fill="both", expand=True)
        content.insert("1.0", markdown.read_text(encoding="utf-8"))
        content.configure(state="disabled")
        self.status.set(f"Zapisano lokalnie: {markdown.name} i {structured.name}.")
        def export_pdf() -> None:
            try:
                targets = export_advanced_outline(Path(self.project.get()), include_pdf=True)
                self.status.set("PDF zapisano lokalnie: " + str(targets[-1]))
            except VideoNotesError as error:
                messagebox.showerror("Konspekt PDF", str(error))
        ttk.Button(body, text="Eksportuj PDF (wymaga lokalnego LibreOffice)",
                   command=export_pdf).pack(anchor="e", pady=(6, 0))

    def _show_notes(self) -> None:
        """Display and edit source-cited, offline basic notes."""
        if self.active:
            messagebox.showwarning("Video Notes", "Poczekaj na zapis bieżącego fragmentu nagrania.")
            return
        if not self.project.get().strip():
            messagebox.showwarning("Video Notes", "Najpierw wskaż istniejący katalog projektu.")
            return
        folder = Path(self.project.get())
        try:
            if not (folder / "notes.json").exists():
                generate_basic_notes(folder)
            notes, changes = read_basic_notes(folder)
            export_basic_notes(folder)
        except VideoNotesError as error:
            if "notes-recover" in str(error):
                if messagebox.askyesno(
                    "Przerwana aktualizacja notatek",
                    "Znaleziono przerwaną aktualizację dwóch plików notatek. "
                    "Przed odzyskaniem wykonaj kopię folderu projektu i upewnij się, "
                    "że drugi program nie edytuje notatek. "
                    "Odzyskać wyłącznie wersje zgodne z zapisanym dziennikiem i historią?"
                ):
                    try:
                        recovery = recover_interrupted_note_update(folder, confirm=True)
                    except VideoNotesError as recovery_error:
                        messagebox.showerror("Odzyskiwanie notatki", str(recovery_error))
                        return
                    messagebox.showinfo(
                        "Odzyskiwanie notatki",
                        "Kontrola zakończona: " + recovery["status"] +
                        ". Zachowano dziennik wersji w historii."
                    )
                    self._show_notes()
                return
            if "Transkrypcja zmieniła się" in str(error) and messagebox.askyesno(
                "Notatka nieaktualna",
                "Transkrypcja została poprawiona. Odbudować notatkę z aktualnych wypowiedzi, zachowując ręczne zmiany i poprzednią wersję?"
            ):
                try:
                    regenerate_basic_notes(folder)
                    notes, changes = read_basic_notes(folder)
                    export_basic_notes(folder)
                except VideoNotesError as recovery_error:
                    messagebox.showerror("Odbudowa notatki", str(recovery_error))
                    return
            else:
                messagebox.showerror("Notatka podstawowa", str(error))
                return

        window = tk.Toplevel(self.root)
        window.title("Notatka podstawowa — fragmenty źródłowe")
        window.geometry("940x560")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="To wybrane wypowiedzi z transkrypcji, nie opracowanie AI.", wraplength=860).pack(anchor="w")
        ttk.Label(frame, text="Każdy punkt zawiera identyfikator wypowiedzi i czas. Zmiany zostają zapisane osobno.", wraplength=860).pack(anchor="w", pady=(0, 10))
        panes = ttk.PanedWindow(frame, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=3)
        panes.add(right, weight=2)
        view = ttk.Treeview(left, columns=("time", "quote"), show="headings", selectmode="browse")
        view.heading("time", text="Czas")
        view.heading("quote", text="Wypowiedź")
        view.column("time", width=85, stretch=False)
        view.column("quote", width=400)
        view.pack(fill="both", expand=True)
        content_by_id: dict[str, dict] = {}
        for section in notes["sections"]:
            for point in section["points"]:
                key = point["id"]
                content_by_id[key] = point
                mm, ss = divmod(point["start_ms"] // 1000, 60)
                value = changes["edits"].get(key, point["text"])
                view.insert("", "end", iid=key, values=(f"{mm:02d}:{ss:02d}", value.replace("\n", " ")))
        ttk.Label(right, text="Tekst punktu (zmieniaj tylko świadomie):").pack(anchor="w")
        editor = tk.Text(right, wrap="word", undo=True)
        editor.pack(fill="both", expand=True, pady=(4, 8))
        status = tk.StringVar(value="Wybierz punkt, aby odczytać i ewentualnie poprawić tekst.")
        ttk.Label(right, textvariable=status, wraplength=320).pack(anchor="w")
        selected_point: list[str | None] = [None]

        def has_unsaved_draft() -> bool:
            key = selected_point[0]
            if key is None:
                return False
            saved = changes["edits"].get(key, content_by_id[key]["text"])
            return editor.get("1.0", "end-1c") != saved

        def selected(_event=None) -> None:
            ids = view.selection()
            if not ids:
                return
            key = ids[0]
            if key == selected_point[0]:
                return
            if has_unsaved_draft() and not messagebox.askyesno(
                "Niezapisana poprawka",
                "Zmienić punkt i odrzucić niezapisany tekst? Wybierz Nie, by zachować szkic."
            ):
                view.selection_set(selected_point[0])
                return
            selected_point[0] = key
            value = changes["edits"].get(key, content_by_id[key]["text"])
            editor.delete("1.0", "end")
            editor.insert("1.0", value)
            status.set("Źródło: " + content_by_id[key]["segment_id"])

        view.bind("<<TreeviewSelect>>", selected)
        def close_notes() -> None:
            if has_unsaved_draft() and not messagebox.askyesno(
                "Niezapisana poprawka", "Zamknąć notatkę i odrzucić niezapisany tekst?"
            ):
                return
            window.destroy()
        window.protocol("WM_DELETE_WINDOW", close_notes)
        def save_edit() -> None:
            ids = view.selection()
            if not ids:
                messagebox.showinfo("Notatka", "Najpierw wybierz punkt.")
                return
            key = ids[0]
            value = editor.get("1.0", "end-1c")
            try:
                edit_note_point(folder, key, value)
                export_basic_notes(folder)
                changes["edits"][key] = value
                view.set(key, "quote", value.replace("\n", " "))
                status.set("Poprawka zapisana lokalnie w notes-edits.json i notes-basic.md.")
            except VideoNotesError as error:
                messagebox.showerror("Notatka", str(error))
        ttk.Button(right, text="Zapisz poprawkę i Markdown", command=save_edit).pack(anchor="e", pady=7)
        def export_docx() -> None:
            if has_unsaved_draft():
                messagebox.showwarning("Eksport DOCX", "Najpierw zapisz poprawkę w edytorze.")
                return
            try:
                path = export_basic_notes_docx(folder)
                status.set("Zapisano lokalny DOCX: " + str(path))
            except VideoNotesError as error:
                messagebox.showerror("Eksport DOCX", str(error))
        ttk.Button(right, text="Eksportuj DOCX (offline)", command=export_docx).pack(anchor="e", pady=4)
        def export_pdf() -> None:
            if has_unsaved_draft():
                messagebox.showwarning("Eksport PDF", "Najpierw zapisz poprawkę w edytorze.")
                return
            try:
                path = export_basic_notes_pdf(folder)
                status.set("Zapisano lokalny PDF: " + str(path))
            except VideoNotesError as error:
                messagebox.showerror("Eksport PDF", str(error))
        ttk.Button(right, text="Eksportuj PDF (LibreOffice)", command=export_pdf).pack(anchor="e", pady=4)
        def regenerate() -> None:
            if has_unsaved_draft():
                messagebox.showwarning("Odbudowa", "Najpierw zapisz niezapisaną poprawkę.")
                return
            if not messagebox.askyesno(
                "Odbudowa notatki",
                "Ponownie wybierać cytaty z transkrypcji? Poprzednia wersja zostanie zapisana w historii. Ręczne poprawki do istniejących segmentów pozostaną."
            ):
                return
            try:
                report = regenerate_basic_notes(folder)
                export_basic_notes(folder)
                if report["unmatched_edits"]:
                    messagebox.showwarning("Odbudowa", "Część zmian dotyczy usuniętych wypowiedzi. Została w poprzedniej wersji historii.")
                window.destroy()
                self._show_notes()
            except VideoNotesError as error:
                messagebox.showerror("Odbudowa", str(error))
        ttk.Button(right, text="Odbuduj notatkę z historią", command=regenerate).pack(anchor="e")

        def show_history() -> None:
            if has_unsaved_draft():
                messagebox.showwarning("Historia", "Najpierw zapisz niezapisaną poprawkę.")
                return
            try:
                versions = list_note_versions(folder)
            except VideoNotesError as error:
                messagebox.showerror("Historia notatek", str(error))
                return
            if not versions:
                messagebox.showinfo("Historia notatek", "Nie zapisano jeszcze wcześniejszych wersji.")
                return
            history = tk.Toplevel(window)
            history.title("Historia notatek — wybierz wersję do przywrócenia")
            history.geometry("880x380")
            history.transient(window)
            panel = ttk.Frame(history, padding=12)
            panel.pack(fill="both", expand=True)
            ttk.Label(
                panel, text="Najpierw wybierz wersję. Przywracanie działa tylko wtedy, gdy cytaty odpowiadają aktualnej transkrypcji.",
                wraplength=830
            ).pack(anchor="w", pady=(0, 8))
            table = ttk.Treeview(panel, columns=("date", "edits", "revision"),
                                 show="headings", selectmode="browse")
            for col, label, width in (("date", "Data UTC", 200),
                                      ("edits", "Ręczne poprawki", 130),
                                      ("revision", "Identyfikator wersji", 440)):
                table.heading(col, text=label)
                table.column(col, width=width, stretch=col == "revision")
            table.pack(fill="both", expand=True)
            for version in versions:
                table.insert("", "end", iid=version["revision"],
                             values=(version["created_at"], version["manual_edits"], version["revision"]))
            def restore_selected() -> None:
                selected_versions = table.selection()
                if not selected_versions:
                    messagebox.showinfo("Historia notatek", "Wybierz wersję do przywrócenia.")
                    return
                if has_unsaved_draft():
                    messagebox.showwarning("Historia notatek", "Najpierw zapisz niezapisaną poprawkę.")
                    return
                revision = selected_versions[0]
                if not messagebox.askyesno(
                    "Przywróć notatkę",
                    "Przywrócić wybraną wersję? Aktualna notatka i jej ręczne poprawki zostaną wcześniej zapisane w historii."
                ):
                    return
                try:
                    restore_note_version(folder, revision)
                    export_basic_notes(folder)
                except VideoNotesError as error:
                    messagebox.showerror("Przywracanie notatki", str(error))
                    return
                history.destroy()
                window.destroy()
                self._show_notes()
            ttk.Button(panel, text="Przywróć wybraną wersję", command=restore_selected).pack(anchor="e", pady=(8, 0))
        ttk.Button(right, text="Historia i przywracanie wersji", command=show_history).pack(anchor="e", pady=4)
        try:
            number_of_versions = len(list_note_versions(folder))
        except VideoNotesError:
            number_of_versions = "do sprawdzenia"
        ttk.Label(right, text=f"Wcześniejsze wersje: {number_of_versions}", wraplength=290).pack(anchor="w", pady=4)
        if content_by_id:
            first = next(iter(content_by_id))
            view.selection_set(first)
            selected()


def launch() -> None:
    root = tk.Tk()
    VideoNotesWindow(root)
    root.mainloop()
