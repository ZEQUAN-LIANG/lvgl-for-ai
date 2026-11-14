# FreeType for the LVGL engine (Windows x64)

The engine enables LVGL's `LV_USE_FREETYPE` by default. This directory carries
the C headers and the MinGW import library used to link it. The DLL itself is
shared with the asset converter, so the skill keeps one copy:

```
core/lvgl_ai/assets/vendor/freetype/libfreetype.dll
```

| File | Version | SHA256 |
| --- | --- | --- |
| `include/` | FreeType 2.13.2 | upstream `VER-2-13-2` headers |
| `lib/libfreetype.dll.a` | generated from the DLL below | `20a29cb7bad545fba9ed2eb870ad911fa022a50712d081f935652408777ebd4c` |
| `../lvgl_ai/assets/vendor/freetype/libfreetype.dll` | FreeType 2.13.2 (freetype-py 2.5.1 wheel) | `090038852d6eb0dc75569f31fb92d6c98e829ca2639c9b6e8d8808032f9a7003` |

The DLL imports only `KERNEL32.dll`, `VCRUNTIME140*.dll` and the Universal CRT;
it has no libpng/zlib/bzip2 dependency. The import library was generated with:

```bat
gendef libfreetype.dll > libfreetype.def
dlltool -d libfreetype.def -l libfreetype.dll.a -D libfreetype.dll
```

`LV_USE_FREETYPE` is defined in `core/engine/lv_conf.h` for both 8.x and 9.x.
CMake links `libfreetype.dll.a` into the LVGL target and copies
`libfreetype.dll` next to `lvgl_engine.exe`, because Windows resolves DLLs from
the executable directory.

Headers come from <https://github.com/freetype/freetype/releases/tag/VER-2-13-2>;
the DLL comes from the pinned freetype-py wheel documented in
`core/lvgl_ai/assets/vendor/README.md`. License: FreeType License (FTL), see
`licenses/FreeType.txt`.
