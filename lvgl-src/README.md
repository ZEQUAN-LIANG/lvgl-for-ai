# LVGL source trees (not vendored)

This directory is populated on demand. LVGL sources are **not** committed to
this repository; only this README is tracked. `lvgl-src/*` is ignored by Git
except for this file.

Upstream: <https://github.com/lvgl/lvgl> (MIT)

## Supported releases

| Version | Upstream tag |
| --- | --- |
| 9.6 | `v9.6.0` |
| 9.5 | `v9.5.0` |
| 9.4 | `v9.4.0` |
| 9.1 | `v9.1.0` |
| 8.4 | `v8.4.0` |
| 8.3 | `v8.3.11` |

The tags are pinned in `core/tools/fetch_lvgl.py`. The script also verifies
the version macros inside the archive, so a renamed or drifted tag fails before
anything is installed.

## Download and install

```bash
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .
```

The script:

1. downloads the exact official tag (codeload.github.com first, then the Gitee
   mirror),
2. verifies the version macros,
3. applies the patches in `patches/<version>/` (if any),
4. installs the tree under `lvgl-src/<version>/`, and
5. writes `lvgl-src/<version>/.lvgl-ai-source.json` with the tag and the
   applied patch names.

Downloaded archives are cached in `.scratch/tmp/archives/`. Use `--force` to
replace an existing tree, `--no-patch` to skip patches, and `--patch-dir PATH`
to use a different patch root.

## Manual setup

```bash
git clone --depth 1 --branch v9.6.0 https://github.com/lvgl/lvgl.git lvgl-src/9.6
cd lvgl-src/9.6
git apply ../../patches/9.6/0001-....patch   # only when patches/9.6/series exists
```

Do not commit the downloaded tree. Only this README belongs in Git.

## Local changes

Keep local changes to LVGL as patches, not as full source copies. See
[`patches/README.md`](../patches/README.md) for the patch layout, generation
commands and application rules. The default tree is the official release; any
local change is opt-in through `patches/<version>/`.
