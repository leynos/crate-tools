"""Filesystem helpers used across :mod:`lading`."""

from __future__ import annotations

from pathlib import Path

from plumbum import local


def normalise_workspace_root(value: Path | str | None) -> Path:
    """Return an absolute workspace path with ``~`` expanded."""
    if value is None:
        return Path.cwd().resolve()
    candidate = local.path(str(value))
    expanded = Path(str(candidate)).expanduser()
    return expanded.resolve(strict=False)
