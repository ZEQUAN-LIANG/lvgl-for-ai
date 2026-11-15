"""Public API for the LVGL AI tools control layer."""

from .control import (
    BuildError,
    EngineNotFound,
    LatError,
    LinkError,
    ProtocolError,
    Recording,
    Runtime,
    RuntimeCrash,
    ScenarioError,
    ToolError,  # noqa: F401 - re-exported for `from lvgl_ai import ToolError`
    session_index,
)
from .paths import TOOL_VERSION
from .scenario import play_scenario

__version__ = TOOL_VERSION

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
    "__version__",
    "play_scenario",
    "session_index",
]
