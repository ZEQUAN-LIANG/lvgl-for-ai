"""Compatibility package for the old control-layer import path.

The implementation lives in :mod:`lvgl_ai.control`; ``lvgl_ai.core`` re-exports
the same public objects so existing imports keep working.
"""

from __future__ import annotations

from ..control import (
    BuildError,
    EngineNotFound,
    LatError,
    LinkError,
    ProtocolError,
    Recording,
    Runtime,
    RuntimeCrash,
    ScenarioError,
    ToolError,
)

# Load the compatibility submodules so ``lvgl_ai.core.errors`` (and the other
# old paths) stay reachable as package attributes, as they were before the
# implementation moved to ``lvgl_ai.control``.
from . import (  # noqa: F401
    build,
    build_plan,
    engine_link,
    errors,
    input,
    keys,
    recording,
    retention,
    runtime,
    session,
    session_schema,
)

__all__ = [
    "BuildError",
    "EngineNotFound",
    "LatError",
    "LinkError",
    "ProtocolError",
    "Recording",
    "Runtime",
    "RuntimeCrash",
    "ScenarioError",
    "ToolError",
]
