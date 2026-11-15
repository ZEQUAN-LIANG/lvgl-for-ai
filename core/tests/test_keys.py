
from __future__ import annotations

import re
import unittest

from lvgl_ai import ScenarioError, paths
from lvgl_ai.control.keys import resolve_key

LV_GROUP_HEADER = (
    paths.LVGL_SRC_ROOT / "9.6" / "include" / "lvgl" / "core" / "lv_group.h"
)
KEY_ENUM_RE = re.compile(r"^\s*LV_KEY_([A-Z_]+)\s*=\s*(\d+)", re.MULTILINE)

REQUIRED_KEYS = {
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "ESC",
    "ENTER",
    "NEXT",
    "PREV",
    "HOME",
    "END",
    "DEL",
    "BACKSPACE",
}


def header_keys() -> dict[str, int]:
    if not LV_GROUP_HEADER.is_file():
        raise unittest.SkipTest(f"LVGL 9.6 headers not present: {LV_GROUP_HEADER}")
    matches = KEY_ENUM_RE.findall(LV_GROUP_HEADER.read_text(encoding="utf-8"))
    return {name: int(value) for name, value in matches}


class KeyMappingTest(unittest.TestCase):
    def test_every_lvgl_96_header_key_resolves_to_its_value(self) -> None:
        from_header = header_keys()
        self.assertEqual(len(from_header), 12)
        for name, code in from_header.items():
            with self.subTest(name=name):
                self.assertEqual(resolve_key(name), (name, code))

    def test_required_lv_key_names_are_covered(self) -> None:
        self.assertLessEqual(REQUIRED_KEYS, set(header_keys()))

    def test_every_key_resolves_with_and_without_the_lv_key_prefix(self) -> None:
        for name, code in header_keys().items():
            with self.subTest(name=name):
                self.assertEqual(resolve_key(name), (name, code))
                self.assertEqual(resolve_key(f"LV_KEY_{name}"), (name, code))
                self.assertEqual(resolve_key(name.lower()), (name, code))
                self.assertEqual(resolve_key(f"lv_key_{name.lower()}"), (name, code))

    def test_unknown_key_raises_scenario_error_with_the_name(self) -> None:
        for name in ("INSERT", "NOPE", "LV_KEY_NOPE"):
            with self.subTest(name=name):
                with self.assertRaises(ScenarioError) as caught:
                    resolve_key(name)
                self.assertIn(name, str(caught.exception))
                self.assertIsNone(caught.exception.step)

    def test_unknown_key_carries_the_step_index(self) -> None:
        with self.assertRaises(ScenarioError) as caught:
            resolve_key("INSERT", step=2)
        self.assertEqual(caught.exception.step, 2)
        self.assertIn("step 2", str(caught.exception))
        self.assertIn("INSERT", str(caught.exception))

    def test_non_string_key_is_rejected(self) -> None:
        with self.assertRaises(ScenarioError) as caught:
            resolve_key(7)
        self.assertIn("must be a string", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
