"""Main Textual application."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.worker import Worker, get_current_worker

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
from ffmpeg_tui.models.job import EncodingJob
from ffmpeg_tui.models.probe import ProbeResult, probe


# ---------------------------------------------------------------------------
# Custom filtered directory tree
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mts"}


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
    Screen {
        layout: vertical;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 1 2;
    }
    .pane-title {
        text-style: bold;
        margin-bottom: 1;
    }
    .section-box {
        border: solid $accent;
        padding: 1 2;
        margin-bottom: 1;
    }
    .section-label {
        text-style: bold;
        margin-bottom: 1;
    }
    #file-browser {
        height: 14;
        border: solid $accent;
    }
    #probe-info {
        margin-top: 1;
        padding: 1 2;
        border: solid $success;
        height: auto;
        max-height: 10;
    }
    #command-preview {
        padding: 1 2;
        border: solid $warning;
        background: $surface;
        margin-top: 1;
        height: auto;
    }
    #command-preview-text {
        color: $text;
    }
    .codec-row {
        height: auto;
        margin-bottom: 0;
    }
    RadioSet {
        height: auto;
        border: solid $accent;
        padding: 1;
    }
    .progress-stats {
        padding: 1 2;
        border: solid $accent;
        margin-top: 1;
    }
    #encode-progress {
        margin: 1 0;
    }
    #ffmpeg-log {
        height: 8;
        border: solid $accent;
        margin-top: 1;
    }
    #results-box {
        padding: 1 2;
        border: solid $success;
    }
    .button-row {
        margin-top: 1;
        height: 3;
    }
    .button-row Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    # Reactive state
    selected_file: reactive[str] = reactive("")
    probe_result: reactive[ProbeResult | None] = reactive(None)

    def __init__(self):
        super().__init__()
        self._job = EncodingJob()
        self._encoding = False
        self._ffmpeg_proc: asyncio.subprocess.Process | None = None
        self._encode_start_time: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            # --- TAB 1: Files ---
            with TabPane("Files", id="tab-files"):
                yield Label("📁 File Selection", classes="pane-title")
                with Horizontal():
                    yield Input(
                        placeholder="Enter video file path or browse below...",
                        id="file-input",
                    )
                    yield Button("Browse ↕", id="btn-toggle-browser", variant="default")
                yield VideoDirectoryTree(Path.home(), id="file-browser")
                yield Static("No file selected.", id="probe-info")

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
                            "Lower = better quality, larger file. "
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

                yield Label("Audio Bitrate", classes="section-label")
                yield Select(
                    [("64k", "64k"), ("96k", "96k"), ("128k", "128k"),
                     ("192k", "192k"), ("256k", "256k"), ("320k", "320k")],
                    value="128k",
                    id="audio-bitrate-select",
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
                yield Static("Ready to encode.", id="encode-status")
                yield ProgressBar(total=100, show_eta=False, id="encode-progress")
                yield Static("", id="encode-stats", classes="progress-stats")
                with Horizontal(classes="button-row"):
                    yield Button("▶ Start Encode", id="btn-start", variant="success")
                    yield Button("✕ Cancel", id="btn-cancel", variant="error")
                yield RichLog(id="ffmpeg-log", wrap=True, markup=True)

            # --- TAB 5: Done ---
            with TabPane("Done", id="tab-done"):
                yield Label("✅ Done", classes="pane-title")
                yield Static("No results yet.", id="results-box")
                with Horizontal(classes="button-row"):
                    yield Button("New Encode", id="btn-new", variant="primary")

        yield Footer()

    # ----- Event handlers -----

    def on_mount(self) -> None:
        self._update_command_preview()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """User selected a file in the tree."""
        path = str(event.path)
        self.query_one("#file-input", Input).value = path
        self._probe_file(path)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "file-input":
            self._probe_file(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "crf-input":
            try:
                self._job.crf = int(event.value) if event.value else 23
            except ValueError:
                pass
            self._update_command_preview()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle codec/container/audio radio changes."""
        set_id = event.radio_set.id
        btn_id = event.pressed.id or ""

        if set_id == "video-codec-set" and btn_id.startswith("vc-"):
            codec_id = btn_id[3:]
            self._job.video_codec_id = codec_id
            # Auto-suggest container
            if codec_id in DEFAULT_CONTAINER:
                suggested = DEFAULT_CONTAINER[codec_id]
                self._select_container(suggested)
            # Update CRF default and presets
            vc = CODEC_BY_ID[codec_id]
            self.query_one("#crf-input", Input).value = str(vc.crf_default)
            self._job.crf = vc.crf_default
            self._job.preset = vc.preset_default
            self._update_preset_select(vc)

        elif set_id == "container-set" and btn_id.startswith("ct-"):
            self._job.container_id = btn_id[3:]

        elif set_id == "audio-codec-set" and btn_id.startswith("ac-"):
            self._job.audio_codec_id = btn_id[3:]

        self._update_command_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "preset-select":
            if event.value is not None and event.value != Select.BLANK:
                self._job.preset = str(event.value)
                self._update_command_preview()
        elif event.select.id == "audio-bitrate-select":
            if event.value is not None and event.value != Select.BLANK:
                self._job.audio_bitrate = str(event.value)
                self._update_command_preview()
        elif event.select.id == "preset-load":
            if event.value is not None and event.value != Select.BLANK:
                self._apply_preset(int(event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._start_encode()
        elif event.button.id == "btn-cancel":
            self._cancel_encode()
        elif event.button.id == "btn-new":
            self.query_one(TabbedContent).active = "tab-files"
        elif event.button.id == "btn-toggle-browser":
            tree = self.query_one("#file-browser", VideoDirectoryTree)
            tree.display = not tree.display

    # ----- Internal helpers -----

    def _probe_file(self, path: str) -> None:
        """Probe a file and update the info panel."""
        p = Path(path).expanduser()
        if not p.is_file():
            self.query_one("#probe-info", Static).update(f"⚠ Not a file: {path}")
            return
        result = probe(p)
        self.probe_result = result
        self._job.input_path = p
        self._job.probe = result
        if result.error:
            self.query_one("#probe-info", Static).update(f"⚠ {result.error}")
        else:
            lines = [f"✅ {p.name}"]
            if result.video:
                v = result.video
                lines.append(f"   Video: {v.codec} {v.resolution} {v.fps}fps pix={v.pixel_format}")
            if result.audio:
                a = result.audio
                lines.append(f"   Audio: {a.codec} {a.sample_rate}Hz {a.channels}ch {a.bitrate_kbps}")
            lines.append(f"   Duration: {result.duration_str}  Size: {result.size_str}  Format: {result.format_name}")
            self.query_one("#probe-info", Static).update("\n".join(lines))
        self._update_command_preview()

    def _select_container(self, container_id: str) -> None:
        """Programmatically select a container radio button."""
        radio_set = self.query_one("#container-set", RadioSet)
        for child in radio_set.children:
            if isinstance(child, RadioButton) and child.id == f"ct-{container_id}":
                child.value = True
                break

    def _update_preset_select(self, vc) -> None:
        """Update the preset Select widget for the current video codec."""
        sel = self.query_one("#preset-select", Select)
        if vc.presets:
            sel.set_options([(p, p) for p in vc.presets])
            sel.value = vc.preset_default
        else:
            sel.set_options([("(not applicable)", "")])
            sel.value = ""

    def _update_command_preview(self) -> None:
        """Refresh the command preview text."""
        try:
            cmd = self._job.command_str()
            self.query_one("#command-preview", Static).update(
                f"[bold]Command:[/bold]\n{cmd}"
            )
        except Exception:
            pass

    def _apply_preset(self, idx: int) -> None:
        """Apply a built-in encoding preset."""
        p = PRESETS[idx]
        self._job.video_codec_id = p.video_codec_id
        self._job.audio_codec_id = p.audio_codec_id
        self._job.container_id = p.container_id
        self._job.crf = p.crf
        self._job.preset = p.preset
        self._job.audio_bitrate = p.audio_bitrate

        # Update UI to reflect preset
        self.query_one("#crf-input", Input).value = str(p.crf)

        # Select the right video codec radio
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

    # ----- Encoding -----

    def _start_encode(self) -> None:
        if self._encoding:
            self.notify("Already encoding!", severity="warning")
            return
        if not self._job.input_path.is_file():
            self.notify("No input file selected!", severity="error")
            return

        self._encoding = True
        self._job.resolve_output_path()  # Lock in output path before encoding
        self.query_one("#encode-status", Static).update(
            f"Encoding: {self._job.input_path.name}"
        )
        self.query_one("#encode-progress", ProgressBar).update(total=100, progress=0)
        self.query_one("#encode-stats", Static).update("")
        log = self.query_one("#ffmpeg-log", RichLog)
        log.clear()

        # Switch to encode tab
        self.query_one(TabbedContent).active = "tab-encode"

        self._encode_start_time = time.time()
        self.run_worker(self._run_ffmpeg, exclusive=True)

    async def _run_ffmpeg(self) -> None:
        """Run ffmpeg as an async subprocess, parse progress."""
        worker = get_current_worker()
        cmd = self._job.build_command()
        # Insert -progress pipe:1 before output file
        # cmd is: [ffmpeg, -i, input, ...flags, -y, output]
        # Insert before -y
        y_idx = cmd.index("-y")
        cmd_with_progress = cmd[:y_idx] + ["-progress", "pipe:1", "-stats_period", "0.5"] + cmd[y_idx:]

        duration = self._job.probe.duration if self._job.probe else 0

        log = self.query_one("#ffmpeg-log", RichLog)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_with_progress,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._ffmpeg_proc = proc

            # Read stderr in background for log display
            async def read_stderr():
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    if worker.is_cancelled:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        self.call_from_thread(log.write, text) if not self.is_running else log.write(text)

            stderr_task = asyncio.create_task(read_stderr())

            # Read stdout (progress pipe)
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

                if text == "progress=continue" or text == "progress=end":
                    self._update_progress(progress_data, duration)
                    progress_data = {}

            await stderr_task
            await proc.wait()

            self._ffmpeg_proc = None
            self._encoding = False

            if proc.returncode == 0:
                self._show_results()
            else:
                self.call_from_thread(
                    self.query_one("#encode-status", Static).update,
                    f"⚠ FFmpeg exited with code {proc.returncode}",
                )

        except Exception as e:
            self._encoding = False
            self._ffmpeg_proc = None
            self.call_from_thread(
                self.query_one("#encode-status", Static).update,
                f"⚠ Error: {e}",
            )

    def _update_progress(self, data: dict[str, str], duration: float) -> None:
        """Update progress bar and stats from ffmpeg progress data."""
        out_time = data.get("out_time_ms", data.get("out_time_us", "0"))
        try:
            # out_time_ms is in microseconds despite the name
            out_us = int(out_time)
            out_seconds = out_us / 1_000_000
        except ValueError:
            out_seconds = 0

        pct = 0.0
        if duration > 0 and out_seconds > 0:
            pct = min(100.0, (out_seconds / duration) * 100)

        speed = data.get("speed", "N/A")
        fps = data.get("fps", "N/A")
        total_size = data.get("total_size", "N/A")
        bitrate = data.get("bitrate", "N/A")
        frame = data.get("frame", "N/A")

        elapsed = time.time() - self._encode_start_time
        elapsed_str = _format_time(elapsed)
        eta_str = "N/A"
        if pct > 0:
            total_est = elapsed / (pct / 100)
            eta = total_est - elapsed
            eta_str = _format_time(eta)

        # Format size nicely
        size_str = total_size
        try:
            size_bytes = int(total_size)
            if size_bytes >= 1_048_576:
                size_str = f"{size_bytes / 1_048_576:.1f} MB"
            elif size_bytes >= 1024:
                size_str = f"{size_bytes / 1024:.0f} KB"
        except (ValueError, TypeError):
            pass

        stats = (
            f"Frame: {frame}  FPS: {fps}  Speed: {speed}\n"
            f"Size: {size_str}  Bitrate: {bitrate}\n"
            f"Elapsed: {elapsed_str}  ETA: {eta_str}  Progress: {pct:.1f}%"
        )

        try:
            self.query_one("#encode-progress", ProgressBar).update(progress=pct)
            self.query_one("#encode-stats", Static).update(stats)
            self.query_one("#encode-status", Static).update(
                f"Encoding: {self._job.input_path.name} — {pct:.1f}%"
            )
        except Exception:
            pass

    def _cancel_encode(self) -> None:
        if self._ffmpeg_proc:
            self._ffmpeg_proc.terminate()
            self.notify("Encoding cancelled.")
            self._encoding = False
            self.query_one("#encode-status", Static).update("Cancelled.")

    def _show_results(self) -> None:
        """Show completion summary."""
        elapsed = time.time() - self._encode_start_time
        out_path = self._job.output_path
        in_size = self._job.probe.size if self._job.probe else 0
        out_size = 0
        if out_path.exists():
            out_size = out_path.stat().st_size

        in_str = _format_size(in_size)
        out_str = _format_size(out_size)
        saved_pct = ((1 - out_size / in_size) * 100) if in_size > 0 else 0

        result_text = (
            f"✅ Encoding complete!\n\n"
            f"  Input:    {self._job.input_path.name} ({in_str})\n"
            f"  Output:   {out_path.name} ({out_str})\n"
            f"  Saved:    {saved_pct:.1f}%\n"
            f"  Time:     {_format_time(elapsed)}\n"
            f"  Codec:    {self._job.video_codec.label}\n"
            f"  CRF:      {self._job.crf}\n"
        )

        try:
            self.query_one("#results-box", Static).update(result_text)
            self.query_one("#encode-status", Static).update("✅ Done!")
            self.query_one("#encode-progress", ProgressBar).update(progress=100)
            self.query_one(TabbedContent).active = "tab-done"
        except Exception:
            pass


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
