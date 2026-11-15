from __future__ import annotations

from urllib.parse import quote


def page_url(host: str, port: int) -> str:
    return f"http://{host}:{int(port)}/"


def frame_url(session_id: str, filename: str) -> str:
    return f"/frames/{quote(str(session_id))}/{quote(str(filename))}"


def snapshot_url(session_id: str, filename: str) -> str:
    return f"/snapshots/{quote(str(session_id))}/{quote(str(filename))}"


def annotations_url(session_id: str) -> str:
    return f"/api/sessions/{quote(str(session_id))}/annotations"


def whiteboards_url(session_id: str) -> str:
    return f"/api/sessions/{quote(str(session_id))}/whiteboards"


def region_url(session_id: str, image: str) -> str:
    filename = str(image).rsplit("/", 1)[-1]
    return f"/regions/{session_id}/{filename}"
