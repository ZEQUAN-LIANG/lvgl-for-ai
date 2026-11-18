from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
PERF_DIR = HOST_DIR / "perf"
for path in (HOST_DIR, PERF_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from perf_protocol import (  # noqa: E402
    PERF_BARS,
    PERF_MAX_LINE,
    PerfSample,
    demo_sample,
    encode,
    sanitize_host,
)


class PerfEncodeTest(unittest.TestCase):
    def test_full_frame(self) -> None:
        sample = PerfSample(
            seq=842,
            cpu=47,
            gpu=28,
            mem_mb=11500,
            mem_total_mb=32768,
            freq_mhz=3480,
            temp_c=64,
            gpu_temp_c=54,
            down_kib_s=12700,
            up_kib_s=800,
            ping_ms=15,
            hhmm=2051,
            host="DESKTOP-01",
            bars=list(range(PERF_BARS)),
        )
        line = encode(sample)
        self.assertTrue(line.startswith("PERF v=1 seq=842 cpu=47 gpu=28"))
        self.assertIn("mem=11500 memt=32768", line)
        self.assertIn("freq=3480 temp=64 gtemp=54", line)
        self.assertIn("down=12700 up=800 ping=15 time=2051", line)
        self.assertIn("host=DESKTOP-01", line)
        self.assertIn("th=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15", line)
        self.assertLessEqual(len(line), PERF_MAX_LINE)

    def test_minimal_frame_defaults(self) -> None:
        line = encode(PerfSample(seq=1, cpu=3))
        self.assertEqual(
            line,
            "PERF v=1 seq=1 cpu=3 down=0 up=0 th=0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
        )

    def test_host_is_sanitized_and_truncated(self) -> None:
        self.assertEqual(sanitize_host("DESK TOP@01"), "DESKTOP01")
        self.assertEqual(sanitize_host("a" * 30), "a" * 12)
        line = encode(PerfSample(seq=2, cpu=1, host="a b"))
        self.assertIn("host=ab", line)

    def test_bars_pad_and_truncate(self) -> None:
        padded = encode(PerfSample(seq=3, cpu=1, bars=[10, 20]))
        self.assertIn("th=10,20,0,0,0,0,0,0,0,0,0,0,0,0,0,0", padded)
        long_bars = list(range(40, 56))
        truncated = encode(PerfSample(seq=4, cpu=1, bars=long_bars))
        self.assertIn(
            "th=40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55", truncated
        )

    def test_thread_count_is_optional(self) -> None:
        line = encode(PerfSample(seq=1, cpu=1, bars=[10] * 8, thread_count=8))
        self.assertIn("thn=8", line)
        self.assertNotIn("thn=", encode(PerfSample(seq=1, cpu=1)))

    def test_invalid_values_raise(self) -> None:
        with self.assertRaises(ValueError):
            encode(PerfSample(seq=1, cpu=101))
        with self.assertRaises(ValueError):
            encode(PerfSample(seq=1, cpu=1, gpu=101))
        with self.assertRaises(ValueError):
            encode(PerfSample(seq=1, cpu=1, hhmm=2460))
        with self.assertRaises(ValueError):
            encode(PerfSample(seq=1, cpu=1, bars=[101] * PERF_BARS))
        with self.assertRaises(ValueError):
            encode(PerfSample(seq=1, cpu=1, thread_count=17))

    def test_demo_sample_is_valid(self) -> None:
        for tick in range(0, 120, 7):
            sample = demo_sample(tick, tick)
            line = encode(sample)
            self.assertLessEqual(len(line), PERF_MAX_LINE)
            self.assertGreaterEqual(sample.cpu, 0)
            self.assertLessEqual(sample.cpu, 100)
            self.assertEqual(len(sample.bars), PERF_BARS)


if __name__ == "__main__":
    unittest.main()
