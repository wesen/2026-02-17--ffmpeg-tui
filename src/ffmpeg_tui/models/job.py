"""Encoding job model — ties together input, codec choices, and settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ffmpeg_tui.models.codecs import (
    AUDIO_BY_ID,
    CODEC_BY_ID,
    CONTAINER_BY_ID,
    AudioCodec,
    Container,
    VideoCodec,
)
from ffmpeg_tui.models.probe import ProbeResult


@dataclass
class EncodingJob:
    """All parameters needed to encode one file."""

    input_path: Path = field(default_factory=lambda: Path("."))
    probe: ProbeResult | None = None
    video_codec_id: str = "libx264"
    audio_codec_id: str = "aac"
    container_id: str = "mp4"
    crf: int = 23
    preset: str = "medium"
    audio_bitrate: str = "128k"
    output_dir: Path | None = None  # None = same dir as input
    _resolved_output: Path | None = field(default=None, repr=False)

    @property
    def video_codec(self) -> VideoCodec:
        return CODEC_BY_ID[self.video_codec_id]

    @property
    def audio_codec(self) -> AudioCodec:
        return AUDIO_BY_ID[self.audio_codec_id]

    @property
    def container(self) -> Container:
        return CONTAINER_BY_ID[self.container_id]

    @property
    def output_path(self) -> Path:
        """Return the resolved output path (stable once resolved)."""
        if self._resolved_output is not None:
            return self._resolved_output
        return self._compute_output_path()

    def resolve_output_path(self) -> Path:
        """Lock in the output path (call once before encoding starts)."""
        self._resolved_output = self._compute_output_path()
        return self._resolved_output

    def _compute_output_path(self) -> Path:
        stem = self.input_path.stem
        ext = self.container.extension
        base_dir = self.output_dir or self.input_path.parent
        out = base_dir / f"{stem}{ext}"
        # Avoid overwriting input
        if out == self.input_path:
            out = base_dir / f"{stem}_encoded{ext}"
        # Avoid overwriting existing output
        counter = 1
        orig_out = out
        while out.exists():
            out = base_dir / f"{orig_out.stem}_{counter:03d}{ext}"
            counter += 1
        return out

    def build_command(self) -> list[str]:
        """Build the ffmpeg command as a list of arguments."""
        cmd = ["ffmpeg", "-i", str(self.input_path)]

        vc = self.video_codec

        # Video codec
        cmd += ["-c:v", vc.encoder]

        # CRF (NVENC uses -cq instead of -crf)
        if vc.hardware:
            cmd += ["-cq", str(self.crf)]
        else:
            cmd += ["-crf", str(self.crf)]

        # Preset
        if self.preset:
            if vc.id == "libvpx-vp9":
                cmd += ["-speed", self.preset]
            elif vc.id == "libsvtav1":
                cmd += ["-preset", self.preset]
            else:
                cmd += ["-preset", self.preset]

        # Audio
        ac = self.audio_codec
        if ac.encoder == "":
            cmd += ["-an"]
        elif ac.encoder == "copy":
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", ac.encoder]
            if self.audio_bitrate:
                cmd += ["-b:a", self.audio_bitrate]

        # Output (overwrite)
        cmd += ["-y", str(self.output_path)]
        return cmd

    def command_str(self) -> str:
        """Build the ffmpeg command as a display string."""
        return " ".join(self.build_command())
