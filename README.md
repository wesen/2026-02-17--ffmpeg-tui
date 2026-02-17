# ffmpeg-tui

A terminal UI for cross-encoding videos with ffmpeg. Built with [Textual](https://textual.textualize.io/).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⭘      FFmpeg TUI                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│  Files  Codec  Settings  Encode  Done                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  📁 File Selection                                                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────┐                         │
│  │ Enter video file path...                        │  [+ Add]  [Browse ↕]   │
│  └─────────────────────────────────────────────────┘                         │
│                                                                              │
│  ┌─ 2 file(s) selected: ──────────────────────────────────────────────────┐  │
│  │  1. interview_raw.mov                                                  │  │
│  │     1920x1080 H264 23m:12s 2.3 GB                                     │  │
│  │  2. concert_4k.mp4                                                     │  │
│  │     3840x2160 H264 1h:02m 8.1 GB                                      │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  [Remove Selected]  [Clear All]                                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  q Quit  F1 Files  F2 Codec  F3 Settings  F4 Encode  F5 Done                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Multi-file selection** — browse or type paths, add multiple files with ffprobe metadata display
- **6 video codecs** — H.264, H.265, AV1, VP9, plus NVIDIA NVENC hardware encoders
- **5 audio options** — AAC, Opus, MP3, copy (passthrough), or no audio
- **3 containers** — MP4, MKV, WebM with auto-suggestion based on codec
- **Quality control** — CRF slider with per-codec ranges, encoder preset selection
- **Resolution scaling** — downscale to 2160p/1440p/1080p/720p/480p/360p
- **7 built-in presets** — Web Upload, Archive, Web Streaming, Future-Proof, GPU Quick
- **Live command preview** — always see the exact ffmpeg command being built
- **Batch encoding** — encode all queued files sequentially with per-job progress tracking
- **Real-time progress** — frame, FPS, speed, bitrate, ETA via ffmpeg's `-progress` pipe
- **Pause/Resume** — SIGSTOP/SIGCONT to pause and resume long encodes
- **Output directory** — configurable, auto-created if missing
- **Results table** — per-file input/output sizes, savings %, time, with totals

## Requirements

- Python ≥ 3.10
- ffmpeg and ffprobe on PATH

## Install

```bash
# Clone and install in editable mode
git clone <this-repo>
cd ffmpeg-tui
pip install -e .
```

## Usage

```bash
ffmpeg-tui
```

Or run directly:

```bash
python -m ffmpeg_tui
```

### Workflow

1. **Files** (F1) — add one or more video files
2. **Codec** (F2) — pick video codec, container, and audio codec
3. **Settings** (F3) — set CRF quality, encoder speed preset, resolution, output directory; or load a built-in preset
4. **Encode** (F4) — start encoding; watch per-job progress, pause/resume, or cancel
5. **Done** (F5) — review results table with sizes and savings

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `F1`–`F5` | Switch tabs |
| `q` | Quit |
| `Tab` / `Shift+Tab` | Navigate widgets |
| `Enter` | Activate buttons / submit input |
| `Space` | Toggle radio buttons |

### Built-in presets

| Preset | Codec | CRF | Speed | Audio | Container |
|--------|-------|-----|-------|-------|-----------|
| Web Upload (YouTube) | H.264 | 18 | slow | AAC 192k | MP4 |
| Archive (Small) | H.265 | 23 | medium | AAC 128k | MKV |
| Archive (Quality) | H.265 | 18 | slow | AAC 192k | MKV |
| Web Streaming | VP9 | 30 | — | Opus 128k | WebM |
| Future-Proof (AV1) | AV1 | 30 | 6 | Opus 128k | MKV |
| Quick GPU (H.264) | NVENC | 23 | p4 | Copy | MP4 |
| Quick GPU (H.265) | NVENC | 28 | p4 | Copy | MKV |

## Project structure

```
src/ffmpeg_tui/
├── app.py              # Main Textual app — all 5 tabs, batch encoding, pause/resume
├── __main__.py         # Entry point
└── models/
    ├── probe.py        # ffprobe JSON wrapper → ProbeResult dataclass
    ├── codecs.py       # Video/audio codec, container, and preset definitions
    └── job.py          # EncodingJob — command builder, output path, queue status
```

## How it works

- **File probing**: `ffprobe -print_format json -show_format -show_streams` extracts resolution, codec, duration, bitrate
- **Command building**: `EncodingJob.build_command()` assembles the ffmpeg invocation from UI settings
- **Progress tracking**: ffmpeg's `-progress pipe:1` writes structured key=value updates; parsed for frame/fps/speed/ETA
- **Async encoding**: Textual's worker API runs ffmpeg as an async subprocess — UI stays responsive
- **Pause/Resume**: `os.kill(pid, SIGSTOP)` pauses the ffmpeg process; `SIGCONT` resumes it

## License

MIT
