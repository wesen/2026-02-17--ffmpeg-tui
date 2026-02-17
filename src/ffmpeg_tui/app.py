"""Main Textual application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Footer,
    Header,
    Label,
    Static,
    TabbedContent,
    TabPane,
)


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
    .placeholder {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Files", id="tab-files"):
                yield Label("📁 File Selection", classes="pane-title")
                yield Static("Select input video files here.", classes="placeholder")
            with TabPane("Codec", id="tab-codec"):
                yield Label("🎬 Codec & Container", classes="pane-title")
                yield Static("Choose video/audio codec and container format.", classes="placeholder")
            with TabPane("Settings", id="tab-settings"):
                yield Label("⚙ Encoding Settings", classes="pane-title")
                yield Static("Configure quality, resolution, and encoding parameters.", classes="placeholder")
            with TabPane("Encode", id="tab-encode"):
                yield Label("📋 Encode", classes="pane-title")
                yield Static("Encoding progress will appear here.", classes="placeholder")
            with TabPane("Done", id="tab-done"):
                yield Label("✅ Done", classes="pane-title")
                yield Static("Encoding results will appear here.", classes="placeholder")
        yield Footer()
