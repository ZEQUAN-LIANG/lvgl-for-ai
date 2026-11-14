# Vendored asset-conversion dependencies

This directory is copied into the released skill package by `core/tools/release.py`.
The converter imports these modules lazily; the LVGL runtime/engine does not use them.

## freetype-py 2.5.1 (win_amd64)

- Upstream: <https://github.com/rougier/freetype-py>
- License: new/revised BSD (`licenses/freetype-py.txt`)
- Wheel: `freetype_py-2.5.1-py3-none-win_amd64.whl`
- Wheel SHA-256: `0b7f8e0342779f65ca13ef8bc103938366fecade23e6bb37cb671c2b8ad7f124`
- The wheel bundles FreeType 2.13.2 as `freetype/libfreetype.dll`
- DLL SHA-256: `090038852d6eb0dc75569f31fb92d6c98e829ca2639c9b6e8d8808032f9a7003`
- FreeType license: FTL (`licenses/FreeType.txt`)
- Only the `freetype/` Python package and its DLL are vendored; tests and
  metadata are not copied.

## pypng 0.20220715.0

- Upstream: <https://gitlab.com/drj11/pypng>
- License: MIT (`licenses/pypng.txt`)
- Wheel: `pypng-0.20220715.0-py3-none-any.whl`
- Wheel SHA-256: `4a43e969b8f5aaafb2a415536c1a8ec7e341cd6a3f957fd5b5f32a4cfeed902c`
- Only `png.py` is vendored (`png.py` SHA-256:
  `b1c6211078af892bbe975f948d40e19f2e9ec064994f635b6e431b5c55e56830`).

## Updating

1. Download the pinned wheels and verify the SHA-256 against PyPI.
2. Replace `freetype/` and `png.py`; do not copy `__pycache__`.
3. Update the hashes and versions above.
4. Run `python -I core/tests/run_tests.py` and the release integration test.

The font emitter's bitmap/cmap layout is modelled after `lv_font_conv` 1.5.3
(MIT, <https://github.com/lvgl/lv_font_conv>); see `licenses/lv_font_conv-MIT.txt`.
`lv_font_conv` itself is not distributed with this package.
