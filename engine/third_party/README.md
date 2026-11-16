# Third-party sources

The engine links three third-party components:

- `freetype/`: FreeType 2.13.2 headers, MinGW import library and runtime DLL
  (`libfreetype.dll`). Committed, because Windows builds need the pinned import
  library; license text is in `docs/licenses/FreeType.txt`.
- `zlib/`: zlib 1.3.1 (`v1.3.1`, commit `51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf`)
- `libpng/`: libpng 1.6.44 (`v1.6.44`, commit `f5e92d76973a7a53f517579bc95d61483bf108c0`)

zlib and libpng are fetched on demand and are not committed:

```bash
python -I scripts/fetch_png.py --repo-root .
```

The fetch script clones each tag into `.scratch/tmp/`, verifies the commit and
the version header, and copies the verified tree here. It never builds or runs
the downloaded content. Builds use this directory.

License texts are committed under `docs/licenses/`.
