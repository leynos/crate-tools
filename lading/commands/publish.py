"""Placeholder implementation for the ``lading publish`` command."""

from __future__ import annotations

from pathlib import Path

from plumbum import local


def run(workspace_root: Path) -> str:
    """Return a placeholder message for the publish command."""
    candidate = local.path(str(workspace_root))
    root_path = Path(str(candidate)).expanduser().resolve(strict=False)
    return f"publish placeholder invoked for {root_path}"
