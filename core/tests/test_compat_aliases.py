"""Compatibility import paths keep pointing at the renamed modules.

The naming cleanup moved the control layer to ``lvgl_ai.control`` and renamed
the web helpers, but old import paths must keep working: each legacy module is
a thin re-export of the new one, so callers and monkeypatches see the same
objects rather than a copy.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import lvgl_ai  # noqa: E402
import lvgl_ai.control as control  # noqa: E402
import lvgl_ai.control.errors as control_errors  # noqa: E402
import lvgl_ai.core as core  # noqa: E402
import lvgl_ai.png_codec as png_codec  # noqa: E402
import lvgl_ai.region as legacy_region  # noqa: E402
import lvgl_ai.web as web  # noqa: E402
import lvgl_ai.web.annotation_crops as annotation_crops  # noqa: E402
import lvgl_ai.web.page as legacy_page  # noqa: E402
import lvgl_ai.web.page_render as page_render  # noqa: E402
import lvgl_ai.web.region_images as legacy_region_images  # noqa: E402
import lvgl_ai.web.server as legacy_server  # noqa: E402
import lvgl_ai.web.stream as legacy_stream  # noqa: E402
import lvgl_ai.web.transport as transport  # noqa: E402
import lvgl_ai.web.webapp as webapp  # noqa: E402


class ControlAliasTest(unittest.TestCase):
    def test_lat_error_is_the_compatibility_alias_for_tool_error(self) -> None:
        self.assertIs(lvgl_ai.LatError, lvgl_ai.ToolError)
        self.assertIs(control_errors.LatError, control_errors.ToolError)

    def test_public_exports_are_unchanged(self) -> None:
        self.assertIn("LatError", lvgl_ai.__all__)
        self.assertNotIn("ToolError", lvgl_ai.__all__)
        self.assertIn("ToolError", control.__all__)
        self.assertIn("ToolError", core.__all__)

    def test_old_control_path_reexports_the_same_objects(self) -> None:
        self.assertIs(core.Runtime, control.Runtime)
        self.assertIs(core.Recording, control.Recording)
        self.assertIs(core.BuildError, control.BuildError)
        self.assertIs(core.errors.ToolError, control.errors.ToolError)

    def test_old_control_package_exposes_its_submodules(self) -> None:
        for name in (
            "build",
            "build_plan",
            "engine_link",
            "errors",
            "input",
            "keys",
            "recording",
            "retention",
            "runtime",
            "session",
            "session_schema",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(core, name))


class WebAliasTest(unittest.TestCase):
    def test_web_aliases_reexport_the_renamed_modules(self) -> None:
        self.assertIs(legacy_server.WebApp, webapp.WebApp)
        self.assertIs(legacy_server.create_server, webapp.create_server)
        self.assertIs(legacy_stream.LiveFrameHub, transport.LiveFrameHub)
        self.assertIs(legacy_stream.encode_frame, transport.encode_frame)
        self.assertIs(legacy_page.render_page, page_render.render_page)
        self.assertIs(
            legacy_region_images.prepare_region_images,
            annotation_crops.prepare_region_images,
        )

    def test_web_package_exports_are_unchanged(self) -> None:
        self.assertIs(web.WebApp, webapp.WebApp)
        self.assertEqual(web.LiveSession.__module__, "lvgl_ai.web.live_session")


class PngCodecAliasTest(unittest.TestCase):
    def test_region_reexports_the_png_codec(self) -> None:
        self.assertIs(legacy_region.PngError, png_codec.PngError)
        self.assertIs(legacy_region.Region, png_codec.Region)
        self.assertIs(legacy_region.crop_png, png_codec.crop_png)


if __name__ == "__main__":
    unittest.main()
