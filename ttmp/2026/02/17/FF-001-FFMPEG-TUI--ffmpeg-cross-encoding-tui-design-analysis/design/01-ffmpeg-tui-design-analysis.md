---
title: "FFmpeg TUI Design Analysis"
doc_type: design
ticket: FF-001-FFMPEG-TUI
status: active
intent: long-term
topics:
  - tui
  - ffmpeg
  - python
  - video-encoding
created: "2026-02-17"
related_files: []
---

# FFmpeg Cross-Encoding TUI — Design Analysis

## 1. Problem Statement

Video cross-encoding (transcoding) with ffmpeg is powerful but has a steep CLI
learning curve. Users must remember codec names, quality parameters, container
compatibility, and the right incantation of flags. A terminal UI (TUI) can make
this accessible while preserving the speed and scriptability of terminal
workflows.

**Goal:** Design a clean, simple Python TUI that lets users:

1. Select one or more input video files
2. Choose a target codec/container
3. Configure encoding quality and parameters
4. Monitor encoding progress in real-time
5. Batch-process multiple files

## 2. Environment & Available Tools

### System

| Component         | Version / Details                                     |
|-------------------|-------------------------------------------------------|
| Python            | 3.11.3                                                |
| FFmpeg            | 6.1.1 (Ubuntu, full codec suite)                      |
| HW Acceleration   | VAAPI, CUDA/NVENC, QSV, Vulkan, OpenCL                |

### Available Video Encoders (confirmed on this system)

| Codec   | Encoder       | Notes                              |
|---------|---------------|------------------------------------|
| H.264   | libx264       | Universal compatibility            |
| H.264   | h264_nvenc    | NVIDIA GPU hardware encode         |
| H.264   | h264_vaapi    | Intel/AMD hardware encode          |
| H.265   | libx265       | Better compression, slower         |
| H.265   | hevc_nvenc    | NVIDIA GPU hardware encode         |
| H.265   | hevc_vaapi    | Intel/AMD hardware encode          |
| AV1     | libsvtav1     | Best compression, slowest (SW)     |
| AV1     | librav1e      | Rust-based AV1 encoder             |
| AV1     | libaom        | Reference AV1 encoder              |
| VP9     | libvpx-vp9    | WebM/web streaming                 |
| VP8     | libvpx        | Legacy web format                  |

### Python TUI Libraries Available

| Library        | Version | Strengths                                      |
|----------------|---------|------------------------------------------------|
| **Textual**    | 2.1.2   | Modern CSS-styled widgets, async, rich ecosystem |
| **Rich**       | 13.9.4  | Beautiful tables/progress/panels, no interactivity |
| **blessed**    | 1.20.0  | Low-level terminal control                     |
| prompt_toolkit | 3.0.48  | Input/autocomplete, not layout-oriented        |

## 3. Library Recommendation: Textual

**Textual** is the clear winner for this project:

- **Widget-rich:** Built-in DataTable, Tree, Select, Input, ProgressBar,
  Header, Footer, Tabs, RadioButton, Checkbox — covers every screen we need
- **CSS styling:** Layouts via familiar CSS, not manual coordinate math
- **Async-native:** `asyncio` workers for non-blocking ffmpeg subprocess
  management — critical for real-time progress monitoring
- **Rich integration:** Inherits Rich's beautiful rendering (syntax
  highlighting, markdown, tables)
- **Active ecosystem:** Textualize actively maintained, good docs
- **Single dependency tree:** `textual` pulls in `rich` (already installed)

**Why not the others:**

- *Rich alone:* No interactive widgets, can't build forms/selections
- *blessed:* Too low-level, would require building every widget from scratch
- *prompt_toolkit:* Great for prompts, not for full-screen multi-pane layouts
- *urwid:* Mature but dated API, poor async story, ugly defaults

## 4. Application Architecture

### 4.1 Screen Flow

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  File Select │────▶│ Codec/Format │────▶│   Settings   │────▶│  Encode Queue│
│   (Screen 1) │     │  (Screen 2)  │     │  (Screen 3)  │     │  (Screen 4)  │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                                                              │
       │                    ┌──────────────┐                          │
       └────────────────────│   Completed  │◀─────────────────────────┘
                            │  (Screen 5)  │
                            └──────────────┘
