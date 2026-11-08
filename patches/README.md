# LVGL patches

Local changes to LVGL are kept here as patches. The repository does not commit
`lvgl-src/`; users download the official release and this directory supplies
the additions.

## Contract

`patches/` is the single patch root. In the development checkout it sits at the
repository root; in the distribution package it sits at the package root
(`<package>/patches/`). `fetch_lvgl.py` defaults to `<repo-root>/patches`, and
`--patch-dir PATH` overrides it. A directory containing only this README is a
valid state: it means the official tree is used unmodified.

## Layout

```text
patches/
├── README.md
├── 9.6/
│   ├── series
│   ├── 0001-indev-expose-probe.patch
│   └── 0002-xxx.patch
└── 8.4/
    ├── series
    └── 0001-xxx.patch
```

`series` lists patch file names in application order, one per line. Blank lines
and lines starting with `#` are ignored. When `series` is absent, every
`*.patch` file in the version directory is applied in lexical order.

Patch paths use `a/...` and `b/...`, so they apply from the LVGL source root
with `git apply -p1`.

## Applying

Recommended, through the download script:

```bash
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .
```

The script verifies the official tag, applies `patches/9.6/series`, then
installs the tree under `lvgl-src/9.6/`. Use `--no-patch` to skip patches or
`--patch-dir PATH` to point at another patch root.

Manual:

```bash
git clone --depth 1 --branch v9.6.0 https://github.com/lvgl/lvgl.git lvgl-src/9.6
cd lvgl-src/9.6
git apply ../../patches/9.6/0001-xxx.patch
```

## Creating a patch

Use a pristine official tree as the base:

```bash
git clone --depth 1 --branch v9.6.0 https://github.com/lvgl/lvgl.git /tmp/lvgl-9.6
cd /tmp/lvgl-9.6
git add -A
git commit -m "upstream v9.6.0"

# Copy only the files you changed over the pristine tree.
# Do not copy a .git directory: it would replace the clone's repository.
cp /path/to/lvgl-src/9.6/src/indev/lv_indev.c src/indev/lv_indev.c

# Include new files, then emit the patch.
git add -N .
git diff > /path/to/patches/9.6/0001-your-change.patch
```

Split unrelated changes into separate patches. Then add the file name to
`patches/9.6/series`. Reset the temporary tree to the pristine baseline before
checking the patch (the copied files are already captured in the diff):

```bash
cd /tmp/lvgl-9.6
git reset --hard HEAD
git apply --check /path/to/patches/9.6/0001-your-change.patch
```

## Rules

- Patches are tied to the exact tag pinned in `core/tools/fetch_lvgl.py`.
  Regenerate them when the LVGL version changes.
- Keep each patch small and explain why it exists in the patch header or a
  sibling README.
- Use LF line endings; `git apply` is sensitive to CRLF. When generating on
  Windows, set `git config core.autocrlf false` first.
- Prefer text patches. If a binary file must change, generate the patch with
  `git diff --binary`.
- Upstream the change when possible; a patch is maintenance debt.
- The current repository has no LVGL patches. Official releases are used
  unmodified.
