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
    ToolError,
    summarize_session,
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
    "summarize_session",
]
