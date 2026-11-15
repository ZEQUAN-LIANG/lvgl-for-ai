from __future__ import annotations

from collections import deque


class RingBuffer:
    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        self.next_seq = 0
        self.first_seq = 0
        self.buffered = 0
        self._chunks: deque[tuple[int, bytes]] = deque()

    def append(self, data: bytes) -> None:
        payload = bytes(data)
        start = self.next_seq
        self._chunks.append((start, payload))
        self.next_seq += len(payload)
        self.buffered += len(payload)

        while self.buffered > self.capacity and self._chunks:
            overflow = self.buffered - self.capacity
            chunk_start, chunk = self._chunks[0]
            if len(chunk) <= overflow:
                self._chunks.popleft()
                self.buffered -= len(chunk)
                continue
            self._chunks[0] = (chunk_start + overflow, chunk[overflow:])
            self.buffered -= overflow
            break

        self.first_seq = self._chunks[0][0] if self._chunks else self.next_seq

    def read(self, since: int, limit: int) -> dict:
        requested = int(since)
        start = requested
        truncated = False
        if start < self.first_seq:
            start = self.first_seq
            truncated = True
        if start > self.next_seq:
            start = self.next_seq

        pieces: list[bytes] = []
        remaining = max(1, int(limit))
        cursor = start
        for chunk_start, chunk in self._chunks:
            chunk_end = chunk_start + len(chunk)
            if chunk_end <= cursor:
                continue
            offset = max(0, cursor - chunk_start)
            piece = chunk[offset : offset + remaining]
            if not piece:
                continue
            pieces.append(piece)
            remaining -= len(piece)
            cursor += len(piece)
            if remaining <= 0:
                break

        data = b"".join(pieces)
        return {
            "since": requested,
            "next": start + len(data),
            "first_seq": self.first_seq,
            "next_seq": self.next_seq,
            "truncated": truncated,
            "data": data,
        }
