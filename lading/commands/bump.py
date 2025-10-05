"""Placeholder implementation for the ``lading bump`` command."""

from __future__ import annotations

from pathlib import Path

from plumbum import local


def run(workspace_root: Path) -> str:
    """Return a placeholder message for the bump command.

    Step 1.1 only wires the CLI, so we provide a friendly acknowledgement
    instead of mutating manifests. The message makes it trivial for tests
    to assert that dispatch occurred correctly without constraining future
    behaviour.
    """
    candidate = local.path(str(workspace_root))
    root_path = Path(str(candidate)).expanduser().resolve(strict=False)
    return f"bump placeholder invoked for {root_path}"
