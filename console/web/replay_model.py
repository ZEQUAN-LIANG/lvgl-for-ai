from __future__ import annotations

from functools import cached_property
from typing import Any

from control.recording import ANNOTATIONS_SCHEMA, Recording
from . import urls

LOG_TAIL_LINES = 80
BUILD_LOG_TAIL_LINES = 40
NOTE_CROP_ALT = "标注区域图"


def _empty_annotations() -> dict[str, Any]:
    return {"schema": ANNOTATIONS_SCHEMA, "notes": []}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _display(value: Any) -> str:
    return "" if value is None else str(value)


def _file_name(relative: str) -> str:
    return relative.rsplit("/", 1)[-1]


def _note_view(
    note: dict[str, Any],
    session_id: str | None,
    frames_by_no: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tags_value = note.get("tags")
    tags = " ".join(f"#{tag}" for tag in tags_value) if tags_value else ""
    anchors_value = note.get("anchors")
    frame_start = note.get("frame_start")
    frame_end = note.get("frame_end")
    frame_numbers: list[int] = []
    annotated_by_frame: dict[int, str] = {}
    region_text = ""
    crops: list[dict[str, str]] = []
    anchor_count = 0
    if isinstance(anchors_value, list) and anchors_value:
        anchor_count = len(anchors_value)
        text_parts = []
        for anchor in anchors_value:
            if not isinstance(anchor, dict):
                continue
            frame_no = anchor.get("frame_no")
            if _is_int(frame_no):
                frame_numbers.append(frame_no)
                annotated = anchor.get("annotated")
                if isinstance(annotated, str) and annotated:
                    annotated_by_frame[frame_no] = annotated
            regions_value = anchor.get("regions") or []
            if not isinstance(regions_value, list) or not regions_value:
                continue
            text_parts.append(
                f"帧 {_display(frame_no)}: "
                + "；".join(
                    f"({region.get('x')}, {region.get('y')}) "
                    f"{region.get('w')}×{region.get('h')}"
                    for region in regions_value
                )
            )
            for region in regions_value:
                image = region.get("image")
                if not isinstance(image, str) or not image:
                    continue
                crops.append(
                    {
                        "url": urls.region_url(session_id, image),
                        "alt": f"帧 {_display(frame_no)} 标注区域",
                    }
                )
        region_text = "\n".join(text_parts)
    else:
        if _is_int(note.get("frame_no")):
            frame_numbers.append(note["frame_no"])
        regions_value = note.get("regions")
        if regions_value:
            region_text = "；".join(
                f"({region.get('x')}, {region.get('y')}) "
                f"{region.get('w')}×{region.get('h')}"
                for region in regions_value
            )
            for region in regions_value:
                image = region.get("image")
                if not isinstance(image, str) or not image:
                    continue
                crops.append(
                    {
                        "url": urls.region_url(session_id, image),
                        "alt": NOTE_CROP_ALT,
                    }
                )
    if anchor_count:
        if frame_start == frame_end:
            meta = (
                f"帧 {_display(frame_start)} · "
                f"{anchor_count} 个锚点 · t={_display(note.get('t_ms'))} ms"
            )
        else:
            meta = (
                f"帧 {_display(frame_start)}–{_display(frame_end)} · "
                f"{anchor_count} 个锚点 · t={_display(note.get('t_ms'))} ms"
            )
    else:
        meta = (
            f"帧 {_display(note.get('frame_no'))} · "
            f"t={_display(note.get('t_ms'))} ms"
        )
    frame_views = []
    by_number = frames_by_no or {}
    for frame_no in dict.fromkeys(frame_numbers):
        frame = by_number.get(frame_no)
        if frame is None:
            continue
        view = {
            "frame_no": frame_no,
            "url": frame["url"],
            "t_ms": frame.get("t_ms", 0),
        }
        annotated = annotated_by_frame.get(frame_no)
        if annotated:
            view["annotated"] = urls.region_url(session_id, annotated)
        frame_views.append(view)
    return {
        "id": note.get("id"),
        "frame_no": note.get("frame_no"),
        "has_frame": _is_int(note.get("frame_no")),
        "meta": meta,
        "tags": tags,
        "text": note.get("text"),
        "region_text": region_text,
        "frames": frame_views,
        "crops": crops,
    }


class ReplayModel:
    def __init__(self, recording: Recording | None = None) -> None:
        self._recording = recording

    @classmethod
    def empty(cls) -> ReplayModel:
        return cls(None)

    @property
    def session_id(self) -> str | None:
        return None if self._recording is None else self._recording.path.name

    @cached_property
    def manifest(self) -> dict[str, Any]:
        return {} if self._recording is None else self._recording.manifest

    @cached_property
    def _timeline_read(
        self,
    ) -> tuple[list[dict[str, Any]], Exception | None]:
        if self._recording is None:
            return [], None
        try:
            return self._recording.timeline(), None
        except (FileNotFoundError, ValueError) as exc:
            return [], exc

    @property
    def timeline(self) -> list[dict[str, Any]]:
        return self._timeline_read[0]

    @property
    def timeline_error(self) -> Exception | None:
        return self._timeline_read[1]

    @cached_property
    def frames(self) -> list[dict[str, Any]]:
        if self._recording is None:
            return []
        self._prime_timeline()
        session_id = self._recording.path.name
        return [
            {
                "frame_no": view["frame_no"],
                "t_ms": view["t_ms"],
                "file": view["file"],
                "url": urls.frame_url(session_id, _file_name(view["file"])),
            }
            for view in self._recording.frame_views()
        ]

    @cached_property
    def snapshots(self) -> list[dict[str, Any]]:
        if self._recording is None:
            return []
        self._prime_timeline()
        session_id = self._recording.path.name
        return [
            {
                "label": view["label"],
                "file": view["file"],
                "url": urls.snapshot_url(session_id, _file_name(view["file"])),
                "frame_no": view["frame_no"],
                "t_ms": view["t_ms"],
            }
            for view in self._recording.snapshot_views()
        ]

    @cached_property
    def _frame_diffs_read(
        self,
    ) -> tuple[list[dict[str, Any]], Exception | None]:
        if self._recording is None:
            return [], None
        try:
            return self._recording.frame_diffs(), None
        except (FileNotFoundError, ValueError) as exc:
            return [], exc

    @property
    def frame_diffs(self) -> list[dict[str, Any]]:
        return self._frame_diffs_read[0]

    @property
    def frame_diffs_error(self) -> Exception | None:
        return self._frame_diffs_read[1]

    @cached_property
    def _reference_diffs_read(
        self,
    ) -> tuple[list[dict[str, Any]] | None, Exception | None]:
        if self._recording is None:
            return [], None
        try:
            return self._recording.reference_diffs(), None
        except (FileNotFoundError, ValueError) as exc:
            return [], exc

    @property
    def reference_diffs(self) -> list[dict[str, Any]] | None:
        return self._reference_diffs_read[0]

    @property
    def reference_diffs_error(self) -> Exception | None:
        return self._reference_diffs_read[1]

    @cached_property
    def _annotations_read(
        self,
    ) -> tuple[dict[str, Any], Exception | None]:
        if self._recording is None:
            return _empty_annotations(), None
        try:
            return self._recording.annotations, None
        except ValueError as exc:
            return _empty_annotations(), exc

    @property
    def annotations(self) -> dict[str, Any]:
        return self._annotations_read[0]

    @property
    def annotations_error(self) -> Exception | None:
        return self._annotations_read[1]

    @cached_property
    def log_tail(self) -> list[str]:
        if self._recording is None:
            return []
        return self._recording.log_tail(LOG_TAIL_LINES)

    @cached_property
    def build_log_tail(self) -> list[str]:
        if self._recording is None:
            return []
        try:
            build_log = self._recording.build_log()
        except FileNotFoundError:
            return []
        return build_log.splitlines()[-BUILD_LOG_TAIL_LINES:]

    @property
    def note_count(self) -> int:
        return len(self.annotations.get("notes") or [])

    def note_views(self) -> list[dict[str, Any]]:
        notes = self.annotations.get("notes") or []
        frames_by_no = {
            frame["frame_no"]: frame
            for frame in self.frames
            if _is_int(frame.get("frame_no"))
        }
        return [
            _note_view(note, self.session_id, frames_by_no) for note in notes
        ]

    def _prime_timeline(self) -> None:
        _ = self.timeline

    def prime(self) -> None:
        _ = (
            self.manifest,
            self.timeline,
            self.frame_diffs,
            self.reference_diffs,
            self.annotations,
            self.build_log_tail,
            self.frames,
            self.snapshots,
            self.log_tail,
        )


def load(recording: Recording) -> ReplayModel:
    return ReplayModel(recording)
