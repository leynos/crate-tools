"""Placeholder implementation for the ``lading publish`` command."""

from __future__ import annotations

import typing as typ

from lading import config as config_module
from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading.config import LadingConfig


def run(workspace_root: Path, configuration: LadingConfig | None = None) -> str:
    """Return a placeholder message for the publish command."""
    root_path = normalise_workspace_root(workspace_root)
    if configuration is None:
        configuration = config_module.current_configuration()
    strip_patches = configuration.publish.strip_patches
    return (
        f"publish placeholder invoked for {root_path} (strip patches: {strip_patches})"
    )
