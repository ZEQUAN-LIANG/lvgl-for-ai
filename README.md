# LVGL Verify Loop

An AI-first development and verification platform for LVGL. AI writes the C code, AI verifies it, and humans only provide intent and feedback.

## Overview

This project enables a complete AI-driven workflow for developing LVGL user interfaces:

- **AI writes LVGL C code** based on human intent
- **AI runs scenarios** to test the code
- **AI reads session evidence** (frames, timeline, logs)
- **AI judges** whether the work meets acceptance criteria

Humans provide intent, reference visuals, and acceptance criteria—but never write code.

## Key Features

### Headless LVGL Engine
A real headless LVGL host that runs without a display, making it ideal for automated testing and CI/CD pipelines.

### Multi-Version Support
One codebase, six LVGL versions: 9.6, 9.5, 9.4, 9.1, 8.4, and 8.3.

### Web Inspector
Live preview and replay at `127.0.0.1:8765` with:
- Frame-by-frame session replay
- Annotation tools for human feedback
- Whiteboards for sketching flows and intent

### Session Evidence
Every run produces comprehensive evidence:
- Full PNG frames
- Timeline with input events
- Per-frame diffs showing changed regions
- Runtime logs from user C code

### Real Hardware Support
- **SiFli SF32LB52x** (Huangshan Pai) via export chain
- **ESP32-C6** (Waveshare ESP32-C6-LCD-1.47) via Arduino bring-up

## Quick Start

### Install from Release

Download from [GitHub Releases](https://github.com/ZEQUAN-LIANG/lvgl-for-ai/releases) or [Gitee Releases](https://gitee.com/liang-zequan/lvgl-for-ai/releases):

- `lvgl-verify-loop-0.2.2-full-win64.zip` - All six LVGL versions + viewer
- `lvgl-verify-loop-0.2.2-full-sifli-win64.zip` - Above + SiFli tools

Requires Python 3.9+ on PATH.

### Run a Scenario

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json --json
```

Output is a single JSON line with the session directory.

### Open Web Inspector

```bash
python -I console/entrypoints/serve.py --open
```

Fixed at `http://127.0.0.1:8765`.

## From Source

```bash
git clone https://gitee.com/liang-zequan/lvgl-for-ai.git
cd lvgl-for-ai

# Install LVGL 9.6 sources
python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .

# Install PNG encoder sources
python -I scripts/fetch_png.py --repo-root .

# Run a scenario
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# Open web inspector
python -I console/entrypoints/serve.py --open
```

## Session Evidence Structure

```
user/sessions/<id>/
  manifest.json          # status, app, resolution, frame count
  timeline.ndjson        # input events, frame spans, marks
  frame_diffs.ndjson     # per-frame changed bboxes
  frames/                # full PNGs (only changed frames)
  snapshots/             # named snapshots
  engine.log             # runtime log from user C code
  build.log              # build commands and compiler output
  annotations.json       # human annotations (optional)
```

## Requirements

| Dependency | Notes |
|------------|-------|
| Python 3.9+ | On PATH; not bundled |
| GCC 15.2.0 | MinGW-w64 64-bit; only for rebuilding user C |
| CMake ≥3.20 | LVGL source builds only |
| Ninja | LVGL source builds only |
| curl | For downloading LVGL/PNG sources |

## Documentation

- `console/README.md` - Tool usage and environment setup
- `user/app/GUIDE.md` - Writing user applications
- `chip-adapt/sifli/README.md` - SiFli adaptation layer
- `chip-adapt/esp32/README.md` - ESP32-C6 board setup
- `CONTEXT.md` - Domain glossary

## License

MIT licensed. See `LICENSE` for details. Third-party licenses in `docs/licenses/`.