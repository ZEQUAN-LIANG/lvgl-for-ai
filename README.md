# LVGL Verify Loop

English | [简体中文](README.zh-CN.md)

**AI writes LVGL. AI verifies it. Humans only provide intent and feedback.**

An AI-first development and verification platform for LVGL: a real headless LVGL host, virtual input and virtual time, frame-by-frame session evidence, a web inspector, and an export path to real SiFli hardware.

## Why AI-first

In the age of AI, code is cheap. Writing C is no longer the bottleneck; what is missing is a loop that lets AI see the real screen and obtain verifiable evidence.

So this project hands LVGL development to AI: AI reads intent, writes C, runs scenarios, reads the evidence, and accepts its own work. Humans do not write code; they provide intent, give feedback on the screen, and set the acceptance criteria.

Everything is AI-first: AI sits in the developer's seat, while humans move up to intent and feedback.

| Human | AI |
| --- | --- |
| Provide intent and reference visuals | Write LVGL C code |
| Circle problems on the screen (annotations, whiteboards) | Run scenarios; read frames, timeline, diffs and logs |
| Define acceptance criteria and make the final call | Self-check against the criteria, self-accept, then fix |

It suits teams that write LVGL UIs with AI and need replayable evidence; it is not built for GPU performance analysis.

## What it does

### Default intro: the LVGL Verify Loop console

`user/app/intro/` is the skill's default app and default template: an 800×600 showcase assembled from real session snapshots (`user/scenarios/intro.json`).

### The AI loop: edit C → run a scenario → read evidence → judge

