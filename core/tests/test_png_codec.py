"""PNG crop tests; no engine or sessions."""

from __future__ import annotations

import struct
import unittest
import zlib

from lvgl_ai.png_codec import (
    MAX_CONTACT_TILES,
    PNG_SIGNATURE,
    PngError,
    PngImage,
    Region,
    build_contact_sheet,
    compare_png,
    crop_png,
    decode_png,
    encode_png,
    read_pixel,
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


class PngPixelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = (
            bytes((1, 2, 3, 4, 5, 6)),
            bytes((7, 8, 9, 10, 11, 12)),
        )
        self.png = encode_png(PngImage(2, 2, 2, self.rows))

    def test_reads_the_rgb_value_at_a_pixel(self) -> None:
        self.assertEqual(read_pixel(self.png, 0, 0), (1, 2, 3))
        self.assertEqual(read_pixel(self.png, 1, 0), (4, 5, 6))
        self.assertEqual(read_pixel(self.png, 1, 1), (10, 11, 12))

    def test_rejects_coordinates_outside_the_image(self) -> None:
        for x, y in ((2, 0), (0, 2), (-1, 0)):
            with self.subTest(x=x, y=y):
                with self.assertRaises(PngError):
                    read_pixel(self.png, x, y)


class CompareImagesTest(unittest.TestCase):
    def test_identical_images_report_no_change(self) -> None:
        png = _rgb_png(2, 2, [(1, 2, 3)] * 4)

        comparison = compare_png(png, png)

        self.assertEqual((comparison.width, comparison.height), (2, 2))
        self.assertIsNone(comparison.bbox)
        self.assertEqual(comparison.changed_px, 0)
        self.assertEqual(comparison.changed_ratio, 0.0)
        self.assertEqual(comparison.max_delta, 0.0)
        self.assertIsNone(comparison.heatmap)

    def test_single_pixel_difference_reports_its_bbox_and_delta(self) -> None:
        left = _rgb_png(4, 4, [(0, 0, 0)] * 16)
        right_pixels = [(0, 0, 0)] * 16
        right_pixels[2 * 4 + 1] = (10, 20, 30)

        comparison = compare_png(left, _rgb_png(4, 4, right_pixels))

        self.assertEqual(comparison.bbox, Region(1, 2, 1, 1))
        self.assertEqual(comparison.changed_px, 1)
        self.assertEqual(comparison.changed_ratio, 1 / 16)
        self.assertAlmostEqual(comparison.max_delta, 30 / 255)

    def test_rectangle_difference_reports_the_union_bbox(self) -> None:
        left = _rgb_png(4, 4, [(0, 0, 0)] * 16)
        right_pixels = [(0, 0, 0)] * 16
        for y in (1, 2):
            for x in (1, 2):
                right_pixels[y * 4 + x] = (255, 0, 0)

        comparison = compare_png(left, _rgb_png(4, 4, right_pixels))

        self.assertEqual(comparison.bbox, Region(1, 1, 2, 2))
        self.assertEqual(comparison.changed_px, 4)
        self.assertEqual(comparison.changed_ratio, 0.25)
        self.assertEqual(comparison.max_delta, 1.0)

    def test_different_sizes_are_an_error_instead_of_silent_alignment(
        self,
    ) -> None:
        left = _solid_png((1, 2, 3), size=4)
        right = _solid_png((1, 2, 3), size=3)

        with self.assertRaises(PngError) as caught:
            compare_png(left, right)

        message = str(caught.exception)
        self.assertIn("4x4", message)
        self.assertIn("3x3", message)
        self.assertIn("identical", message)

    def test_rejects_an_oversized_image_before_decoding(self) -> None:
        header_only = _png_with_header(9000, 9000)

        with self.assertRaises(PngError) as caught:
            compare_png(header_only, header_only)

        message = str(caught.exception)
        self.assertIn("compare", message)
        self.assertIn("crop", message)

    def test_heatmap_marks_changed_pixels_by_delta(self) -> None:
        left = _rgb_png(3, 1, [(0, 0, 0)] * 3)
        right = _rgb_png(
            3, 1, [(255, 0, 0), (10, 0, 0), (0, 0, 0)]
        )

        comparison = compare_png(left, right, heatmap=True)

        self.assertIsNotNone(comparison.heatmap)
        heatmap_png = comparison.to_png()
        self.assertEqual(
            (comparison.heatmap.width, comparison.heatmap.height),
            (3, 1),
        )
        self.assertEqual(read_pixel(heatmap_png, 0, 0), (255, 0, 0))
        self.assertEqual(read_pixel(heatmap_png, 1, 0), (255, 245, 0))
        self.assertEqual(read_pixel(heatmap_png, 2, 0), (24, 24, 24))


def _solid_png(rgb: tuple[int, int, int], size: int = 8) -> bytes:
    return encode_png(
        PngImage(size, size, 2, (bytes(rgb) * size,) * size)
    )


def _rgb_png(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int]],
) -> bytes:
    rows = tuple(
        b"".join(
            bytes(pixel)
            for pixel in pixels[y * width:(y + 1) * width]
        )
        for y in range(height)
    )
    return encode_png(PngImage(width, height, 2, rows))


