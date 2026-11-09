# Third-party PNG sources

The engine writes PNG evidence with libpng + zlib instead of LVGL's bundled
lodepng. The pinned source trees are fetched on demand; they are not committed:

```bash
python -I core/tools/fetch_png.py --repo-root .
```

- `zlib/`: zlib 1.3.1 (`v1.3.1`, commit `51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf`)
- `libpng/`: libpng 1.6.44 (`v1.6.44`, commit `f5e92d76973a7a53f517579bc95d61483bf108c0`)

The fetch script clones each tag into `.scratch/tmp/`, verifies the commit and
the version header, and copies the verified tree here. It never builds or runs
the downloaded content. Builds use this directory.

License texts are committed under `licenses/zlib.txt` and `licenses/libpng.txt`.