AI edits `user/app/**/*.c` directly, then builds and plays a scenario with one command:

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json --json
```

stdout is a single line of JSON pointing to a session; the session contains full PNG frames, the timeline, per-frame diffs and the engine log. AI reads this evidence against the human-provided acceptance criteria, then decides whether to change anything. The tool never outputs pass/fail; acceptance criteria come from humans.

There is no object tree, `inspect`, property read or `set`: exact internal state is printed to `engine.log` by user C code, and becomes part of the evidence too.

### Web inspector: live preview, replay, annotations, whiteboards

```bash
python -I console/entrypoints/serve.py --open
```

Fixed at `127.0.0.1:8765`. The page shows frames from the real LVGL runtime, either live or replayed from a recorded session; on the right is the annotation tool, where humans circle problems and write a note, saved as an annotation.

Whiteboards support single-frame, time-range and global scopes — good for sketching flows and explaining intent; every whiteboard requires text or labels, so images and words reach AI together.

AI reads these materials directly:

- Annotations and whiteboards: frame numbers, bboxes, ranges, text and labels in `annotations.json` and `whiteboards.json`;
- User code: `user/app/**/*.c` is the only source of truth; widget creation, `lv_obj_add_event_cb` bindings and state live in C;
- Run trace: `timeline.ndjson` records the object name and class hit by each input (`hit` / `hit_class`), and `frame_diffs.ndjson` records changed bboxes.

With the three aligned, AI can tell which code created a widget, which callback an event is bound to, who was hit by an input, and which area changed afterwards — then modify the code based on the annotations and whiteboards.

### Multi-version verification: one app, six LVGL versions

The same `apps` and the same scenario run on LVGL 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3, selected with `--lvgl <version>`. Cross-version comparison covers event semantics and the set of session files, not pixels.

Device apps are written against the LVGL 9.4 baseline; export only checks compatibility and rejects 9.5/9.6-only APIs.

### Real hardware: verify on the host, then SiFli export → build → flash

```bash
python -I chip-adapt/sifli/export.py sift_watch --dry-run --force
python -I chip-adapt/sifli/host/cli.py build --app sift_watch --actor ai --json
python -I chip-adapt/sifli/host/cli.py flash --app sift_watch --actor ai --json
```

The shared source stays in `user/app/`; export copies app sources against the LVGL 9.4 baseline. Without a board, you can only stop at host verification and an export dry-run — never claim the device is verified.

Huangshan Pai (SiFli SF32LB52x, board `sf32lb52-lchspi-ulp`) in real use; the desktop serial and flashing host lives in `chip-adapt/sifli/host/`. The board's screen is 390×450; apps built for other sizes need layout adjustments:

<p align="center"><video src="docs/media/huangshanpai.mp4" controls width="280"></video></p>

[Open the video](docs/media/huangshanpai.mp4)

Two more points: prebuilt LVGL libraries let you run with just GCC installed (`--prebuilt`); the tools are independent of harnesses like Claude Code and Cursor and are not tied to any model.

## Install the skill

The release zip **is** the skill. Download one of the two 0.2.2 bundles from
[GitHub Releases](https://github.com/ZEQUAN-LIANG/lvgl-for-ai/releases) or
[Gitee Releases](https://gitee.com/liang-zequan/lvgl-for-ai/releases):

- `lvgl-verify-loop-0.2.2-full-win64.zip`: all six LVGL versions and the viewer.
- `lvgl-verify-loop-0.2.2-full-sifli-win64.zip`: the same bundle plus the SiFli tools.

Python 3.9+ must be on PATH (`python`/`pythonw`, or `py`/`pyw`); the package
does not bundle Python. Running the bundled apps needs no CMake or GCC.

Install it as a personal Claude Code skill with one command (Windows PowerShell):

```powershell
Expand-Archive .\lvgl-verify-loop-0.2.2-full-win64.zip "$env:USERPROFILE\.claude\skills"
```

The zip contains a single top-level `lvgl-verify-loop\` folder, so this creates
`%USERPROFILE%\.claude\skills\lvgl-verify-loop\SKILL.md`. For a single project,
extract into that project's `.claude\skills\` folder instead. You can also
right-click the zip, choose **Extract All**, and use the same destination.

Restart Claude Code, then run:

```text
/lvgl-verify-loop
```

Or simply describe the LVGL UI you want. The skill edits `user/app/**/*.c`, runs
scenarios and reads the session evidence. The bundle carries the prebuilt LVGL libraries and
prebuilt engines for 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3, and the viewer. Running
them needs only Python 3.9+; no CMake, administrator rights or version
downloads. Rebuilding after the AI edits C needs GCC 15.2.0 (MinGW-w64 64-bit),
matching the compiler recorded in the bundled LVGL libraries. CMake and Ninja are only
needed to build LVGL itself from source, which the release bundle does not do.

Without an AI, open the extracted `lvgl-verify-loop` folder and double-click
`bin\LVGL-AI-Viewer.exe` (or run `bin\lvgl.cmd serve`); with Python on PATH the
browser opens `http://127.0.0.1:8765`.

Open the extracted `lvgl-verify-loop` folder as the Claude Code workspace (or
`cd` there first); the skill's commands are relative to that folder. If you
installed into the skills directory:

```bat
cd "%USERPROFILE%\.claude\skills\lvgl-verify-loop"
bin\lvgl.cmd run --scenario user\scenarios\intro.json --json
```

## From source

```bash
git clone https://gitee.com/liang-zequan/lvgl-for-ai.git lvgl-for-agent
cd lvgl-for-agent

# 1. Download and install LVGL 9.6 sources
python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .

# 2. Download PNG encoder sources (zlib / libpng)
python -I scripts/fetch_png.py --repo-root .

# 3. Run a scenario (the first run builds the engine; usually takes a few minutes)
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# 4. Open the web inspector
python -I console/entrypoints/serve.py --open
```

On success the exit code is `0`, the last stdout line is the session directory, and `manifest.json` has `status: ok`. The default `--source auto` tries GitHub codeload first and the Gitee mirror second; the Gitee LVGL mirror can return HTML/400, so use the default or a version pack when that happens.

Working from source? Open this repository in Claude Code; `CLAUDE.md` covers the
repo workflow and `SKILL.md` is the skill entry. No separate skill install
is needed.

## Reading the evidence

A session is the `user/sessions/<id>/` directory:

