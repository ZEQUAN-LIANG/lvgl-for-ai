"""PNG crop tests; no engine or sessions."""

from __future__ import annotations

import unittest

from lvgl_ai.png_codec import (
    PngError,
    PngImage,
    Region,
    crop_png,
    decode_png,
    encode_png,
)


class PngCropTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = (
            bytes((255, 0, 0, 0, 255, 0, 0, 0, 255)),
            bytes((10, 20, 30, 40, 50, 60, 70, 80, 90)),
        )
        self.png = encode_png(PngImage(3, 2, 2, self.rows))

    def test_rgb_roundtrip_and_crop(self) -> None:
        image = decode_png(self.png)
        self.assertEqual((image.width, image.height, image.color_type), (3, 2, 2))
        self.assertEqual(image.rows, self.rows)

        cropped, box, _ = crop_png(self.png, Region(1, 0, 2, 2))
        self.assertEqual(box, Region(1, 0, 2, 2))
        self.assertEqual(
            decode_png(cropped).rows,
            (self.rows[0][3:9], self.rows[1][3:9]),
        )

    def test_clips_to_image_and_rejects_empty_intersection(self) -> None:
        cropped, box, _ = crop_png(self.png, Region(-5, -5, 10, 10))
        self.assertEqual(box, Region(0, 0, 3, 2))
        self.assertEqual(decode_png(cropped).rows, self.rows)
        with self.assertRaises(PngError):
            crop_png(self.png, Region(10, 10, 5, 5))

if __name__ == "__main__":
    unittest.main(verbosity=2)
