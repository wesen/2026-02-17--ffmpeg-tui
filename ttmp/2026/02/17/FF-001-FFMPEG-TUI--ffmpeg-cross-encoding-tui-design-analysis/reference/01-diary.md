---
title: "Diary"
doc_type: reference
ticket: FF-001-FFMPEG-TUI
status: active
intent: long-term
topics:
  - tui
  - ffmpeg
  - python
  - video-encoding
created: "2026-02-17"
related_files:
  - /home/manuel/code/wesen/2026-02-17--ffmpeg-tui/ttmp/2026/02/17/FF-001-FFMPEG-TUI--ffmpeg-cross-encoding-tui-design-analysis/design/01-ffmpeg-tui-design-analysis.md
---

# Diary

## Goal

Capture the design analysis journey for an FFmpeg cross-encoding TUI in Python,
from research through screen mockups to design decisions, before any code is written.

## Step 1: Environment Research & Ticket Setup

Set up the docmgr workspace and researched the local environment to understand
what tools and libraries are available. This shapes every design decision — we
need to know what codecs ffmpeg has, what HW acceleration is present, and which
Python TUI libraries are installed before designing screens.

### Prompt Context

**User prompt (verbatim):** "Create a new docmgr FF-001-FFMPEG-TUI and analyze how to create a nice simple and clear textual (python) TUI to cross-encode videos, use ffmpeg. Store the document in the ticket, upload to remarkable. Add ASCII screenshots for me to review. DO NOT WRITE CODE yet. Keep a frequent diary as you work."

**Assistant interpretation:** Create a design analysis document (not code) with ASCII mockups for a Python Textual-based ffmpeg transcoding TUI, manage it in docmgr, keep a diary, and upload to reMarkable.

**Inferred user intent:** Get a reviewable, printed design document on reMarkable before committing to implementation. Wants to see the screens, understand the architecture, and decide on scope before any code is written.

### What I did
- Created docmgr ticket FF-001-FFMPEG-TUI with topics: tui, ffmpeg, python, video-encoding
- Created diary doc (reference/01-diary.md) and design doc (design/01-ffmpeg-tui-design-analysis.md)
- Probed system: Python 3.11.3, Textual 2.1.2, Rich 13.9.4, ffmpeg 6.1.1
- Inventoried available encoders: libx264, libx265, libsvtav1, librav1e, libaom, libvpx-vp9, nvenc, vaapi variants
- Confirmed HW acceleration: VAAPI, CUDA, QSV, Vulkan, OpenCL

### Why
- Need to design around real capabilities, not hypothetical ones
- Library choice (Textual vs alternatives) depends on what's installed and what each offers
- Encoder inventory determines what the codec selection screen shows

### What worked
- docmgr ticket creation and doc creation smooth
- ffmpeg has a very complete encoder set on this system (all major SW + HW encoders)
- Textual 2.1.2 is already installed with Rich — no new dependencies needed

### What didn't work
- N/A (setup phase, no failures)

### What I learned
- This system has both NVENC and VAAPI — HW encoding is a real option, not just a "nice to have"
- Textual 2.1.2 has mature widget set including DataTable, TabbedContent, RadioButton — enough to build every screen without custom widgets

### What was tricky to build
- N/A (research phase)

### What warrants a second pair of eyes
- N/A

### What should be done in the future
- Validate that NVENC actually works (having the encoder compiled in ≠ having a compatible GPU)

### Code review instructions
- N/A (no code yet)

### Technical details
- ffmpeg 6.1.1-3ubuntu5, libavcodec 60.31.102
- HW accels: vdpau, cuda, vaapi, qsv, drm, opencl, vulkan
- Available encoders: libx264, libx265, libsvtav1, librav1e, libaom, libvpx, libvpx-vp9, h264_nvenc, hevc_nvenc, h264_vaapi, hevc_vaapi

## Step 2: Design Analysis & ASCII Mockups

Wrote the full design analysis document with 5 ASCII screen mockups covering
the complete user flow: file selection → codec/container → encoding settings →
queue/progress → completion summary. Each mockup includes keybinding hints and
behavioral notes. Also documented architecture (module structure), key technical
decisions (progress parsing, subprocess management, presets), and a prioritized
MVP scope.

