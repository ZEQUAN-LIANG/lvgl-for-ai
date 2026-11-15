from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from ring_buffer import RingBuffer


class RingBufferTest(unittest.TestCase):
    def test_read_from_cursor(self) -> None:
        ring = RingBuffer(16)
        ring.append(b"hello")
        self.assertEqual(ring.next_seq, 5)
        chunk = ring.read(0, 1024)
        self.assertEqual(chunk["data"], b"hello")
        self.assertEqual(chunk["next"], 5)
        self.assertFalse(chunk["truncated"])
        self.assertEqual(ring.read(2, 1024)["data"], b"llo")
        empty = ring.read(99, 1024)
        self.assertEqual(empty["data"], b"")
        self.assertEqual(empty["next"], 5)

    def test_limit_splits_chunks(self) -> None:
        ring = RingBuffer(16)
        ring.append(b"abc")
        ring.append(b"def")
        first = ring.read(0, 4)
        self.assertEqual(first["data"], b"abcd")
        self.assertEqual(first["next"], 4)
        second = ring.read(first["next"], 4)
        self.assertEqual(second["data"], b"ef")
        self.assertEqual(second["next"], 6)

    def test_oversized_chunk_keeps_tail(self) -> None:
        ring = RingBuffer(4)
        ring.append(b"abcdefgh")
        chunk = ring.read(0, 1024)
        self.assertTrue(chunk["truncated"])
        self.assertEqual(chunk["data"], b"efgh")
        self.assertEqual(chunk["first_seq"], 4)
        self.assertEqual(ring.buffered, 4)

    def test_zero_capacity_drops_all(self) -> None:
        ring = RingBuffer(0)
        ring.append(b"x")
        self.assertEqual(ring.buffered, 0)
        self.assertEqual(ring.first_seq, 1)
        chunk = ring.read(0, 10)
        self.assertTrue(chunk["truncated"])
        self.assertEqual(chunk["data"], b"")

    def test_capacity_enforced_across_chunks(self) -> None:
        ring = RingBuffer(5)
        ring.append(b"aaa")
        ring.append(b"bbb")
        self.assertEqual(ring.buffered, 5)
        self.assertEqual(ring.read(0, 100)["data"], b"aabbb")
        self.assertEqual(ring.first_seq, 1)


if __name__ == "__main__":
    unittest.main()
