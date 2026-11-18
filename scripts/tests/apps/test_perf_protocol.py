from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "user" / "app" / "perf_monitor"
HOST_DIR = REPO_ROOT / "chip-adapt" / "esp32" / "host"

if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from perf_protocol import PerfSample, encode  # noqa: E402

HARNESS = r"""
#include "perf_protocol.h"

#include <stdio.h>
#include <string.h>

int main(void)
{
    char line[512];

    while(fgets(line, sizeof(line), stdin) != NULL) {
        size_t len = strlen(line);
        while(len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) {
            line[--len] = '\0';
        }

        perf_sample_t sample;
        perf_parse_result_t result = perf_protocol_parse(line, len, &sample);

        printf("%s|%u|%u|%u|%u|%u|%u|%d|%d|%u|%u|%u|%u|%s|",
               perf_parse_result_name(result), (unsigned)sample.seq,
               (unsigned)sample.cpu, (unsigned)sample.gpu,
               (unsigned)sample.mem_mb, (unsigned)sample.mem_total_mb,
               (unsigned)sample.freq_mhz, (int)sample.temp_c,
               (int)sample.gpu_temp_c, (unsigned)sample.down_kib_s,
               (unsigned)sample.up_kib_s, (unsigned)sample.ping_ms,
               (unsigned)sample.hhmm, sample.host);
        for(int i = 0; i < PERF_PROTOCOL_BARS; i++) {
            printf("%s%u", i == 0 ? "" : ",", (unsigned)sample.bars[i]);
        }
        printf("|%u\n", (unsigned)sample.thread_count);
        fflush(stdout);
    }

    return 0;
}
"""


def _find_gcc() -> str | None:
    configured = os.environ.get("LVGL_VERIFY_LOOP_GCC")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
    return shutil.which("gcc")


