"""Wrap ffprobe to extract video/audio metadata."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AudioStream:
    """Metadata for a single audio stream."""

    codec: str = "unknown"
    sample_rate: int = 0
    channels: int = 0
    bitrate: int = 0  # bits/sec

    @property
    def bitrate_kbps(self) -> str:
        if self.bitrate:
            return f"{self.bitrate // 1000}k"
        return "N/A"


@dataclass
class VideoStream:
    """Metadata for a single video stream."""

    codec: str = "unknown"
    width: int = 0
    height: int = 0
    fps: float = 0.0
    pixel_format: str = "unknown"
    bitrate: int = 0  # bits/sec

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def bitrate_kbps(self) -> str:
        if self.bitrate:
            return f"{self.bitrate // 1000}k"
        return "N/A"


@dataclass
class ProbeResult:
    """Complete probe result for a media file."""

    path: Path = field(default_factory=lambda: Path("."))
    duration: float = 0.0  # seconds
    size: int = 0  # bytes
    format_name: str = "unknown"
    video: VideoStream | None = None
    audio: AudioStream | None = None
    error: str | None = None

    @property
    def duration_str(self) -> str:
        """Human-readable duration like '1h:02m:15s' or '23m:12s'."""
        total = int(self.duration)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h:{minutes:02d}m:{seconds:02d}s"
        return f"{minutes}m:{seconds:02d}s"

    @property
    def size_str(self) -> str:
        """Human-readable file size."""
        if self.size >= 1_073_741_824:
            return f"{self.size / 1_073_741_824:.1f} GB"
        if self.size >= 1_048_576:
            return f"{self.size / 1_048_576:.0f} MB"
        if self.size >= 1024:
            return f"{self.size / 1024:.0f} KB"
        return f"{self.size} B"

    @property
    def summary(self) -> str:
        """One-line summary: resolution codec duration size."""
        parts = []
        if self.video:
            parts.append(self.video.resolution)
            parts.append(self.video.codec.upper())
        parts.append(self.duration_str)
        parts.append(self.size_str)
        return " ".join(parts)


def _parse_fps(stream: dict) -> float:
    """Parse frame rate from ffprobe stream data."""
    # Try r_frame_rate first (e.g. "24000/1001"), then avg_frame_rate
    for key in ("r_frame_rate", "avg_frame_rate"):
        raw = stream.get(key, "0/0")
        if "/" in raw:
            num, den = raw.split("/", 1)
            try:
                n, d = int(num), int(den)
                if d > 0:
                    return round(n / d, 3)
            except ValueError:
                continue
    return 0.0


def probe(path: str | Path) -> ProbeResult:
    """Run ffprobe on a file and return parsed metadata.

    Never raises — errors are captured in ProbeResult.error.
    """
    path = Path(path)
    result = ProbeResult(path=path)

    if not path.exists():
        result.error = f"File not found: {path}"
        return result

    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        result.error = "ffprobe not found — is ffmpeg installed?"
        return result
    except subprocess.TimeoutExpired:
        result.error = "ffprobe timed out"
        return result

    if proc.returncode != 0:
        result.error = f"ffprobe failed (exit {proc.returncode})"
        return result

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result.error = "Failed to parse ffprobe output"
        return result

    # Format-level info
    fmt = data.get("format", {})
    result.duration = float(fmt.get("duration", 0))
    result.size = int(fmt.get("size", 0))
    result.format_name = fmt.get("format_name", "unknown")

    # Parse streams
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")

        if codec_type == "video" and result.video is None:
            result.video = VideoStream(
                codec=stream.get("codec_name", "unknown"),
                width=int(stream.get("width", 0)),
                height=int(stream.get("height", 0)),
                fps=_parse_fps(stream),
                pixel_format=stream.get("pix_fmt", "unknown"),
                bitrate=int(stream.get("bit_rate", 0) or 0),
            )

        elif codec_type == "audio" and result.audio is None:
            result.audio = AudioStream(
                codec=stream.get("codec_name", "unknown"),
                sample_rate=int(stream.get("sample_rate", 0) or 0),
                channels=int(stream.get("channels", 0) or 0),
                bitrate=int(stream.get("bit_rate", 0) or 0),
            )

    return result