### Prompt Context

**User prompt (verbatim):** (same as Step 1)

**Assistant interpretation:** (same as Step 1)

**Inferred user intent:** (same as Step 1)

### What I did
- Designed 5 screens with detailed ASCII mockups (78-col width, ~30 rows each)
- Defined module structure: app.py, screens/, models/, workers/, widgets/, presets
- Documented codec/container compatibility and preset system (7 built-in presets)
- Wrote ffmpeg progress parsing strategy (-progress pipe:1 + stderr fallback)
- Defined MVP (v0.1) scope with priority/complexity matrix
- Listed risks, mitigations, and 5 open questions for review

### Why
- ASCII mockups let the user review the UX on reMarkable before any code exists
- Architecture section prevents "just start coding" chaos
- Command preview widget builds user trust and teaches ffmpeg CLI
- Preset system covers 90% of use cases without per-encode configuration

### What worked
- Textual's widget set maps perfectly to every UI element needed
- CRF slider with human-readable labels is a natural fit for Textual's built-in widgets
- Tab-based navigation (TabbedContent) avoids complex screen state machines

### What didn't work
- N/A (design phase)

### What I learned
- The command preview panel is the most important trust-building element — users should always see what ffmpeg command will run
- Separating HW encoders into their own section (below a divider) keeps the codec list clean
- Audio "copy" (passthrough) is the right default for cross-encoding — users usually just want to change the video codec

### What was tricky to build
- Fitting all the encoding settings into a single screen without overwhelming the user. Solved by: CRF slider with guidance labels, collapsible Advanced section, and presets for common workflows.
- Deciding how much ffmpeg log to show in the queue screen. Settled on 3-5 lines of raw stderr at the bottom, with structured stats above.

### What warrants a second pair of eyes
- The 5 open questions at the end of the design doc need user input before implementation
- Container/codec compatibility matrix needs validation (which combos are actually valid?)

### What should be done in the future
- Get user feedback on the ASCII mockups (this upload)
- Resolve open questions
- Implement v0.1 based on approved design

### Code review instructions
- Review the design doc: `ttmp/.../design/01-ffmpeg-tui-design-analysis.md`
- Focus on: screen mockups (Section 5), MVP scope table (Section 7), open questions (Section 10)

### Technical details
- Design doc is ~26KB, 5 ASCII mockups at 78-col width
- Estimated v0.1 size: ~500-700 lines of Python
- Dependencies: textual>=2.0, rich>=13.0 (both already installed)

## Step 3: Docmgr Bookkeeping & reMarkable Upload

Completed all ticket bookkeeping (tasks, changelog, file relations) and bundled
the design analysis + diary into a single PDF uploaded to reMarkable for offline
review. The document is now at `/ai/2026/02/17/FF-001-FFMPEG-TUI/` on the device.

### Prompt Context

**User prompt (verbatim):** (same as Step 1)

**Assistant interpretation:** (same as Step 1)

**Inferred user intent:** (same as Step 1)

### What I did
- Added 4 tasks to the ticket (design ✅, upload ✅, feedback pending, implement pending)
- Related design doc and diary to ticket index
- Updated changelog with design completion and upload entries
- Dry-run verified remarquee bundle upload
- Uploaded bundle: `FF-001 FFmpeg TUI Design.pdf` → `/ai/2026/02/17/FF-001-FFMPEG-TUI/`

### Why
- Clean ticket state for handoff/review
- reMarkable upload enables offline annotation of the ASCII mockups

### What worked
- `remarquee upload bundle` cleanly merged both docs into one PDF with ToC
- All docmgr commands ran without issues

### What didn't work
- N/A

### What I learned
- Bundle upload is the right approach — keeps design + diary as one reviewable document

### What was tricky to build
- N/A

### What warrants a second pair of eyes
- The 5 open questions in the design doc need answers before implementation begins

### What should be done in the future
- Wait for user review feedback on reMarkable
- Resolve open questions (Section 10 of design doc)
- Begin v0.1 implementation

### Code review instructions
- Review the PDF on reMarkable: `/ai/2026/02/17/FF-001-FFMPEG-TUI/FF-001 FFmpeg TUI Design.pdf`
- Focus on: 5 ASCII screen mockups, MVP scope table, open questions