```text
user/sessions/<id>/
  manifest.json          # status, app, resolution, frame count
  timeline.ndjson        # input events, frame spans, marks
  frame_diffs.ndjson     # per-frame changed bboxes
  frames/                # full PNGs; only frames with visual changes
  snapshots/             # named snapshots
  engine.log             # runtime log; exact state is printf'd here by C code
  build.log              # actual build commands and compiler output
  annotations.json       # human annotations (optional)
```

stdout with `--json` is a single line, e.g. (key fields only, paths simplified):

```json
{"session_id": "20261114-095536-1d9d", "session_dir": "user/sessions/20261114-095536-1d9d", "status": "ok", "app": "coffee", "display": {"width": 800, "height": 600}, "frame_count": 305, "error": null}
```


AI conclusions must point at these files. `status: ok` means the session ended normally; whether the UI meets the acceptance criteria is decided by humans.

## Versions and real hardware

- Host default is LVGL 9.6, for daily preview and evidence collection; the package's `intro` app targets 9.4+.
- The 0.2.2 release publishes exactly two zips: `full` contains all six LVGL versions and their engines; `full-sifli` adds the SiFli tools. Both require Python 3.9+ on the host and do not bundle it; there is no per-version download step.
- The bundled LVGL libraries were exported with GCC 15.2.0. Rebuilding user C through the prebuilt path requires the same GCC version; CMake/Ninja are only for LVGL source builds.
- Device apps are written against the LVGL 9.4 baseline; export only checks compatibility and never rewrites sources.
- Inspect versions or use source installation only for a custom build:

  ```bash
  python -I scripts/install_version.py --list
  python -I scripts/install_version.py --lvgl 9.4 --mode source
  ```

  Source mode needs CMake/Ninja/GCC. A scenario may set `"lvgl": "9.4"`;
  `--lvgl` wins over the scenario, then `LVGL_VERIFY_LOOP_LVGL_VERSION`.
- SiFli is only in `full-sifli`: the self-developed export/host layer,
  `SiFli-Host.exe`, pyserial/xterm, `sift_watch` source and an exported example.
  It does not include the SiFli SDK, ARM toolchain, sftool or firmware. SDK,
  toolchain and sftool installation are in `chip-adapt/vendor/README.md`.

## Requirements

| Dependency | Requirement | Notes |
| --- | --- | --- |
| Python | 3.9+ on PATH; not bundled | Tool layer uses the standard library; asset conversion uses bundled FreeType/pypng, no `pip install` or Node.js; the engine also links the bundled FreeType 2.13.2 with `LV_USE_FREETYPE=1` on every version; always run with `python -I` |
| GCC | MinGW-w64 64-bit, 15.2.0 | Only when rebuilding user C; must match the bundled LVGL manifest. The prebuilt engine does not need it |
| CMake | ≥ 3.20 | LVGL source builds only; not needed for the release bundles |
| Ninja | any recent version | LVGL source builds only; not needed for the release bundles |
| curl | any recent version | Only for downloading LVGL / PNG sources |
| Disk | ~1 GB free | LVGL sources and build artifacts |

On Windows, MSYS2 UCRT64 is recommended. Full installation steps, PATH setup, first-run notes and common errors are in `console/README.md`.

## More docs

- `console/README.md`: tool usage, environment setup, common errors, tests, lint and formatting.
- `user/app/GUIDE.md`: writing user apps.
- `docs/skill/`: the skill contract (`SKILL.md`) and per-version `api-nav/`.
- `chip-adapt/sifli/README.md` / `chip-adapt/docs/sifli.html`: SiFli adaptation layer and capabilities.
- `chip-adapt/host/README.md`: standalone flasher page shared by the ESP32 (esptool) and SiFli (sftool) hosts, including the HTTP contract, firmware sources and troubleshooting.
- `CONTEXT.md`: domain glossary.
- `CLAUDE.md`: repository working notes for AI coding agents.
- `SKILL.md` at the release package root (source: `docs/skill/SKILL.md`): the AI entry contract and agent workflow for the installed skill.

## License

Project source is MIT; see `LICENSE`. Full license texts for LVGL, lodepng, zlib, libpng, freetype-py, FreeType, pypng and the lv_font_conv algorithm reference are in `docs/licenses/`.
