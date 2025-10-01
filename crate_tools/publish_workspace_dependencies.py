"""Dependency rewriting utilities for publish-time manifest adjustments.

These helpers centralise the logic that updates inter-crate dependency entries
so release automation can substitute version numbers and optional local path
references in a single place.
"""

from __future__ import annotations

import logging
from pathlib import Path

from publish_patch import REPLACEMENTS, apply_replacements

__all__ = ["apply_workspace_replacements"]


LOGGER = logging.getLogger(__name__)


def _compute_valid_targets(
    crates: tuple[str, ...] | None,
) -> tuple[tuple[str, ...], set[str]]:
    """Determine which crates should receive replacement updates."""

    if crates is None:
        return tuple(REPLACEMENTS), set()

    unknown = {crate for crate in crates if crate not in REPLACEMENTS}
    valid = tuple(crate for crate in crates if crate in REPLACEMENTS)
    return valid, unknown


def apply_workspace_replacements(
    workspace_root: Path,
    version: str,
    *,
    include_local_path: bool,
    crates: tuple[str, ...] | None = None,
) -> None:
    """Rewrite workspace dependency declarations for publish workflows.

    Crates lacking replacement configuration are reported via a warning and left
    unchanged so publish runs can continue updating the remaining manifests.

    Parameters
    ----------
    workspace_root : Path
        Root directory of the rstest-bdd workspace whose manifests are rewritten.
    version : str
        Version string applied to patched dependency entries.
    include_local_path : bool
        Toggle whether rewritten dependencies retain their relative path entries.
    crates : tuple[str, ...] | None, optional
        Subset of crates to update; default rewrites every crate with
        replacements. Crates without replacement configuration are skipped and
        left untouched so callers can safely request broader sets.

    Returns
    -------
    None
        All matching manifests are rewritten in place.

    Examples
    --------
    >>> from pathlib import Path
    >>> apply_workspace_replacements(Path("."), "1.2.3", include_local_path=False)

    """
    workspace_root = Path(workspace_root)
    targets, unknown = _compute_valid_targets(crates)
    if unknown:
        formatted = ", ".join(sorted(unknown))
        LOGGER.warning("Skipping crates without replacement entries: %s", formatted)
    for crate in targets:
        manifest = workspace_root / "crates" / crate / "Cargo.toml"
        apply_replacements(
            crate,
            manifest,
            version,
            include_local_path=include_local_path,
        )
