from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from lvgl_ai import paths

DRIVER = textwrap.dedent(
    r"""
    #include "frame_analysis.h"

    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    static int failures;

    static void check(const char * name, int condition)
    {
        if(!condition) {
            printf("FAIL: %s\n", name);
            failures++;
        }
    }

    static uint32_t next_random(uint32_t * state)
    {
        *state = *state * 1664525u + 1013904223u;
        return *state;
    }

    static void fill_pattern(uint8_t * pixels, uint32_t width, uint32_t height,
                             uint32_t seed)
    {
        size_t count = (size_t)width * height;
        uint32_t state = seed;
        for(size_t i = 0; i < count; i++) {
            uint32_t value = next_random(&state);
            pixels[i * 4u + 0u] = (uint8_t)(value & 0xFFu);
            pixels[i * 4u + 1u] = (uint8_t)((value >> 8) & 0xFFu);
            pixels[i * 4u + 2u] = (uint8_t)((value >> 16) & 0xFFu);
            pixels[i * 4u + 3u] = (uint8_t)((value >> 24) & 0xFFu);
        }
    }

    static void set_pixel(uint8_t * pixels, uint32_t width, uint32_t x,
                          uint32_t y, uint8_t r, uint8_t g, uint8_t b)
    {
        uint8_t * pixel = pixels + ((size_t)y * width + x) * 4u;
        pixel[0] = r;
        pixel[1] = g;
        pixel[2] = b;
        pixel[3] = 255u;
    }

    /* The pre-refactor implementation: one strict scan, then one stats scan. */
    static void reference_analysis(const uint8_t * previous,
                                   const uint8_t * current,
                                   uint32_t width,
                                   uint32_t height,
                                   int threshold,
                                   frame_analysis_t * out)
    {
        memset(out, 0, sizeof(*out));
        out->min_x = width;
        out->min_y = height;
        out->rgb_equal = true;

        size_t pixels = (size_t)width * height;
        for(size_t i = 0; i < pixels; i++) {
            const uint8_t * left = previous + i * 4u;
            const uint8_t * right = current + i * 4u;
            if(left[0] != right[0] || left[1] != right[1] ||
               left[2] != right[2]) {
                out->rgb_equal = false;
                break;
            }
        }
        for(size_t i = 0; i < pixels; i++) {
            const uint8_t * left = previous + i * 4u;
            const uint8_t * right = current + i * 4u;
            unsigned delta = 0;
            for(size_t channel = 0; channel < 3u; channel++) {
                int difference = (int)left[channel] - (int)right[channel];
                unsigned magnitude =
                    (unsigned)(difference < 0 ? -difference : difference);
                if(magnitude > delta) delta = magnitude;
            }
            if(delta > out->max_delta) out->max_delta = delta;
            if((int)delta > threshold) {
                uint32_t x = (uint32_t)(i % width);
                uint32_t y = (uint32_t)(i / width);
                out->changed_px++;
                if(x < out->min_x) out->min_x = x;
                if(y < out->min_y) out->min_y = y;
                if(x > out->max_x) out->max_x = x;
                if(y > out->max_y) out->max_y = y;
            }
        }
    }

    static void check_matches(const char * name,
                              const uint8_t * previous,
                              const uint8_t * current,
                              uint32_t width,
                              uint32_t height,
                              int threshold)
    {
        frame_analysis_t actual;
        frame_analysis_t expected;
        frame_analysis_compare(previous, current, width, height, threshold,
                               &actual);
        reference_analysis(previous, current, width, height, threshold,
                           &expected);
        check(name, actual.rgb_equal == expected.rgb_equal);
        check(name, actual.changed_px == expected.changed_px);
        check(name, actual.min_x == expected.min_x);
        check(name, actual.min_y == expected.min_y);
        check(name, actual.max_x == expected.max_x);
        check(name, actual.max_y == expected.max_y);
        check(name, actual.max_delta == expected.max_delta);
    }

    static void test_identical_frames(void)
    {
        enum { WIDTH = 7, HEIGHT = 5 };
        uint8_t previous[WIDTH * HEIGHT * 4];
        uint8_t current[WIDTH * HEIGHT * 4];
        fill_pattern(previous, WIDTH, HEIGHT, 1u);
        memcpy(current, previous, sizeof(previous));

        frame_analysis_t result;
        frame_analysis_compare(previous, current, WIDTH, HEIGHT, 10, &result);
        check("identical rgb_equal", result.rgb_equal == true);
        check("identical changed_px", result.changed_px == 0);
        check("identical max_delta", result.max_delta == 0);
        check("identical bbox init",
              result.min_x == WIDTH && result.min_y == HEIGHT &&
              result.max_x == 0 && result.max_y == 0);
    }

    static void test_alpha_is_ignored(void)
    {
        enum { WIDTH = 6, HEIGHT = 4 };
        uint8_t previous[WIDTH * HEIGHT * 4];
        uint8_t current[WIDTH * HEIGHT * 4];
        fill_pattern(previous, WIDTH, HEIGHT, 2u);
        memcpy(current, previous, sizeof(previous));
        for(size_t i = 0; i < WIDTH * HEIGHT; i++) {
            current[i * 4u + 3u] = (uint8_t)(previous[i * 4u + 3u] ^ 0x7Fu);
        }

        frame_analysis_t result;
        frame_analysis_compare(previous, current, WIDTH, HEIGHT, 10, &result);
        check("alpha rgb_equal", result.rgb_equal == true);
        check("alpha changed_px", result.changed_px == 0);
        check("alpha max_delta", result.max_delta == 0);
    }

    static void test_threshold_boundary(void)
    {
        enum { WIDTH = 4, HEIGHT = 3 };
        uint8_t previous[WIDTH * HEIGHT * 4];
        uint8_t current[WIDTH * HEIGHT * 4];
        memset(previous, 0, sizeof(previous));
        memset(current, 0, sizeof(current));
        for(size_t i = 0; i < WIDTH * HEIGHT; i++) {
            previous[i * 4u + 3u] = 255u;
            current[i * 4u + 3u] = 255u;
        }
        set_pixel(current, WIDTH, 2, 1, 10, 0, 0);

        frame_analysis_t result;
        frame_analysis_compare(previous, current, WIDTH, HEIGHT, 10, &result);
        check("boundary rgb_equal", result.rgb_equal == false);
        check("boundary equal to threshold is not changed",
              result.changed_px == 0);
        check("boundary max_delta", result.max_delta == 10);

        frame_analysis_compare(previous, current, WIDTH, HEIGHT, 9, &result);
        check("boundary above threshold is changed", result.changed_px == 1);
        check("boundary bbox x", result.min_x == 2 && result.max_x == 2);
        check("boundary bbox y", result.min_y == 1 && result.max_y == 1);
    }

    static void test_bbox_union(void)
    {
        enum { WIDTH = 8, HEIGHT = 6 };
        uint8_t previous[WIDTH * HEIGHT * 4];
        uint8_t current[WIDTH * HEIGHT * 4];
        memset(previous, 0, sizeof(previous));
        memset(current, 0, sizeof(current));
        set_pixel(current, WIDTH, 1, 1, 20, 0, 0);
        set_pixel(current, WIDTH, 6, 4, 0, 30, 0);
        set_pixel(current, WIDTH, 2, 5, 0, 0, 11);

        frame_analysis_t result;
        frame_analysis_compare(previous, current, WIDTH, HEIGHT, 10, &result);
        check("union changed_px", result.changed_px == 3);
        check("union bbox",
              result.min_x == 1 && result.min_y == 1 &&
              result.max_x == 6 && result.max_y == 5);
        check("union max_delta", result.max_delta == 30);
    }

    static void test_random_equivalence(void)
    {
        enum { WIDTH = 31, HEIGHT = 17 };
        uint8_t previous[WIDTH * HEIGHT * 4];
        uint8_t current[WIDTH * HEIGHT * 4];
        const int thresholds[] = {0, 10, 255};

        for(uint32_t seed = 1u; seed <= 20u; seed++) {
            fill_pattern(previous, WIDTH, HEIGHT, seed);
            memcpy(current, previous, sizeof(previous));
            uint32_t state = seed * 7919u;
            for(int mutation = 0; mutation < 40; mutation++) {
                uint32_t pixel =
                    next_random(&state) % (WIDTH * HEIGHT);
                uint32_t channel = next_random(&state) % 3u;
                current[pixel * 4u + channel] =
                    (uint8_t)(current[pixel * 4u + channel] ^
                              (uint8_t)(1u + (next_random(&state) % 255u)));
                /* Alpha changes must not influence either definition. */
                current[pixel * 4u + 3u] =
                    (uint8_t)(current[pixel * 4u + 3u] ^ 0x5Au);
            }
            for(size_t i = 0; i < sizeof(thresholds) / sizeof(thresholds[0]);
                i++) {
                check_matches("random equivalence", previous, current, WIDTH,
                              HEIGHT, thresholds[i]);
            }
        }
    }

    int main(void)
    {
        test_identical_frames();
        test_alpha_is_ignored();
        test_threshold_boundary();
        test_bbox_union();
        test_random_equivalence();
        if(failures != 0) {
            printf("%d frame_analysis checks failed\n", failures);
            return 1;
        }
        printf("ok: frame_analysis matches strict equality and threshold stats\n");
        return 0;
    }
    """
)


class FrameAnalysisSeamTest(unittest.TestCase):
    def test_single_traversal_matches_both_definitions(self) -> None:
        compiler = shutil.which("gcc")
        if compiler is None:
            self.skipTest("gcc is not available")

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            driver = work / "frame_analysis_driver.c"
            driver.write_text(DRIVER, encoding="utf-8")
            executable = work / "frame_analysis_driver"
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-I",
                    str(paths.ENGINE_DIR),
                    str(paths.ENGINE_DIR / "frame_analysis.c"),
                    str(driver),
                    "-o",
                    str(executable),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                compile_result.returncode,
                0,
                compile_result.stdout + compile_result.stderr,
            )

            run_result = subprocess.run(
                [str(executable)], capture_output=True, text=True
            )
            self.assertEqual(
                run_result.returncode,
                0,
                run_result.stdout + run_result.stderr,
            )
            self.assertIn("ok: frame_analysis", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