@unittest.skipUnless(_find_gcc(), "gcc is required to compile the parser test")
class PerfProtocolCTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        harness = tmp / "perf_protocol_harness.c"
        harness.write_text(HARNESS, encoding="utf-8")
        executable = tmp / (
            "perf_protocol_test.exe"
            if os.name == "nt"
            else "perf_protocol_test"
        )
        gcc = _find_gcc()
        assert gcc is not None
        completed = subprocess.run(
            [
                gcc,
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(APP_DIR),
                str(harness),
                str(APP_DIR / "perf_protocol.c"),
                "-o",
                str(executable),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"parser harness compile failed:\n{completed.stdout}\n{completed.stderr}"
            )
        cls.executable = executable

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_lines(self, lines: list[str]) -> list[list[str]]:
        payload = "\n".join(lines) + "\n"
        completed = subprocess.run(
            [str(self.executable)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return [line.split("|") for line in completed.stdout.splitlines()]

    def test_full_frame(self) -> None:
        lines = self.run_lines(
            [
                "PERF v=1 seq=842 cpu=47 gpu=28 mem=11500 memt=32768 "
                "freq=3480 temp=64 gtemp=54 down=12700 up=800 ping=15 "
                "time=2051 host=DESKTOP-01 th=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"
            ]
        )
        parts = lines[0]
        self.assertEqual(parts[0], "ok")
        self.assertEqual(
            parts[1:14],
            [
                "842",
                "47",
                "28",
                "11500",
                "32768",
                "3480",
                "64",
                "54",
                "12700",
                "800",
                "15",
                "2051",
                "DESKTOP-01",
            ],
        )
        self.assertEqual(parts[14], "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15")
        self.assertEqual(parts[15], "16")

    def test_minimal_frame_defaults(self) -> None:
        parts = self.run_lines(["PERF v=1 seq=1 cpu=3"])[0]
        self.assertEqual(parts[0], "ok")
        self.assertEqual(parts[1], "1")
        self.assertEqual(parts[2], "3")
        self.assertEqual(parts[3], "255")
        self.assertEqual(parts[7], "-32768")
        self.assertEqual(parts[8], "-32768")
        self.assertEqual(parts[11], "65535")
        self.assertEqual(parts[12], "65535")
        self.assertEqual(parts[13], "DESKTOP")
        self.assertEqual(parts[14], "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
        self.assertEqual(parts[15], "16")

    def test_thread_count(self) -> None:
        parts = self.run_lines(
            ["PERF v=1 seq=8 cpu=12 thn=8 th=10,20,30,40,50,60,70,80"]
        )[0]
        self.assertEqual(parts[0], "ok")
        self.assertEqual(parts[13], "DESKTOP")
        self.assertEqual(parts[14], "10,20,30,40,50,60,70,80,0,0,0,0,0,0,0,0")
        self.assertEqual(parts[15], "8")

    def test_bad_thread_count(self) -> None:
        results = self.run_lines(
            ["PERF v=1 seq=1 cpu=3 thn=0", "PERF v=1 seq=1 cpu=3 thn=17"]
        )
        self.assertEqual(
            [row[0] for row in results], ["bad-value", "bad-value"]
        )

    def test_python_encoder_matches_c_parser(self) -> None:
        sample = PerfSample(
            seq=77,
            cpu=63,
            gpu=41,
            mem_mb=12000,
            mem_total_mb=32768,
            freq_mhz=4100,
            temp_c=70,
            gpu_temp_c=61,
            down_kib_s=2048,
            up_kib_s=512,
            ping_ms=9,
            hhmm=2317,
            host="DESKTOP-7F",
            bars=list(range(16)),
        )
        parts = self.run_lines([encode(sample)])[0]
        self.assertEqual(parts[0], "ok")
        self.assertEqual(parts[1:6], ["77", "63", "41", "12000", "32768"])
        self.assertEqual(parts[6:9], ["4100", "70", "61"])
        self.assertEqual(parts[9:13], ["2048", "512", "9", "2317"])
        self.assertEqual(parts[13], "DESKTOP-7F")
        self.assertEqual(parts[14], "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15")
        self.assertEqual(parts[15], "16")

    def test_commands(self) -> None:
        results = self.run_lines(
            [
                "PERF HELLO",
                "PERF PING",
                "PERF DEMO",
                "PERF LIVE",
                "PERF PORTRAIT",
                "PERF LANDSCAPE",
            ]
        )
        self.assertEqual(
            [row[0] for row in results],
            ["hello", "ping", "demo", "live", "portrait", "landscape"],
        )

    def test_errors(self) -> None:
        results = self.run_lines(
            [
                "pages",
                "",
                "PERF v=2 seq=1 cpu=3",
                "PERF v=1 seq=1 cpu=101",
                "PERF v=1 seq=1",
                "PERF v=1 seq=1 cpu=3 time=2460",
                "PERF v=1 seq=1 cpu=3 th=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17",
                "PERF v=1 seq=1 cpu=3 th=101",
                "PERF v=1 seq=1 cpu=3 host=DESKTOP@01",
                "PERF v=1 seq=1 cpu=3 " + "x" * 400,
            ]
        )
        self.assertEqual(results[0][0], "not-perf")
        self.assertEqual(results[1][0], "empty")
        self.assertEqual(results[2][0], "bad-version")
        self.assertEqual(results[3][0], "bad-value")
        self.assertEqual(results[4][0], "missing-field")
        self.assertEqual(results[5][0], "bad-value")
        self.assertEqual(results[6][0], "bad-value")
        self.assertEqual(results[7][0], "bad-value")
        self.assertEqual(results[8][0], "ok")
        self.assertEqual(results[8][13], "DESKTOP")
        self.assertEqual(results[9][0], "too-long")

    def test_partial_bars_and_unknown_keys(self) -> None:
        parts = self.run_lines(["PERF v=1 seq=5 cpu=9 th=7,8,9 foo=bar"])[0]
        self.assertEqual(parts[0], "ok")
        self.assertEqual(parts[14], "7,8,9,0,0,0,0,0,0,0,0,0,0,0,0,0")


if __name__ == "__main__":
    unittest.main()
