"""Workspace member maintenance for publish preparation workflows.

This module concentrates all helpers that validate, filter, and persist the
workspace member listings so that the main automation can depend on consistent
manifest structure.
"""

from __future__ import annotations

import functools
import typing as typ
from pathlib import Path

from publish_workspace_serialise import _write_manifest_with_newline
from tomlkit import array, parse
from tomlkit.items import Array

if typ.TYPE_CHECKING:
    from tomlkit.toml_document import TOMLDocument

PUBLISHABLE_CRATES: typ.Final[tuple[str, ...]] = (
    "rstest-bdd-patterns",
    "rstest-bdd-macros",
    "rstest-bdd",
    "cargo-bdd",
)

__all__ = [
    "PUBLISHABLE_CRATES",
    "_convert_list_to_array",
    "_ensure_members_array",
    "_filter_workspace_members",
    "_format_multiline_members_if_needed",
    "_get_valid_workspace_members",
    "_should_write_manifest",
    "_write_manifest_if_changed",
    "prune_workspace_members",
]


def prune_workspace_members(manifest: Path) -> None:
    """Remove non-crate entries from the workspace members list."""
    manifest = Path(manifest)
    document = parse(manifest.read_text(encoding="utf-8"))
    members = _get_valid_workspace_members(document)
    if members is None:
        return

    changed = _filter_workspace_members(members)
    _write_manifest_if_changed(
        document=document,
        manifest=manifest,
        changed=changed,
        members=members,
    )


def _get_valid_workspace_members(document: TOMLDocument) -> Array | None:
    """Return the workspace members array when it exists and is valid."""
    workspace = document.get("workspace")
    if workspace is None:
        return None

    members = workspace.get("members")
    if members is None:
        return None

    return _ensure_members_array(workspace, members)


def _ensure_members_array(workspace: dict, members: object) -> Array | None:
    """Normalise ``workspace['members']`` to a TOML array when possible."""
    if isinstance(members, Array):
        return members

    if isinstance(members, list):
        return _convert_list_to_array(workspace, members)

    return None


def _convert_list_to_array(workspace: dict, members: list) -> Array:
    """Convert ``members`` list to a TOML array attached to ``workspace``."""
    rebuilt_members = array()
    rebuilt_members.extend(members)
    workspace["members"] = rebuilt_members
    return rebuilt_members


def _filter_workspace_members(members: Array) -> bool:
    """Remove ineligible workspace members, returning ``True`` if mutated."""
    changed = False
    for index in range(len(members) - 1, -1, -1):
        entry = members[index]
        if not isinstance(entry, str) or Path(entry).name not in PUBLISHABLE_CRATES:
            del members[index]
            changed = True

    return changed


def _write_manifest_if_changed(
    *, document: TOMLDocument, manifest: Path, changed: bool, members: Array
) -> None:
    """Persist ``document`` to ``manifest`` only when ``changed`` is ``True``."""
    if not _should_write_manifest(changed=changed, document=document):
        return

    _format_multiline_members_if_needed(members)
    _write_manifest_with_newline(document, manifest)


def _should_write_manifest(*, changed: bool, document: TOMLDocument) -> bool:
    """Return ``True`` when the manifest should be persisted."""
    return changed and document.get("workspace") is not None


def _members_is_multiline(members: Array) -> bool:
    """Return the multiline flag recorded on ``members`` arrays."""
    return bool(getattr(members, "_multiline", False))


def _format_multiline_members_if_needed(members: Array) -> None:
    """Ensure ``members`` renders multiline and expose the state for callers.

    The function toggles TOMLKit's multiline rendering when the serialised array
    spans multiple lines and attaches an ``is_multiline`` helper so downstream
    logic can observe the state. The helper reads the private ``_multiline``
    attribute that TOMLKit maintains.
    """
    should_multiline = "\n" in members.as_string()
    members.multiline(multiline=should_multiline)

    # ``is_multiline`` is dynamically attached for compatibility with existing
    # consumers that query TOMLKit arrays for this helper.
    members.is_multiline = functools.partial(  # type: ignore[attr-defined]
        _members_is_multiline, members
    )
