"""Placeholder implementation for the ``lading bump`` command."""

from __future__ import annotations

import typing as typ

from lading import config as config_module
from lading.commands._shared import describe_crates
from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading.config import LadingConfig
    from lading.workspace import WorkspaceGraph


def run(
    workspace_root: Path,
    configuration: LadingConfig | None = None,
    workspace: WorkspaceGraph | None = None,
) -> str:
    """Return a placeholder message for the bump command.

    Step 1.1 only wires the CLI, so we provide a friendly acknowledgement
    instead of mutating manifests. The message makes it trivial for tests
    to assert that dispatch occurred correctly without constraining future
    behaviour.
    """
    root_path = normalise_workspace_root(workspace_root)
    if configuration is None:
        configuration = config_module.current_configuration()
    if workspace is None:
        from lading.workspace import load_workspace

        workspace = load_workspace(root_path)
    doc_files = configuration.bump.doc_files
    doc_files_summary = ", ".join(doc_files) if doc_files else "none"
    crate_summary = describe_crates(workspace)
    return (
        "bump placeholder invoked for "
        f"{root_path} (crates: {crate_summary}, doc files: {doc_files_summary})"
    )