def _png_with_header(width: int, height: int) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + chunk_type
            + payload
            + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", ihdr)
        + chunk(b"IEND", b"")
    )


class ContactSheetTest(unittest.TestCase):
    def test_keeps_input_order_labels_and_tile_geometry(self) -> None:
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        items = [
            ("first", _solid_png(colors[0])),
            ("second", _solid_png(colors[1])),
            ("third", _solid_png(colors[2])),
        ]

        sheet = build_contact_sheet(
            items, columns=2, tile_width=64, tile_height=48
        )

        self.assertEqual([tile.label for tile in sheet.tiles], [
            "first", "second", "third"
        ])
        self.assertEqual((sheet.columns, sheet.rows), (2, 2))
        self.assertEqual(len(sheet.tiles), 3)
        self.assertEqual((sheet.image.width, sheet.image.height), (152, 120))
        self.assertEqual(
            [(tile.x, tile.y, tile.width, tile.height) for tile in sheet.tiles],
            [(8, 8, 64, 48), (80, 8, 64, 48), (8, 64, 64, 48)],
        )
        png = sheet.to_png()
        for tile, color in zip(sheet.tiles, colors):
            x = tile.image_x + tile.image_width // 2
            y = tile.image_y + tile.image_height // 2
            self.assertEqual(read_pixel(png, x, y), color)

    def test_draws_the_label_text_into_the_tile(self) -> None:
        image = _solid_png((10, 20, 30))
        with_label_a = build_contact_sheet(
            [("A", image)], columns=1, tile_width=64, tile_height=48
        )
        with_label_b = build_contact_sheet(
            [("B", image)], columns=1, tile_width=64, tile_height=48
        )

        self.assertNotEqual(
            with_label_a.image.rows, with_label_b.image.rows
        )
        tile = with_label_a.tiles[0]
        label_rows = with_label_a.image.rows[
            tile.y:tile.image_y
        ]
        white = sum(
            1
            for row in label_rows
            for index in range(0, len(row), 3)
            if tuple(row[index:index + 3]) == (255, 255, 255)
        )
        self.assertGreater(white, 0)

    def test_rejects_empty_or_too_many_tiles(self) -> None:
        png = _solid_png((1, 2, 3))
        with self.assertRaises(PngError):
            build_contact_sheet([])
        with self.assertRaises(PngError) as caught:
            build_contact_sheet(
                [("tile", png)] * (MAX_CONTACT_TILES + 1)
            )
        self.assertIn(str(MAX_CONTACT_TILES), str(caught.exception))

    def test_rejects_an_oversized_source_before_decoding(self) -> None:
        with self.assertRaises(PngError) as caught:
            build_contact_sheet([("huge", _png_with_header(9000, 9000))])

        message = str(caught.exception)
        self.assertIn("contact-sheet", message)
        self.assertIn("crop", message)

    def test_rejects_a_sheet_over_the_size_budget(self) -> None:
        png = _solid_png((1, 2, 3), size=2)
        with self.assertRaises(PngError) as caught:
            build_contact_sheet(
                [("tile", png)] * MAX_CONTACT_TILES,
                columns=8,
                tile_width=480,
                tile_height=360,
            )

        message = str(caught.exception)
        self.assertIn("contact sheet", message)
        self.assertIn("reduce", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
