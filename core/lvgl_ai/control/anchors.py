"""Stable feedback anchors and the row-order resolver.

An input command only queues work inside LVGL; frames are recorded by
``tick`` / ``wait``. A frame's ``t_ms`` is therefore not a reliable lookup key.
Resolution walks ``timeline.ndjson`` in row order instead: the picture before
an event is the last evidence row at or before it, and the result is the first
evidence row after it. Frames and snapshots are both evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import session_schema
from .recording import Recording

ANCHOR_KINDS = ("click", "input", "mark", "t_ms", "step")
RESOLVE_STATUSES = (
    "resolved", "fallback", "ambiguous", "missing", "no_timeline"
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_rows(path: Path, *, tolerant: bool = False) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            if tolerant:
                continue
            raise ValueError(
                f"{path}:{line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(row, dict):
            if tolerant:
                continue
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(row)
    return rows


def timeline_rows(
    recording: Recording, *, tolerant: bool = False
) -> list[dict[str, Any]]:
    return read_rows(
        recording.path / session_schema.TIMELINE_FILE, tolerant=tolerant
    )


def diff_rows(
    recording: Recording, *, tolerant: bool = False
) -> list[dict[str, Any]]:
    return read_rows(
        recording.path / session_schema.FRAME_DIFFS_FILE, tolerant=tolerant
    )


def _row_time(row: dict[str, Any]) -> int | None:
    value = row.get("t_ms")
    return value if _is_int(value) else None


def _row_index(rows: list[dict[str, Any]], predicate) -> int | None:
    for index, row in enumerate(rows):
        if predicate(row):
            return index
    return None


def _evidence(
    recording: Recording, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        kind = row.get("type")
        if kind not in ("frame", "snapshot"):
            continue
        file = row.get("file")
        t_ms = _row_time(row)
        if not isinstance(file, str) or t_ms is None:
            continue
        evidence.append(
            {
                "row_index": index,
                "kind": kind,
                "frame_no": row.get("frame_no"),
                "t_ms": t_ms,
                "file": file,
                "label": row.get("label") if kind == "snapshot" else None,
            }
        )
    return evidence


def _last_evidence_at_or_before(
    evidence: list[dict[str, Any]], row_index: int
) -> dict[str, Any] | None:
    found = None
    for item in evidence:
        if item["row_index"] > row_index:
            break
        found = item
    return found


def _first_evidence_after(
    evidence: list[dict[str, Any]], row_index: int
) -> dict[str, Any] | None:
    for item in evidence:
        if item["row_index"] > row_index:
            return item
    return None


def _last_frame_at_or_before(
    evidence: list[dict[str, Any]], row_index: int
) -> dict[str, Any] | None:
    found = None
    for item in evidence:
        if item["row_index"] > row_index:
            break
        if item["kind"] == "frame":
            found = item
    return found


def _snapshot_at(
    evidence: list[dict[str, Any]], row_index: int, t_ms: int
) -> dict[str, Any] | None:
    for item in evidence:
        if item["row_index"] <= row_index:
            continue
        if item["kind"] == "snapshot" and item["t_ms"] == t_ms:
            return item
        if item["row_index"] > row_index and item["t_ms"] > t_ms:
            break
    return None


def _frame_number(row: dict[str, Any] | None) -> int | None:
    if row is None:
        return None
    value = row.get("frame_no")
    return value if _is_int(value) else None


def _image(recording: Recording, item: dict[str, Any]) -> str:
    return str((recording.path / item["file"]).resolve())


def _candidates(
    evidence: list[dict[str, Any]], row_index: int
) -> dict[str, int | None]:
    before = None
    after = None
    for item in evidence:
        if item["kind"] != "frame":
            continue
        number = _frame_number(item)
        if number is None:
            continue
        if item["row_index"] <= row_index:
            before = number
        elif after is None:
            after = number
    return {"before": before, "after": after}


def _result(
    recording: Recording,
    *,
    item: dict[str, Any] | None,
    requested_t_ms: int | None,
    basis: str,
    status: str,
    relation: str,
    evidence: list[dict[str, Any]],
    row_index: int,
    frame_before: int | None = None,
    frame_after: int | None = None,
) -> dict[str, Any]:
    candidates = _candidates(evidence, row_index)
    if frame_before is not None:
        candidates["before"] = frame_before
    if frame_after is not None:
        candidates["after"] = frame_after
    if item is None:
        return {
            "resolved": False,
            "requested_t_ms": requested_t_ms,
            "resolved_t_ms": None,
            "delta_ms": None,
            "relation": relation,
            "frame_no": None,
            "image": None,
            "image_kind": None,
            "basis": basis,
            "snapshot": None,
            "status": status,
            "approximate": False,
            "candidates": candidates,
        }
    resolved_t_ms = item["t_ms"]
    delta = (
        None
        if requested_t_ms is None
        else resolved_t_ms - requested_t_ms
    )
    snapshot = item["label"] if item["kind"] == "snapshot" else None
    return {
        "resolved": True,
        "requested_t_ms": requested_t_ms,
        "resolved_t_ms": resolved_t_ms,
        "delta_ms": delta,
        "relation": relation,
        "frame_no": _frame_number(item),
        "image": _image(recording, item),
        "image_kind": item["kind"],
        "basis": basis,
        "snapshot": snapshot,
        "status": status,
        "approximate": status in ("fallback", "ambiguous"),
        "candidates": candidates,
    }


def _relation(resolved_t_ms: int | None, requested_t_ms: int | None) -> str:
    if resolved_t_ms is None or requested_t_ms is None:
        return "exact"
    if resolved_t_ms == requested_t_ms:
        return "exact"
    return "before" if resolved_t_ms < requested_t_ms else "after"


def _input_row(
    rows: list[dict[str, Any]], seq: Any
) -> tuple[int, dict[str, Any]] | None:
    for index, row in enumerate(rows):
        if row.get("type") == "input" and row.get("seq") == seq:
            return index, row
    return None


def _input_anchor(
    recording: Recording,
    rows: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    row_index: int,
    row: dict[str, Any],
    *,
    at: str,
) -> dict[str, Any]:
    t_ms = _row_time(row)
    seq = row.get("seq")
    if at == "event":
        item = _last_frame_at_or_before(evidence, row_index)
        return _result(
            recording,
            item=item,
            requested_t_ms=t_ms,
            basis=f"input_{seq}_event",
            status="resolved" if item else "missing",
            relation=_relation(
                None if item is None else item["t_ms"], t_ms
            ),
            evidence=evidence,
            row_index=row_index,
        )
    item = _first_evidence_after(evidence, row_index)
    if item is None:
        item = _last_evidence_at_or_before(evidence, row_index)
        return _result(
            recording,
            item=item,
            requested_t_ms=t_ms,
            basis=f"input_{seq}_fallback",
            status="fallback" if item else "missing",
            relation="before",
            evidence=evidence,
            row_index=row_index,
        )
    return _result(
        recording,
        item=item,
        requested_t_ms=t_ms,
        basis=f"input_{seq}_after",
        status="resolved",
        relation=_relation(item["t_ms"], t_ms),
        evidence=evidence,
        row_index=row_index,
    )


def _click_anchor(
    recording: Recording,
    rows: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    seq_down: Any,
    seq_up: Any,
    *,
    at: str,
    offset_ms: int = 0,
) -> dict[str, Any]:
    down = _input_row(rows, seq_down)
    up = _input_row(rows, seq_up)
    if down is None or up is None:
        return _result(
            recording,
            item=None,
            requested_t_ms=None,
            basis=f"click_{seq_down}_{seq_up}",
            status="missing",
            relation="exact",
            evidence=evidence,
            row_index=len(rows),
        )
    down_index, down_row = down
    up_index, up_row = up
    down_t = _row_time(down_row)
    up_t = _row_time(up_row)
    frame_before = _frame_number(
        _last_evidence_at_or_before(evidence, down_index)
    )
    frame_after = _frame_number(_first_evidence_after(evidence, up_index))
    if offset_ms and up_t is not None:
        target = up_t + offset_ms
        return _resolve_time(
            recording,
            rows,
            evidence,
            target,
            basis=f"click_{seq_up}_offset",
            frame_before=frame_before,
            frame_after=frame_after,
        )
    if at == "event":
        item = _last_frame_at_or_before(evidence, down_index)
        return _result(
            recording,
            item=item,
            requested_t_ms=down_t,
            basis=f"click_{seq_down}_event",
            status="resolved" if item else "missing",
            relation=_relation(
                None if item is None else item["t_ms"], down_t
            ),
            evidence=evidence,
            row_index=down_index,
            frame_before=frame_before,
            frame_after=frame_after,
        )
    item = _first_evidence_after(evidence, up_index)
    if item is None:
        item = _last_evidence_at_or_before(evidence, up_index)
        return _result(
            recording,
            item=item,
            requested_t_ms=up_t,
            basis=f"click_{seq_up}_fallback",
            status="fallback" if item else "missing",
            relation=_relation(
                None if item is None else item["t_ms"], up_t
            ),
            evidence=evidence,
            row_index=up_index,
            frame_before=frame_before,
            frame_after=frame_after,
        )
    return _result(
        recording,
        item=item,
        requested_t_ms=up_t,
        basis=f"click_{seq_up}_after",
        status="resolved",
        relation=_relation(item["t_ms"], up_t),
        evidence=evidence,
        row_index=up_index,
        frame_before=frame_before,
        frame_after=frame_after,
    )


def _mark_rows(
    rows: list[dict[str, Any]], mark_id: Any
) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("type") == "mark" and row.get("id") == mark_id
    ]


def _mark_anchor(
    recording: Recording,
    rows: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    mark_id: Any,
    *,
    offset_ms: int = 0,
    at: str = "result",
) -> dict[str, Any]:
    matches = _mark_rows(rows, mark_id)
    if not matches:
        return _result(
            recording,
            item=None,
            requested_t_ms=None,
            basis=f"mark_{mark_id}",
            status="missing",
            relation="exact",
            evidence=evidence,
            row_index=len(rows),
        )
    row_index, row = matches[-1]
    t_ms = _row_time(row)
    ambiguous = len(matches) > 1
    if offset_ms and t_ms is not None:
        result = _resolve_time(
            recording,
            rows,
            evidence,
            t_ms + offset_ms,
            basis=f"mark_{mark_id}_offset",
        )
        if ambiguous:
            result["status"] = "ambiguous"
            result["approximate"] = True
        return result
    item = _snapshot_at(evidence, row_index, t_ms) if t_ms is not None else None
    if item is not None:
        return _result(
            recording,
            item=item,
            requested_t_ms=t_ms,
            basis=f"mark_{mark_id}_snapshot",
            status="ambiguous" if ambiguous else "resolved",
            relation=_relation(item["t_ms"], t_ms),
            evidence=evidence,
            row_index=row_index,
        )
    item = _first_evidence_after(evidence, row_index)
    if item is not None:
        return _result(
            recording,
            item=item,
            requested_t_ms=t_ms,
            basis=f"mark_{mark_id}_after",
            status="ambiguous" if ambiguous else "resolved",
            relation=_relation(item["t_ms"], t_ms),
            evidence=evidence,
            row_index=row_index,
        )
    item = _last_evidence_at_or_before(evidence, row_index)
    return _result(
        recording,
        item=item,
        requested_t_ms=t_ms,
        basis=f"mark_{mark_id}_fallback",
        status="missing" if item is None else "ambiguous" if ambiguous else "fallback",
        relation="before" if item is not None else "exact",
        evidence=evidence,
        row_index=row_index,
    )


def _resolve_time(
    recording: Recording,
    rows: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    t_ms: int,
    *,
    basis: str,
    frame_no: int | None = None,
    frame_before: int | None = None,
    frame_after: int | None = None,
) -> dict[str, Any]:
    if frame_no is not None:
        for item in evidence:
            if item["kind"] == "frame" and _frame_number(item) == frame_no:
                return _result(
                    recording,
                    item=item,
                    requested_t_ms=t_ms,
                    basis=f"{basis}_frame",
                    status="resolved",
                    relation=_relation(item["t_ms"], t_ms),
                    evidence=evidence,
                    row_index=item["row_index"],
                    frame_before=frame_before,
                    frame_after=frame_after,
                )
    exact = [item for item in evidence if item["t_ms"] == t_ms]
    if exact:
        chosen = exact[0]
        for item in exact:
            if item["kind"] == "snapshot":
                chosen = item
        return _result(
            recording,
            item=chosen,
            requested_t_ms=t_ms,
            basis=basis,
            status="resolved",
            relation="exact",
            evidence=evidence,
            row_index=chosen["row_index"],
            frame_before=frame_before,
            frame_after=frame_after,
        )
    before = None
    after = None
    for item in evidence:
        if item["t_ms"] < t_ms:
            before = item
        elif item["t_ms"] > t_ms and after is None:
            after = item
    item = after if after is not None else before
    if item is None:
        return _result(
            recording,
            item=None,
            requested_t_ms=t_ms,
            basis=basis,
            status="missing",
            relation="exact",
            evidence=evidence,
            row_index=len(rows),
            frame_before=frame_before,
            frame_after=frame_after,
        )
    return _result(
        recording,
        item=item,
        requested_t_ms=t_ms,
        basis=f"{basis}_{'after' if after is not None else 'before'}",
        status="fallback",
        relation="after" if after is not None else "before",
        evidence=evidence,
        row_index=item["row_index"],
        frame_before=frame_before,
        frame_after=frame_after,
    )


def resolve_anchor(
    recording: Recording,
    anchor: dict[str, Any],
    *,
    at: str = "result",
    offset_ms: int | None = None,
) -> dict[str, Any]:
    rows = timeline_rows(recording)
    evidence = _evidence(recording, rows)
    kind = anchor.get("kind")
    offset = (
        anchor.get("offset_ms", 0) if offset_ms is None else offset_ms
    )
    if not _is_int(offset):
        offset = 0
    if not rows:
        result = _result(
            recording,
            item=None,
            requested_t_ms=None,
            basis=str(kind or "anchor"),
            status="no_timeline",
            relation="exact",
            evidence=evidence,
            row_index=0,
        )
        result["truncated"] = bool(recording.manifest.get("truncated"))
        return result
    if kind == "click":
        result = _click_anchor(
            recording,
            rows,
            evidence,
            anchor.get("seq_down"),
            anchor.get("seq_up"),
            at=at,
            offset_ms=offset,
        )
    elif kind == "input":
        found = _input_row(rows, anchor.get("seq"))
        if found is None:
            result = _result(
                recording,
                item=None,
                requested_t_ms=None,
                basis=f"input_{anchor.get('seq')}",
                status="missing",
                relation="exact",
                evidence=evidence,
                row_index=len(rows),
            )
        else:
            result = _input_anchor(
                recording, rows, evidence, found[0], found[1], at=at
            )
    elif kind == "mark":
        result = _mark_anchor(
            recording,
            rows,
            evidence,
            anchor.get("id"),
            offset_ms=offset,
            at=at,
        )
    elif kind in ("t_ms", "frame", "step"):
        t_ms = anchor.get("t_ms")
        if kind == "frame":
            t_ms = _frame_time(rows, anchor.get("frame_no"), t_ms)
        if not _is_int(t_ms):
            result = _result(
                recording,
                item=None,
                requested_t_ms=None,
                basis=str(kind),
                status="missing",
                relation="exact",
                evidence=evidence,
                row_index=len(rows),
            )
        else:
            result = _resolve_time(
                recording,
                rows,
                evidence,
                t_ms,
                basis=str(kind),
                frame_no=(
                    anchor.get("frame_no")
                    if _is_int(anchor.get("frame_no"))
                    else None
                ),
            )
    else:
        result = _result(
            recording,
            item=None,
            requested_t_ms=None,
            basis=str(kind or "anchor"),
            status="missing",
            relation="exact",
            evidence=evidence,
            row_index=len(rows),
        )
    result["truncated"] = bool(recording.manifest.get("truncated"))
    return result


def _frame_time(
    rows: list[dict[str, Any]], frame_no: Any, fallback: Any
) -> Any:
    if _is_int(frame_no):
        for row in rows:
            if row.get("type") == "frame" and row.get("frame_no") == frame_no:
                t_ms = _row_time(row)
                if t_ms is not None:
                    return t_ms
    return fallback


def derive_anchor(
    recording: Recording,
    *,
    frame_no: int | None = None,
    t_ms: int | None = None,
) -> dict[str, Any]:
    """Derive the nearest mark / click / input before a note's frame."""
    rows = timeline_rows(recording)
    if not rows:
        return {"kind": "t_ms", "t_ms": t_ms if _is_int(t_ms) else 0}
    position = None
    if _is_int(frame_no):
        position = _row_index(
            rows,
            lambda row: row.get("type") == "frame"
            and row.get("frame_no") == frame_no,
        )
    if position is None and _is_int(t_ms):
        position = _row_index(
            rows, lambda row: (_row_time(row) or -1) >= t_ms
        )
    if position is None:
        position = len(rows) - 1
    note_t = t_ms if _is_int(t_ms) else _row_time(rows[position]) or 0
    pending_up: dict[str, Any] | None = None
    for index in range(position, -1, -1):
        row = rows[index]
        kind = row.get("type")
        if kind == "mark":
            anchor_t = _row_time(row) or 0
            return {
                "kind": "mark",
                "id": row.get("id"),
                "offset_ms": max(0, note_t - anchor_t),
            }
        if kind != "input":
            continue
        device = row.get("device")
        action = row.get("action")
        if device != "pointer":
            anchor_t = _row_time(row) or 0
            return {
                "kind": "input",
                "seq": row.get("seq"),
                "offset_ms": max(0, note_t - anchor_t),
            }
        if action == "up" and pending_up is None:
            pending_up = row
            continue
        if action != "down":
            continue
        if pending_up is not None and pending_up.get("device") == "pointer":
            up_t = _row_time(pending_up) or 0
            return {
                "kind": "click",
                "seq_down": row.get("seq"),
                "seq_up": pending_up.get("seq"),
                "offset_ms": max(0, note_t - up_t),
            }
        anchor_t = _row_time(row) or 0
        return {
            "kind": "input",
            "seq": row.get("seq"),
            "offset_ms": max(0, note_t - anchor_t),
        }
    return {"kind": "t_ms", "t_ms": note_t}


def note_anchor(note: dict[str, Any]) -> dict[str, Any] | None:
    value = note.get("feedback_anchor")
    return value if isinstance(value, dict) else None