```

Navigation: Tab-based (Textual `TabbedContent`) so users can jump between
screens. The flow is left-to-right but non-linear — you can always go back.

### 4.2 Module Structure

```
ffmpeg-tui/
├── app.py              # Main Textual App, screen routing
├── screens/
│   ├── file_select.py  # File browser + input list
│   ├── codec.py        # Codec/container picker
│   ├── settings.py     # Encoding parameters form
│   ├── queue.py        # Batch queue + progress monitoring
│   └── complete.py     # Results summary
├── models/
│   ├── job.py          # Encoding job dataclass
│   ├── codec.py        # Codec/container definitions
│   └── probe.py        # ffprobe wrapper (input analysis)
├── workers/
│   ├── encoder.py      # Async ffmpeg subprocess runner
│   └── progress.py     # ffmpeg progress parser (stderr/progress pipe)
├── widgets/
│   ├── file_tree.py    # Custom file tree with video filtering
│   ├── video_info.py   # Video metadata panel
│   └── progress_bar.py # Enhanced progress with ETA/speed
├── presets.py          # Built-in encoding presets
├── config.py           # User config (last dir, defaults)
└── __main__.py         # Entry point
```

## 5. Screen Designs (ASCII Mockups)

### Screen 1: File Selection

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⎆ FFmpeg TUI                                            ◷ 06:15 PM  ■ □ ✕ │
├──────────────────────────────────────────────────────────────────────────────┤
│  📁 Files │ 🎬 Codec │ ⚙ Settings │ 📋 Queue │ ✅ Done                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ File Browser ──────────────────────┐  ┌─ Selected Files ──────────────┐ │
│  │ 📂 ..                               │  │                               │ │
│  │ 📂 projects/                        │  │  1. interview_raw.mov         │ │
│  │ 📂 exports/                         │  │     1920x1080 H.264 23m:12s  │ │
│  │ 🎬 interview_raw.mov     2.3 GB    │  │     2.3 GB → ~450 MB (est)   │ │
│  │ 🎬 concert_4k.mp4        8.1 GB    │  │                               │ │
│  │ 🎬 tutorial_screen.mkv   1.1 GB    │  │  2. concert_4k.mp4            │ │
│  │ 🎬 drone_footage.mp4     4.7 GB    │  │     3840x2160 H.264 1h:02m   │ │
│  │ 📄 notes.txt                        │  │     8.1 GB → ~1.6 GB (est)   │ │
│  │ 🎬 wedding_clip.avi      980 MB    │  │                               │ │
│  │                                     │  │                               │ │
│  │                                     │  │                               │ │
│  └─────────────────────────────────────┘  └───────────────────────────────┘ │
│                                                                              │
│  Path: ~/Videos/raw                                                          │
│  Filter: *.mp4 *.mkv *.avi *.mov *.webm *.flv                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  [a] Add file  [r] Remove  [Enter] Open dir  [Tab] Next ▸  [q] Quit        │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- Left pane: filesystem tree, filtered to video files + directories
- Right pane: selected files with ffprobe metadata (resolution, codec, duration, size)
- Estimated output size shown based on target codec defaults
- `a` / `Enter` to add, `r` to remove, cursor keys to navigate

### Screen 2: Codec & Container Selection

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⎆ FFmpeg TUI                                            ◷ 06:15 PM  ■ □ ✕ │
├──────────────────────────────────────────────────────────────────────────────┤
│  📁 Files │ 🎬 Codec │ ⚙ Settings │ 📋 Queue │ ✅ Done                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ Video Codec ───────────────────────┐  ┌─ Container ──────────────────┐  │
│  │                                     │  │                              │  │
│  │  ( ) H.264 (libx264)               │  │  ( ) MP4  (.mp4)             │  │
│  │      Universal. Fast. Good quality. │  │      Most compatible         │  │
│  │                                     │  │                              │  │
│  │  (●) H.265 / HEVC (libx265)        │  │  (●) MKV  (.mkv)            │  │
│  │      50% smaller. Slower encode.    │  │      Supports everything     │  │
│  │                                     │  │                              │  │
│  │  ( ) AV1 (libsvtav1)               │  │  ( ) WebM (.webm)            │  │
│  │      Best compression. Very slow.   │  │      Web streaming           │  │
│  │                                     │  │                              │  │
│  │  ( ) VP9 (libvpx-vp9)              │  │  ( ) AVI  (.avi)             │  │
│  │      Good for web. Moderate speed.  │  │      Legacy format           │  │
│  │                                     │  │                              │  │
│  │  ── Hardware Accelerated ────────── │  │                              │  │
│  │  ( ) H.264 (NVENC)                 │  │                              │  │
│  │  ( ) H.265 (NVENC)                 │  │                              │  │
│  │  ( ) H.264 (VAAPI)                 │  │                              │  │
│  │  ( ) H.265 (VAAPI)                 │  │                              │  │
│  │                                     │  │                              │  │
│  └─────────────────────────────────────┘  └──────────────────────────────┘  │
│                                                                              │
│  ┌─ Audio Codec ───────────────────────────────────────────────────────────┐ │
│  │  (●) AAC (aac)  ( ) Opus (libopus)  ( ) Copy (no re-encode)           │ │
│  │  ( ) MP3 (libmp3lame)  ( ) Vorbis (libvorbis)  ( ) No audio           │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  ◂ [Shift+Tab] Back   Codec: H.265 → MKV + AAC   [Tab] Next ▸  [q] Quit   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- Radio buttons for codec selection, organized: software → hardware-accelerated
- Container auto-suggested based on codec (H.265 → MKV, VP9 → WebM) but overridable
- Audio codec row: copy (passthrough) is a great default for cross-encoding
- Invalid combinations greyed out (e.g., VP9 in AVI container)
- One-line description per codec to help users decide

### Screen 3: Encoding Settings

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⎆ FFmpeg TUI                                            ◷ 06:15 PM  ■ □ ✕ │
├──────────────────────────────────────────────────────────────────────────────┤
│  📁 Files │ 🎬 Codec │ ⚙ Settings │ 📋 Queue │ ✅ Done                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Encoding: H.265 (libx265) → MKV + AAC                                      │
│                                                                              │
│  ┌─ Quality ───────────────────────────────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  Mode:  (●) CRF (Constant Quality)  ( ) Bitrate  ( ) 2-Pass           │ │
│  │                                                                         │ │
│  │  CRF Value:     ◂ ███████████████░░░░░░░░░░░ ▸   23                   │ │
│  │                  ← better quality    smaller files →                    │ │
│  │                  (18=visually lossless  28=good  35=low)               │ │
│  │                                                                         │ │
│  │  Preset:  [▾ medium                           ]                        │ │
│  │           ultrafast / fast / medium / slow / veryslow                   │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Resolution ────────────────────────────────────────────────────────────┐ │
│  │  (●) Keep original   ( ) Scale to:  [▾ 1080p (1920×1080) ]            │ │
│  │                                                                         │ │
│  │  Available: 2160p  1440p  1080p  720p  480p  Custom                    │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Audio ─────────────────────────────────────────────────────────────────┐ │
│  │  Bitrate: [▾ 128k ]    Sample Rate: [▾ 48000 ]   Channels: [▾ stereo ]│ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Advanced (collapsed) ──────────────────────────────── [+] expand ─────┐ │
│  │  Pixel format • Tune • Profile/Level • Custom ffmpeg flags             │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Command Preview ───────────────────────────────────────────────────────┐ │
│  │  ffmpeg -i input.mov -c:v libx265 -crf 23 -preset medium              │ │
│  │         -c:a aac -b:a 128k -ar 48000 output.mkv                       │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  ◂ [Shift+Tab] Back   [p] Load preset   [s] Save preset   [Tab] Next ▸     │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- CRF slider with labeled guidance (human-readable quality descriptions)
- Preset dropdown for encode speed/quality tradeoff
- Resolution scaling with common presets, keeps aspect ratio
- **Command Preview:** Always visible, shows the exact ffmpeg command being built
  — this is key for learning and trust
- Collapsible "Advanced" for pixel format, tune, profile, and raw flags
- Preset load/save: store favorite configs as named presets (JSON)

### Screen 4: Encoding Queue & Progress

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⎆ FFmpeg TUI                                            ◷ 06:17 PM  ■ □ ✕ │
├──────────────────────────────────────────────────────────────────────────────┤
│  📁 Files │ 🎬 Codec │ ⚙ Settings │ 📋 Queue │ ✅ Done                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ Queue ─────────────────────────────────────────────────────────────────┐ │
│  │ # │ Input                │ Output              │ Status    │ Progress   │ │
│  │───┼──────────────────────┼─────────────────────┼───────────┼────────────│ │
│  │ 1 │ interview_raw.mov    │ interview_raw.mkv   │ Encoding  │ ████░ 67%  │ │
│  │ 2 │ concert_4k.mp4       │ concert_4k.mkv      │ Waiting   │ ░░░░░  0%  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Current Job: interview_raw.mov ────────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  Progress: ████████████████████████████████░░░░░░░░░░░░░░░░  67.3%     │ │
│  │                                                                         │ │
│  │  ┌─────────────────────┬─────────────────────┬────────────────────────┐ │ │
│  │  │ Time:  15m:32s      │ ETA:   7m:40s       │ Total:  ~23m:12s      │ │ │
│  │  ├─────────────────────┼─────────────────────┼────────────────────────┤ │ │
│  │  │ Frame:  23,847      │ FPS:   42.3         │ Speed:  1.73x          │ │ │
│  │  ├─────────────────────┼─────────────────────┼────────────────────────┤ │ │
│  │  │ Size:   298 MB      │ Bitrate: 4,218 kb/s │ Est Total: ~445 MB    │ │ │
│  │  └─────────────────────┴─────────────────────┴────────────────────────┘ │ │
│  │                                                                         │ │
│  │  ffmpeg -i interview_raw.mov -c:v libx265 -crf 23 -preset medium      │ │
│  │         -c:a aac -b:a 128k interview_raw.mkv                           │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Log (last 5 lines) ───────────────────────────────────────────────────┐ │
│  │  frame=23847 fps=42.3 q=28.0 size=298MB time=00:15:32.1 speed=1.73x   │ │
│  │  frame=23889 fps=42.2 q=28.0 size=298MB time=00:15:33.8 speed=1.73x   │ │
│  │  frame=23931 fps=42.3 q=27.0 size=299MB time=00:15:35.5 speed=1.73x   │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  [Enter] Start  [p] Pause  [c] Cancel job  [x] Cancel all  [q] Quit        │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- Top table: queue overview with per-job progress bars
- Middle panel: detailed stats for the active job — frame, FPS, speed, bitrate, ETA
- Bottom: scrolling ffmpeg log output (raw stderr)
- ffmpeg progress parsed via `-progress pipe:1` or stderr regex
- Pause sends SIGSTOP to ffmpeg, resume sends SIGCONT
- Cancel sends SIGTERM then cleans up partial output file

### Screen 5: Completion Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⎆ FFmpeg TUI                                            ◷ 06:45 PM  ■ □ ✕ │
├──────────────────────────────────────────────────────────────────────────────┤
│  📁 Files │ 🎬 Codec │ ⚙ Settings │ 📋 Queue │ ✅ Done                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ Results ───────────────────────────────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  ✅ 2 files encoded successfully                                        │ │
│  │                                                                         │ │
│  │  # │ File                 │ In Size  │ Out Size │ Saved   │ Time        │ │
│  │  ──┼──────────────────────┼──────────┼──────────┼─────────┼──────────── │ │
│  │  1 │ interview_raw.mov    │  2.3 GB  │  412 MB  │  82.5%  │ 23m:08s    │ │
│  │  2 │ concert_4k.mp4       │  8.1 GB  │  1.4 GB  │  82.7%  │ 58m:41s    │ │
│  │  ──┼──────────────────────┼──────────┼──────────┼─────────┼──────────── │ │
│  │    │ TOTAL                │ 10.4 GB  │  1.8 GB  │  82.7%  │ 1h:21m     │ │
│  │                                                                         │ │
│  │  Output directory: ~/Videos/encoded/                                    │ │
│  │  Codec: H.265 (libx265) CRF 23 medium → MKV + AAC 128k               │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Actions ───────────────────────────────────────────────────────────────┐ │
│  │  [o] Open output dir   [n] New batch   [l] View log   [q] Quit         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  Total saved: 8.6 GB (82.7%)   Total time: 1h:21m                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 6. Key Design Decisions

### 6.1 FFmpeg Progress Parsing

Two approaches for real-time progress:

1. **`-progress pipe:1`** (recommended): FFmpeg writes key=value progress to a
   pipe. Reliable, structured, gives `out_time`, `speed`, `bitrate`, `frame`.
2. **Stderr parsing**: Regex on ffmpeg's stderr line. Fragile but universal.

Recommendation: Use `-progress pipe:1` with stderr as fallback/log display.

### 6.2 Subprocess Management

```
App (asyncio event loop)
  └── Worker thread
        └── asyncio.create_subprocess_exec("ffmpeg", ...)
              ├── stdout → progress pipe reader
              ├── stderr → log panel reader
              └── process.pid → for SIGSTOP/SIGCONT/SIGTERM
