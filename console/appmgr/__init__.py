"""User app domain package: discovery, scaffold, trash and filesystem views.

Apps are discovered from ``user/app/<name>/app.json``; there is no central
registration table to edit.  The CLI ``scripts/new_app.py`` and the web layer
both call this package, so scaffolding, deletion and generated-registry output
have one implementation.

Public lifecycle interface: :func:`list_apps`, :func:`app_tree`,
:func:`recent_apps`, :func:`list_trash`, :func:`scaffold_app`,
:func:`delete_app`, :func:`restore_app`, :func:`permanently_delete`.
"""

from __future__ import annotations

from .common import AppError, WINDOWS_DEVICE_NAMES, resolve_repo_root
from .policy import is_protected_name
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
    "permanently_delete",
    "recent_apps",
    "resolve_repo_root",
    "restore_app",
    "scaffold_app",
]
