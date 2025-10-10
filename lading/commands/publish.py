"""Placeholder implementation for the ``lading publish`` command."""

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
    """Return a placeholder message for the publish command."""
    root_path = normalise_workspace_root(workspace_root)
    if configuration is None:
        configuration = config_module.current_configuration()
    if workspace is None:
        from lading.workspace import load_workspace

        workspace = load_workspace(root_path)
    strip_patches = configuration.publish.strip_patches
    crate_summary = describe_crates(workspace)
    return (
        "publish placeholder invoked for "
        f"{root_path} (crates: {crate_summary}, strip patches: {strip_patches})"
    )
