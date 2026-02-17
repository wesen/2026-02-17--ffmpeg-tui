"""Main Textual application."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListView,
    ListItem,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.worker import get_current_worker

from ffmpeg_tui.models.codecs import (
    AUDIO_BY_ID,
    AUDIO_CODECS,
    CODEC_BY_ID,
    CONTAINER_BY_ID,
    CONTAINERS,
    DEFAULT_CONTAINER,
    PRESETS,
    VIDEO_CODECS,
)
from ffmpeg_tui.models.job import (
    RESOLUTIONS,
    EncodingJob,
    JobStatus,
    create_job_from_template,
)
from ffmpeg_tui.models.probe import ProbeResult, probe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
    ".wmv", ".m4v", ".ts", ".mts",
}


def _format_time(seconds: float) -> str:
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h:{m:02d}m:{s:02d}s"
    return f"{m}m:{s:02d}s"


def _format_size(size: int) -> str:
    if size >= 1_073_741_824:
        return f"{size / 1_073_741_824:.1f} GB"
    if size >= 1_048_576:
        return f"{size / 1_048_576:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


class VideoDirectoryTree(DirectoryTree):
    """A DirectoryTree that only shows video files and directories."""

    def filter_paths(self, paths):
        return [
            p for p in paths
            if p.is_dir() or p.suffix.lower() in VIDEO_EXTENSIONS
        ]


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class FFmpegTUI(App):
    """A TUI for cross-encoding videos with ffmpeg."""

    TITLE = "FFmpeg TUI"

    CSS = """
    Screen { layout: vertical; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 1 2; overflow-y: auto; }
    .pane-title { text-style: bold; margin-bottom: 1; }
    .section-label { text-style: bold; margin-bottom: 1; }

    /* --- File Selection --- */
    #file-input { width: 1fr; }
    #btn-add-file { width: auto; min-width: 10; }
    #btn-toggle-browser { width: auto; min-width: 12; }
    #file-browser { height: 12; border: solid $accent; margin-top: 1; }
    #file-list-box { margin-top: 1; border: solid $success; padding: 1; height: auto; max-height: 14; }
    .file-list-header { text-style: bold; margin-bottom: 1; }
    #btn-remove-file { margin-top: 1; }

    /* --- Codec Selection --- */
    #tab-codec Horizontal { height: auto; }
    #tab-codec Horizontal > Vertical { width: 1fr; margin: 0 1; }
    RadioSet { height: auto; border: solid $accent; padding: 1; }

    /* --- Settings --- */
    #tab-settings Horizontal { height: auto; }
    #tab-settings Horizontal > Vertical { width: 1fr; margin: 0 1; }
    #crf-input { width: 12; }
    #output-dir-input { width: 1fr; margin-top: 1; }
    #command-preview {
        padding: 1 2; border: solid $warning;
        background: $surface; margin-top: 1; height: auto;
    }

    /* --- Encode --- */
    #queue-table { height: auto; max-height: 10; margin-bottom: 1; }
    .progress-stats { padding: 1 2; border: solid $accent; margin-top: 1; }
    #encode-progress { margin: 1 0; }
    #ffmpeg-log { height: 6; border: solid $accent; margin-top: 1; }

    /* --- Done --- */
    #results-table { height: auto; max-height: 16; }
    #results-summary { padding: 1 2; border: solid $success; margin-top: 1; }

    /* --- Shared --- */
    .button-row { margin-top: 1; height: 3; }
    .button-row Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "switch_tab('tab-files')", "Files", show=True),
        Binding("f2", "switch_tab('tab-codec')", "Codec", show=True),
        Binding("f3", "switch_tab('tab-settings')", "Settings", show=True),
        Binding("f4", "switch_tab('tab-encode')", "Encode", show=True),
        Binding("f5", "switch_tab('tab-done')", "Done", show=True),
    ]

    def __init__(self):
        super().__init__()
        # Selected files (path → probe result)
        self._selected_files: dict[str, ProbeResult] = {}
        # Encoding queue
        self._queue: list[EncodingJob] = []
        self._current_job_idx: int = -1
        self._encoding = False
        self._paused = False
        self._ffmpeg_proc: asyncio.subprocess.Process | None = None
        self._encode_start_time: float = 0.0

    # =====================================================================
    # Compose
    # =====================================================================

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            # --- TAB 1: Files ---
            with TabPane("Files", id="tab-files"):
                yield Label("📁 File Selection", classes="pane-title")
                with Horizontal():
                    yield Input(
                        placeholder="Enter video file path...",
                        id="file-input",
                    )
                    yield Button("+ Add", id="btn-add-file", variant="success")
                    yield Button("Browse ↕", id="btn-toggle-browser", variant="default")
                yield VideoDirectoryTree(Path.home(), id="file-browser")
                yield Static("", id="file-list-box")
                with Horizontal(classes="button-row"):
                    yield Button("Remove Selected", id="btn-remove-file", variant="error")
                    yield Button("Clear All", id="btn-clear-files", variant="warning")

            # --- TAB 2: Codec ---
            with TabPane("Codec", id="tab-codec"):
                yield Label("🎬 Codec & Container", classes="pane-title")
                with Horizontal():
                    with Vertical():
                        yield Label("Video Codec", classes="section-label")
                        with RadioSet(id="video-codec-set"):
                            for i, vc in enumerate(VIDEO_CODECS):
                                label = f"{vc.label} — {vc.description}"
                                yield RadioButton(label, value=(i == 0), id=f"vc-{vc.id}")
                    with Vertical():
                        yield Label("Container", classes="section-label")
                        with RadioSet(id="container-set"):
                            for i, ct in enumerate(CONTAINERS):
                                label = f"{ct.label} ({ct.extension}) — {ct.description}"
                                yield RadioButton(label, value=(i == 0), id=f"ct-{ct.id}")

                yield Label("Audio Codec", classes="section-label")
                with RadioSet(id="audio-codec-set"):
                    for i, ac in enumerate(AUDIO_CODECS):
                        yield RadioButton(ac.label, value=(i == 0), id=f"ac-{ac.id}")

            # --- TAB 3: Settings ---
            with TabPane("Settings", id="tab-settings"):
                yield Label("⚙ Encoding Settings", classes="pane-title")
                with Horizontal():
                    with Vertical():
                        yield Label("CRF (Quality)", classes="section-label")
                        yield Input("23", type="integer", id="crf-input")
                        yield Static(
                            "Lower = better quality, larger file.\n"
                            "18=near-lossless  23=default  28=good  35=low",
                            id="crf-hint",
                        )
                    with Vertical():
                        yield Label("Preset (Speed)", classes="section-label")
                        yield Select(
                            [(p, p) for p in (
                                "ultrafast", "superfast", "veryfast", "faster", "fast",
                                "medium", "slow", "slower", "veryslow",
                            )],
                            value="medium",
                            id="preset-select",
                        )
                        yield Static("Slower = better compression", id="preset-hint")

                with Horizontal():
                    with Vertical():
                        yield Label("Audio Bitrate", classes="section-label")
                        yield Select(
                            [("64k", "64k"), ("96k", "96k"), ("128k", "128k"),
                             ("192k", "192k"), ("256k", "256k"), ("320k", "320k")],
                            value="128k",
                            id="audio-bitrate-select",
                        )
                    with Vertical():
                        yield Label("Resolution", classes="section-label")
                        yield Select(
                            [(label, height) for label, height in RESOLUTIONS],
                            value=None,
                            id="resolution-select",
                        )

                yield Label("Output Directory", classes="section-label")
                yield Input(
                    placeholder="Leave empty = same directory as input",
                    id="output-dir-input",
                )

                yield Label("Quick Presets", classes="section-label")
                yield Select(
                    [(p.name, i) for i, p in enumerate(PRESETS)],
                    prompt="Load a preset...",
                    id="preset-load",
                )

                yield Static("", id="command-preview")

            # --- TAB 4: Encode ---
            with TabPane("Encode", id="tab-encode"):
                yield Label("📋 Encode", classes="pane-title")
                yield DataTable(id="queue-table")
                yield Static("Ready to encode.", id="encode-status")
                yield ProgressBar(total=100, show_eta=False, id="encode-progress")
                yield Static("", id="encode-stats", classes="progress-stats")
                with Horizontal(classes="button-row"):
                    yield Button("▶ Start Encode", id="btn-start", variant="success")
                    yield Button("⏸ Pause", id="btn-pause", variant="warning")
                    yield Button("✕ Cancel", id="btn-cancel", variant="error")
                yield RichLog(id="ffmpeg-log", wrap=True, markup=True)

            # --- TAB 5: Done ---
            with TabPane("Done", id="tab-done"):
                yield Label("✅ Done", classes="pane-title")
                yield DataTable(id="results-table")
                yield Static("No results yet.", id="results-summary")
                with Horizontal(classes="button-row"):
                    yield Button("New Encode", id="btn-new", variant="primary")

        yield Footer()

    # =====================================================================
    # Actions
    # =====================================================================

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    # =====================================================================
    # Event handlers
    # =====================================================================

    def on_mount(self) -> None:
        self._update_command_preview()
        self._update_file_list_display()
        # Setup queue table columns
        qt = self.query_one("#queue-table", DataTable)
        qt.add_columns("#", "File", "Status", "Progress")
        # Setup results table columns
        rt = self.query_one("#results-table", DataTable)
        rt.add_columns("#", "File", "Input", "Output", "Saved", "Time")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = str(event.path)
        self.query_one("#file-input", Input).value = path
        self._add_file(path)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "file-input":
            self._add_file(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("crf-input", "output-dir-input"):
            self._update_command_preview()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        set_id = event.radio_set.id
        btn_id = event.pressed.id or ""

        if set_id == "video-codec-set" and btn_id.startswith("vc-"):
            codec_id = btn_id[3:]
            if codec_id in DEFAULT_CONTAINER:
                self._select_container(DEFAULT_CONTAINER[codec_id])
            vc = CODEC_BY_ID[codec_id]
            self.query_one("#crf-input", Input).value = str(vc.crf_default)
            self._update_preset_select(vc)

        self._update_command_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        sel_id = event.select.id
        if sel_id == "preset-load":
            if event.value is not None and event.value != Select.BLANK:
                self._apply_preset(int(event.value))
        else:
            self._update_command_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-add-file":
            val = self.query_one("#file-input", Input).value
            if val:
                self._add_file(val)
        elif bid == "btn-remove-file":
            self._remove_last_file()
        elif bid == "btn-clear-files":
            self._selected_files.clear()
            self._update_file_list_display()
            self.notify("Cleared all files.")
        elif bid == "btn-toggle-browser":
            tree = self.query_one("#file-browser", VideoDirectoryTree)
            tree.display = not tree.display
        elif bid == "btn-start":
            self._start_batch_encode()
        elif bid == "btn-pause":
            self._toggle_pause()
        elif bid == "btn-cancel":
            self._cancel_encode()
        elif bid == "btn-new":
            self.query_one(TabbedContent).active = "tab-files"

    # =====================================================================
    # File management
    # =====================================================================

    def _add_file(self, path: str) -> None:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            self.notify(f"Not a file: {path}", severity="warning")
            return
        key = str(p)
        if key in self._selected_files:
            self.notify(f"Already added: {p.name}", severity="warning")
            return
        result = probe(p)
        if result.error:
            self.notify(f"Probe error: {result.error}", severity="error")
            return
        self._selected_files[key] = result
        self._update_file_list_display()
        self._update_command_preview()
        self.notify(f"Added: {p.name}")
        self.query_one("#file-input", Input).value = ""

    def _remove_last_file(self) -> None:
        if self._selected_files:
            key = list(self._selected_files.keys())[-1]
            name = Path(key).name
            del self._selected_files[key]
            self._update_file_list_display()
            self._update_command_preview()
            self.notify(f"Removed: {name}")

    def _update_file_list_display(self) -> None:
        box = self.query_one("#file-list-box", Static)
        if not self._selected_files:
            box.update("[dim]No files selected. Add files above.[/dim]")
            return
        lines = [f"[bold]{len(self._selected_files)} file(s) selected:[/bold]"]
        for i, (path, pr) in enumerate(self._selected_files.items(), 1):
            name = Path(path).name
            info = pr.summary if pr else "?"
            lines.append(f"  {i}. {name}")
            lines.append(f"     {info}")
        box.update("\n".join(lines))

    # =====================================================================
    # Settings helpers
    # =====================================================================

    def _get_current_settings(self) -> dict:
        """Read current UI settings into a dict."""
        # Video codec
        vc_id = "libx264"
        for child in self.query_one("#video-codec-set", RadioSet).children:
            if isinstance(child, RadioButton) and child.value:
                vc_id = child.id[3:] if child.id else "libx264"
                break
        # Container
        ct_id = "mp4"
        for child in self.query_one("#container-set", RadioSet).children:
            if isinstance(child, RadioButton) and child.value:
                ct_id = child.id[3:] if child.id else "mp4"
                break
        # Audio codec
        ac_id = "aac"
        for child in self.query_one("#audio-codec-set", RadioSet).children:
            if isinstance(child, RadioButton) and child.value:
                ac_id = child.id[3:] if child.id else "aac"
                break
        # CRF
        try:
            crf = int(self.query_one("#crf-input", Input).value or "23")
        except ValueError:
            crf = 23
        # Preset
        preset_sel = self.query_one("#preset-select", Select)
        preset = str(preset_sel.value) if preset_sel.value not in (None, Select.BLANK) else "medium"
        # Audio bitrate
        ab_sel = self.query_one("#audio-bitrate-select", Select)
        audio_bitrate = str(ab_sel.value) if ab_sel.value not in (None, Select.BLANK) else "128k"
        # Resolution
        res_sel = self.query_one("#resolution-select", Select)
        scale_height = res_sel.value if res_sel.value not in (None, Select.BLANK) else None
        # Output dir
        out_dir_str = self.query_one("#output-dir-input", Input).value.strip()
        output_dir = Path(out_dir_str).expanduser() if out_dir_str else None

        return dict(
            video_codec_id=vc_id,
            container_id=ct_id,
            audio_codec_id=ac_id,
            crf=crf,
            preset=preset,
            audio_bitrate=audio_bitrate,
            scale_height=scale_height,
            output_dir=output_dir,
        )

    def _select_container(self, container_id: str) -> None:
        for child in self.query_one("#container-set", RadioSet).children:
            if isinstance(child, RadioButton) and child.id == f"ct-{container_id}":
                child.value = True
                break

    def _update_preset_select(self, vc) -> None:
        sel = self.query_one("#preset-select", Select)
        if vc.presets:
            sel.set_options([(p, p) for p in vc.presets])
            sel.value = vc.preset_default
        else:
            sel.set_options([("(not applicable)", "")])
            sel.value = ""

    def _update_command_preview(self) -> None:
        try:
            settings = self._get_current_settings()
            # Use first selected file, or a placeholder
            if self._selected_files:
                first_path = Path(next(iter(self._selected_files)))
                first_probe = next(iter(self._selected_files.values()))
            else:
                first_path = Path("input.mp4")
                first_probe = None

            job = create_job_from_template(first_path, first_probe, **settings)
            cmd = job.command_str()
            count = len(self._selected_files)
            prefix = f"[bold]Command ({count} file{'s' if count != 1 else ''}):[/bold]\n" if count else "[bold]Command:[/bold]\n"
            self.query_one("#command-preview", Static).update(prefix + cmd)
        except Exception:
            pass

    def _apply_preset(self, idx: int) -> None:
        p = PRESETS[idx]
        self.query_one("#crf-input", Input).value = str(p.crf)

        for child in self.query_one("#video-codec-set", RadioSet).children:
            if isinstance(child, RadioButton) and child.id == f"vc-{p.video_codec_id}":
                child.value = True
                break
        self._select_container(p.container_id)
        for child in self.query_one("#audio-codec-set", RadioSet).children:
            if isinstance(child, RadioButton) and child.id == f"ac-{p.audio_codec_id}":
                child.value = True
                break

        vc = CODEC_BY_ID[p.video_codec_id]
        self._update_preset_select(vc)
        if vc.presets:
            self.query_one("#preset-select", Select).value = p.preset

        ab_sel = self.query_one("#audio-bitrate-select", Select)
        if p.audio_bitrate:
            ab_sel.value = p.audio_bitrate

        self._update_command_preview()
        self.notify(f"Loaded preset: {p.name}")

    # =====================================================================
    # Batch encoding
    # =====================================================================

    def _build_queue(self) -> list[EncodingJob]:
        """Build encoding jobs for all selected files with current settings."""
        settings = self._get_current_settings()
        output_dir = settings.pop("output_dir")
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

        jobs = []
        for path_str, probe_result in self._selected_files.items():
            job = create_job_from_template(
                Path(path_str), probe_result, output_dir=output_dir, **settings,
            )
            job.resolve_output_path()
            jobs.append(job)
        return jobs

    def _update_queue_table(self) -> None:
        qt = self.query_one("#queue-table", DataTable)
        qt.clear()
        for i, job in enumerate(self._queue, 1):
            pct = f"{job.progress:.0f}%" if job.progress > 0 else "—"
            qt.add_row(str(i), job.input_path.name, job.status.value, pct)

    def _start_batch_encode(self) -> None:
        if self._encoding:
            self.notify("Already encoding!", severity="warning")
            return
        if not self._selected_files:
            self.notify("No files selected!", severity="error")
            return

        self._queue = self._build_queue()
        self._current_job_idx = -1
        self._encoding = True
        self._paused = False
        self._update_queue_table()

        self.query_one("#encode-status", Static).update(
            f"Starting batch: {len(self._queue)} file(s)"
        )
        self.query_one("#encode-progress", ProgressBar).update(total=100, progress=0)
        self.query_one("#encode-stats", Static).update("")
        self.query_one("#ffmpeg-log", RichLog).clear()
        self.query_one(TabbedContent).active = "tab-encode"

        self.run_worker(self._run_batch, exclusive=True)

    async def _run_batch(self) -> None:
        """Encode all jobs in the queue sequentially."""
        worker = get_current_worker()

        for idx, job in enumerate(self._queue):
            if worker.is_cancelled:
                break

            self._current_job_idx = idx
            job.status = JobStatus.ENCODING
            self._update_queue_table()

            self.query_one("#encode-status", Static).update(
                f"({idx + 1}/{len(self._queue)}) Encoding: {job.input_path.name}"
            )
            self.query_one("#encode-progress", ProgressBar).update(total=100, progress=0)
            self.query_one("#encode-stats", Static).update("")

            self._encode_start_time = time.time()
            success = await self._run_single_ffmpeg(job, worker)

            job.elapsed = time.time() - self._encode_start_time
            if success:
                job.status = JobStatus.DONE
                job.progress = 100.0
                if job.output_path.exists():
                    job.output_size = job.output_path.stat().st_size
            elif worker.is_cancelled:
                job.status = JobStatus.CANCELLED
            else:
                job.status = JobStatus.FAILED

            self._update_queue_table()

        self._encoding = False
        self._ffmpeg_proc = None
        self._show_batch_results()

    async def _run_single_ffmpeg(self, job: EncodingJob, worker) -> bool:
        """Run ffmpeg for a single job. Returns True on success."""
        cmd = job.build_command()
        y_idx = cmd.index("-y")
        cmd_with_progress = (
            cmd[:y_idx]
            + ["-progress", "pipe:1", "-stats_period", "0.5"]
            + cmd[y_idx:]
        )

        duration = job.probe.duration if job.probe else 0
        log = self.query_one("#ffmpeg-log", RichLog)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_with_progress,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._ffmpeg_proc = proc

            async def read_stderr():
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    if worker.is_cancelled:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        log.write(text)

            stderr_task = asyncio.create_task(read_stderr())

            progress_data: dict[str, str] = {}
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                if worker.is_cancelled:
                    proc.terminate()
                    break

                text = line.decode("utf-8", errors="replace").strip()
                if "=" in text:
                    key, _, val = text.partition("=")
                    progress_data[key.strip()] = val.strip()

                if text in ("progress=continue", "progress=end"):
                    pct = self._update_progress(progress_data, duration)
                    job.progress = pct
                    self._update_queue_table()
                    progress_data = {}

            await stderr_task
            await proc.wait()
            self._ffmpeg_proc = None
            return proc.returncode == 0

        except Exception as e:
            self._ffmpeg_proc = None
            log.write(f"[red]Error: {e}[/red]")
            return False

    def _update_progress(self, data: dict[str, str], duration: float) -> float:
        """Update UI and return percentage."""
        out_time = data.get("out_time_ms", data.get("out_time_us", "0"))
        try:
            out_seconds = int(out_time) / 1_000_000
        except ValueError:
            out_seconds = 0

        pct = min(100.0, (out_seconds / duration) * 100) if duration > 0 else 0.0

        speed = data.get("speed", "N/A")
        fps = data.get("fps", "N/A")
        total_size = data.get("total_size", "N/A")
        bitrate = data.get("bitrate", "N/A")
        frame = data.get("frame", "N/A")

        elapsed = time.time() - self._encode_start_time
        eta_str = _format_time((elapsed / (pct / 100)) - elapsed) if pct > 0 else "N/A"

        size_str = total_size
        try:
            sb = int(total_size)
            size_str = _format_size(sb)
        except (ValueError, TypeError):
            pass

        pause_indicator = "  ⏸ PAUSED" if self._paused else ""
        job_num = f"({self._current_job_idx + 1}/{len(self._queue)}) " if len(self._queue) > 1 else ""
        stats = (
            f"Frame: {frame}  FPS: {fps}  Speed: {speed}{pause_indicator}\n"
            f"Size: {size_str}  Bitrate: {bitrate}\n"
            f"Elapsed: {_format_time(elapsed)}  ETA: {eta_str}  Progress: {pct:.1f}%"
        )

        try:
            self.query_one("#encode-progress", ProgressBar).update(progress=pct)
            self.query_one("#encode-stats", Static).update(stats)
            cur_job = self._queue[self._current_job_idx] if self._current_job_idx >= 0 else None
            name = cur_job.input_path.name if cur_job else "?"
            self.query_one("#encode-status", Static).update(
                f"{job_num}Encoding: {name} — {pct:.1f}%{pause_indicator}"
            )
        except Exception:
            pass

        return pct

    # =====================================================================
    # Pause / Cancel
    # =====================================================================

    def _toggle_pause(self) -> None:
        if not self._ffmpeg_proc or not self._encoding:
            return
        if self._paused:
            # Resume
            try:
                os.kill(self._ffmpeg_proc.pid, signal.SIGCONT)
            except OSError:
                pass
            self._paused = False
            self.query_one("#btn-pause", Button).label = "⏸ Pause"
            self.notify("Resumed encoding.")
        else:
            # Pause
            try:
                os.kill(self._ffmpeg_proc.pid, signal.SIGSTOP)
            except OSError:
                pass
            self._paused = True
            self.query_one("#btn-pause", Button).label = "▶ Resume"
            self.notify("Encoding paused.")

    def _cancel_encode(self) -> None:
        if self._ffmpeg_proc:
            # Resume first if paused, then terminate
            if self._paused:
                try:
                    os.kill(self._ffmpeg_proc.pid, signal.SIGCONT)
                except OSError:
                    pass
                self._paused = False
            self._ffmpeg_proc.terminate()
            self.notify("Encoding cancelled.")
        self._encoding = False
        self.query_one("#encode-status", Static).update("Cancelled.")
        self.query_one("#btn-pause", Button).label = "⏸ Pause"

    # =====================================================================
    # Results
    # =====================================================================

    def _show_batch_results(self) -> None:
        rt = self.query_one("#results-table", DataTable)
        rt.clear()

        total_in = 0
        total_out = 0
        total_time = 0.0
        done_count = 0
        fail_count = 0

        for i, job in enumerate(self._queue, 1):
            in_size = job.probe.size if job.probe else 0
            out_size = job.output_size
            saved = f"{((1 - out_size / in_size) * 100):.1f}%" if in_size > 0 and out_size > 0 else "—"
            status_icon = "✅" if job.status == JobStatus.DONE else "❌" if job.status == JobStatus.FAILED else "⊘"

            rt.add_row(
                f"{status_icon} {i}",
                job.input_path.name,
                _format_size(in_size),
                _format_size(out_size) if out_size else "—",
                saved,
                _format_time(job.elapsed),
            )

            total_in += in_size
            total_out += out_size
            total_time += job.elapsed
            if job.status == JobStatus.DONE:
                done_count += 1
            elif job.status == JobStatus.FAILED:
                fail_count += 1

        # Totals row
        total_saved = f"{((1 - total_out / total_in) * 100):.1f}%" if total_in > 0 and total_out > 0 else "—"
        rt.add_row("", "TOTAL", _format_size(total_in), _format_size(total_out), total_saved, _format_time(total_time))

        # Summary
        summary_parts = [f"✅ {done_count} encoded"]
        if fail_count:
            summary_parts.append(f"❌ {fail_count} failed")
        summary_parts.append(f"Total saved: {total_saved}")
        summary_parts.append(f"Total time: {_format_time(total_time)}")

        self.query_one("#results-summary", Static).update("  ".join(summary_parts))
        self.query_one("#encode-status", Static).update("✅ Batch complete!")
        self.query_one("#encode-progress", ProgressBar).update(progress=100)
        self.query_one(TabbedContent).active = "tab-done"
