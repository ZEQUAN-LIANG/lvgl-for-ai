import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import layout


class LayoutTest(unittest.TestCase):
    def test_zones_live_under_chip_adapt(self):
        self.assertEqual(layout.ADAPTER_DIR, HERE)
        self.assertEqual(layout.CHIP_ADAPT_DIR, HERE.parent)
        self.assertEqual(layout.VENDOR_DIR, HERE.parent / "vendor")
        self.assertEqual(layout.SDK_DIR, HERE.parent / "vendor" / "sifli-sdk")
        self.assertEqual(layout.EXPORTS_DIR, HERE.parent / "exports")

    def test_adapter_manifest_keeps_paths_out(self):
        payload = json.loads((HERE / "adapter.json").read_text(encoding="utf-8"))
        for key in ("sdk_path", "ezip", "vendor_root", "exports_root"):
            self.assertNotIn(key, payload)


if __name__ == "__main__":
    unittest.main()
