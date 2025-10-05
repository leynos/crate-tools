"""Placeholder implementation for the ``lading bump`` command."""

from __future__ import annotations

import typing as typ

from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path


def run(workspace_root: Path) -> str:
    """Return a placeholder message for the bump command.

    Step 1.1 only wires the CLI, so we provide a friendly acknowledgement
    instead of mutating manifests. The message makes it trivial for tests
    to assert that dispatch occurred correctly without constraining future
    behaviour.
    """
    root_path = normalise_workspace_root(workspace_root)
    return f"bump placeholder invoked for {root_path}"