```

Textual's `Worker` API handles async background tasks perfectly. The worker
reads ffmpeg's progress pipe and posts `ProgressUpdate` messages to the UI.

### 6.3 Presets System

Built-in presets cover 90% of use cases:

| Preset Name           | Codec     | CRF | Preset  | Audio   | Container |
|-----------------------|-----------|-----|---------|---------|-----------|
| Web Upload (YouTube)  | H.264     | 18  | slow    | AAC 192k| MP4       |
| Archive (Small)       | H.265     | 23  | medium  | AAC 128k| MKV       |
| Archive (Quality)     | H.265     | 18  | slow    | AAC 192k| MKV       |
| Web Streaming         | VP9       | 30  | —       | Opus 128k| WebM     |
| Future-Proof          | AV1       | 30  | 6       | Opus 128k| MKV      |
| Quick (GPU H.264)     | h264_nvenc| —   | p4      | Copy    | MP4       |
| Quick (GPU H.265)     | hevc_nvenc| —   | p4      | Copy    | MKV       |

Users can save custom presets to `~/.config/ffmpeg-tui/presets.json`.

### 6.4 File Probing

Use `ffprobe -v quiet -print_format json -show_format -show_streams` to get:

- Duration, total bitrate, file size
- Video: codec, resolution, frame rate, pixel format, color space
- Audio: codec, sample rate, channels, bitrate

This populates the "Selected Files" panel and enables size estimation.

### 6.5 Output Naming

Default: `{input_stem}.{output_ext}` in a configurable output directory.
Conflict handling: append `_encoded` or `_001` suffix. Never overwrite silently.

## 7. Minimal Viable Scope (v0.1)

| Feature                      | Priority | Complexity |
|------------------------------|----------|------------|
| Single file selection (path) | P0       | Low        |
| Codec radio selection        | P0       | Low        |
| CRF/quality slider           | P0       | Medium     |
| Single-file encode + progress| P0       | Medium     |
| ffprobe input info           | P0       | Low        |
| Command preview              | P0       | Low        |
| File browser tree            | P1       | Medium     |
| Batch queue                  | P1       | Medium     |
| Preset load/save             | P1       | Low        |
| HW encoder detection         | P1       | Medium     |
| Resolution scaling           | P2       | Low        |
| 2-pass encoding              | P2       | Medium     |
| Audio codec settings         | P2       | Low        |
| Pause/resume                 | P2       | Low        |

**v0.1 delivers:** pick a file → choose codec → set quality → encode with
live progress → see result. ~500-700 lines of Python.

## 8. Dependencies

```
textual>=2.0
rich>=13.0
```

No other dependencies. FFmpeg and ffprobe must be on PATH.

## 9. Risks & Mitigations

| Risk                                  | Mitigation                            |
|---------------------------------------|---------------------------------------|
| ffmpeg progress parsing breaks        | Dual approach: -progress + stderr     |
| HW encoders unavailable               | Probe at startup, grey out options    |
| Large file stalls UI                  | All I/O in Textual Workers (async)    |
| Container/codec incompatibility       | Validation matrix, grey invalid combos|
| User wants raw ffmpeg flags           | "Advanced" panel with custom flags    |
| Terminal too small for layout         | Responsive CSS, min-width warning     |

## 10. Open Questions for Review

1. **Single-file vs directory-recursive scan?** Current design is explicit
   file selection. Should we add a "scan directory" mode?
2. **Output directory strategy:** Same directory as input? A single output
   directory? Per-job configurable?
3. **Subtitle handling:** Copy subtitles? Convert? Ignore for v0.1?
4. **Config persistence:** How much state to save between sessions?
   (Last directory, last codec choice, window size?)
5. **Error recovery:** If ffmpeg fails mid-encode, what to show? Just the
   error log, or try to diagnose common issues (missing codec, permission)?
