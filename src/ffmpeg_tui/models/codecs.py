"""Codec, container, and preset definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Video codecs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VideoCodec:
    """A video encoder definition."""

    id: str  # internal key, e.g. "libx264"
    label: str  # display name, e.g. "H.264 (libx264)"
    encoder: str  # ffmpeg encoder name
    description: str
    crf_range: tuple[int, int] = (0, 51)  # (min, max) CRF
    crf_default: int = 23
    presets: tuple[str, ...] = (
        "ultrafast", "superfast", "veryfast", "faster", "fast",
        "medium", "slow", "slower", "veryslow",
    )
    preset_default: str = "medium"
    hardware: bool = False


VIDEO_CODECS: list[VideoCodec] = [
    VideoCodec(
        id="libx264",
        label="H.264 (libx264)",
        encoder="libx264",
        description="Universal. Fast. Good quality.",
    ),
    VideoCodec(
        id="libx265",
        label="H.265 / HEVC (libx265)",
        encoder="libx265",
        description="50% smaller. Slower encode.",
        crf_default=28,
    ),
    VideoCodec(
        id="libsvtav1",
        label="AV1 (SVT-AV1)",
        encoder="libsvtav1",
        description="Best compression. Very slow.",
        crf_range=(0, 63),
        crf_default=30,
        presets=tuple(str(i) for i in range(14)),  # 0-13
        preset_default="6",
    ),
    VideoCodec(
        id="libvpx-vp9",
        label="VP9 (libvpx-vp9)",
        encoder="libvpx-vp9",
        description="Good for web. Moderate speed.",
        crf_range=(0, 63),
        crf_default=30,
        presets=(),  # VP9 uses -speed, not -preset
        preset_default="",
    ),
    VideoCodec(
        id="h264_nvenc",
        label="H.264 (NVENC)",
        encoder="h264_nvenc",
        description="NVIDIA GPU. Very fast.",
        crf_range=(0, 51),
        crf_default=23,
        presets=("p1", "p2", "p3", "p4", "p5", "p6", "p7"),
        preset_default="p4",
        hardware=True,
    ),
    VideoCodec(
        id="hevc_nvenc",
        label="H.265 (NVENC)",
        encoder="hevc_nvenc",
        description="NVIDIA GPU. Very fast.",
        crf_range=(0, 51),
        crf_default=28,
        presets=("p1", "p2", "p3", "p4", "p5", "p6", "p7"),
        preset_default="p4",
        hardware=True,
    ),
]

CODEC_BY_ID: dict[str, VideoCodec] = {c.id: c for c in VIDEO_CODECS}


# ---------------------------------------------------------------------------
# Audio codecs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AudioCodec:
    """An audio encoder definition."""

    id: str
    label: str
    encoder: str  # ffmpeg encoder name, or "copy" / ""
    default_bitrate: str  # e.g. "128k"


AUDIO_CODECS: list[AudioCodec] = [
    AudioCodec(id="aac", label="AAC", encoder="aac", default_bitrate="128k"),
    AudioCodec(id="libopus", label="Opus", encoder="libopus", default_bitrate="128k"),
    AudioCodec(id="copy", label="Copy (no re-encode)", encoder="copy", default_bitrate=""),
    AudioCodec(id="libmp3lame", label="MP3", encoder="libmp3lame", default_bitrate="192k"),
    AudioCodec(id="none", label="No audio", encoder="", default_bitrate=""),
]

AUDIO_BY_ID: dict[str, AudioCodec] = {c.id: c for c in AUDIO_CODECS}


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Container:
    """An output container format."""

    id: str
    label: str
    extension: str
    description: str


CONTAINERS: list[Container] = [
    Container(id="mp4", label="MP4", extension=".mp4", description="Most compatible"),
    Container(id="mkv", label="MKV", extension=".mkv", description="Supports everything"),
    Container(id="webm", label="WebM", extension=".webm", description="Web streaming"),
]

CONTAINER_BY_ID: dict[str, Container] = {c.id: c for c in CONTAINERS}

# Which container to suggest per video codec
DEFAULT_CONTAINER: dict[str, str] = {
    "libx264": "mp4",
    "libx265": "mkv",
    "libsvtav1": "mkv",
    "libvpx-vp9": "webm",
    "h264_nvenc": "mp4",
    "hevc_nvenc": "mkv",
}


# ---------------------------------------------------------------------------
# Presets (full encoding configurations)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EncodingPreset:
    """A named preset covering codec + quality + audio + container."""

    name: str
    video_codec_id: str
    crf: int
    preset: str
    audio_codec_id: str
    audio_bitrate: str
    container_id: str


PRESETS: list[EncodingPreset] = [
    EncodingPreset("Web Upload (YouTube)", "libx264", 18, "slow", "aac", "192k", "mp4"),
    EncodingPreset("Archive (Small)", "libx265", 23, "medium", "aac", "128k", "mkv"),
    EncodingPreset("Archive (Quality)", "libx265", 18, "slow", "aac", "192k", "mkv"),
    EncodingPreset("Web Streaming", "libvpx-vp9", 30, "", "libopus", "128k", "webm"),
    EncodingPreset("Future-Proof (AV1)", "libsvtav1", 30, "6", "libopus", "128k", "mkv"),
    EncodingPreset("Quick GPU (H.264)", "h264_nvenc", 23, "p4", "copy", "", "mp4"),
    EncodingPreset("Quick GPU (H.265)", "hevc_nvenc", 28, "p4", "copy", "", "mkv"),
]
