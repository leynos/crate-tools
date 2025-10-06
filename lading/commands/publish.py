"""Placeholder implementation for the ``lading publish`` command."""

from __future__ import annotations

import typing as typ

from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path


def run(workspace_root: Path) -> str:
    """Return a placeholder message for the publish command."""
    root_path = normalise_workspace_root(workspace_root)
    return f"publish placeholder invoked for {root_path}"
