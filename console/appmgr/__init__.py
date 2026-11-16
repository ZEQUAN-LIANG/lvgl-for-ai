"""User app domain package: registry, scaffold, trash and filesystem views.

The CLI ``scripts/new_app.py`` and the web layer both call this package, so
registration, scaffolding and deletion have one implementation, never a
second registry.

Public lifecycle interface: :func:`list_apps`, :func:`app_tree`,
:func:`recent_apps`, :func:`list_trash`, :func:`scaffold_app`,
:func:`delete_app`, :func:`restore_app`, :func:`permanently_delete`.
Compatibility re-exports keep the registry text helpers and :class:`AppError`
importable from ``apps`` exactly as before the package split.
"""

from __future__ import annotations

from .common import AppError, WINDOWS_DEVICE_NAMES, resolve_repo_root
from .policy import is_protected_name
from .registry import parse_app_entries, register_app, unregister_app
from .scaffold import scaffold_app
from .trash import delete_app, list_trash, permanently_delete, restore_app
from .views import app_tree, list_apps, recent_apps

__all__ = [
    "AppError",
    "WINDOWS_DEVICE_NAMES",
    "app_tree",
    "delete_app",
    "is_protected_name",
    "list_apps",
    "list_trash",
    "parse_app_entries",
    "permanently_delete",
    "recent_apps",
    "register_app",
    "resolve_repo_root",
    "restore_app",
    "scaffold_app",
    "unregister_app",
]
