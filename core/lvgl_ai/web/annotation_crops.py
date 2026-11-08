"""Crop saved annotation regions so the evidence is readable without a CLI.

The annotation transaction calls :func:`prepare_region_images` to decode every
crop before anything is written, then :func:`write_region_crops` to commit
them. Each region gains a session-relative ``image`` path such as
``regions/note-1a2b3c4d-0.png``; the page also serves those PNGs, so an AI
agent can read ``annotations.json`` and then the image file directly.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..control.recording import Recording
from ..png_codec import PngError, Region, crop_png

IMAGE_DIR = "regions"


class RegionImageError(ValueError):
    """A note's frame or region cannot be turned into a crop."""


def _safe_note_stem(note_id: str) -> str:
    """Filesystem-safe stem that still points back to the note id."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", note_id).strip("._-")
    if not safe:
        safe = "note"
    if safe != note_id or len(safe) > 64:
        digest = hashlib.sha1(note_id.encode("utf-8")).hexdigest()[:8]
        safe = f"{safe[:48]}-{digest}"
    if not safe[0].isalnum():
        safe = f"n-{safe}"
    return safe


def _frame_path(recording: Recording, frame_no: int) -> Path:
    for path in recording.frames:
        if path.stem.isdigit() and int(path.stem) == frame_no:
            return path
    raise RegionImageError(
        f"frame {frame_no} not found under {recording.path / 'frames'}"
    )


def prepare_region_images(
    recording: Recording, note: dict[str, Any]
) -> tuple[dict[str, Any], list[tuple[Path, bytes]]]:
    """Return ``note`` with ``regions[i].image`` paths plus crops to write.

    A note with no regions returns the note unchanged and no crops. All crops
    are decoded before any file is written, so a bad frame/region cannot leave
    a half-updated annotation in place.
    """
    regions_value = note.get("regions") or []
    if not regions_value:
        return dict(note), []

    frame_no = note.get("frame_no")
    if isinstance(frame_no, bool) or not isinstance(frame_no, int):
        raise RegionImageError("note has no valid frame_no")
    frame_path = _frame_path(recording, frame_no)
    try:
        frame_data = frame_path.read_bytes()
    except OSError as exc:
        raise RegionImageError(f"cannot read frame {frame_path}: {exc}") from exc

    stem = _safe_note_stem(str(note.get("id") or "note"))
    prepared: list[tuple[Path, bytes]] = []
    regions: list[dict[str, Any]] = []
    for index, raw in enumerate(regions_value):
        try:
            region = Region(
                int(raw["x"]), int(raw["y"]), int(raw["w"]), int(raw["h"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RegionImageError(f"region {index} is malformed") from exc
        try:
            cropped, _clipped, _image = crop_png(frame_data, region)
        except PngError as exc:
            raise RegionImageError(
                f"cannot crop region {index} from frame {frame_no}: {exc}"
            ) from exc
        relative = f"{IMAGE_DIR}/{stem}-{index}.png"
        prepared.append((recording.path / relative, cropped))
        updated = dict(raw)
        updated["image"] = relative
        regions.append(updated)

    result = dict(note)
    result["regions"] = regions
    return result, prepared


# (path, previous bytes or None when the file did not exist yet)
CropJournal = list[tuple[Path, bytes | None]]


def write_region_crops(prepared: list[tuple[Path, bytes]]) -> CropJournal:
    """Write prepared crops and return a journal that can undo this call.

    Existing crop files are kept in the journal before they are overwritten,
    so a failed transaction restores the old content instead of leaving the
    new one behind. A new crop is removed by the rollback. The journal is
    empty when the note has no regions.
    """
    if not prepared:
        return []
    journal: CropJournal = []
    try:
        prepared[0][0].parent.mkdir(parents=True, exist_ok=True)
        for path, payload in prepared:
            previous = path.read_bytes() if path.exists() else None
            journal.append((path, previous))
            path.write_bytes(payload)
    except OSError:
        rollback_region_crops(journal)
        raise
    return journal


def rollback_region_crops(journal: CropJournal) -> None:
    """Best-effort undo of the crops a failed transaction wrote."""
    for path, previous in journal:
        try:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous)
        except OSError:
            pass
