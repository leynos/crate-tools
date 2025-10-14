"""Version bumping command implementation."""

from __future__ import annotations

import os
import tempfile
import typing as typ
from contextlib import suppress
from pathlib import Path

from tomlkit import parse as parse_toml
from tomlkit import string
from tomlkit.items import Item, Table

from lading import config as config_module
from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from tomlkit.toml_document import TOMLDocument

    from lading.config import LadingConfig
    from lading.workspace import WorkspaceGraph

_WORKSPACE_SELECTORS: typ.Final[tuple[tuple[str, ...], ...]] = (
    ("package",),
    ("workspace", "package"),
)


def run(
    workspace_root: Path | str,
    target_version: str,
    *,
    configuration: LadingConfig | None = None,
    workspace: WorkspaceGraph | None = None,
) -> str:
    """Update workspace and crate manifest versions to ``target_version``."""
    root_path = normalise_workspace_root(workspace_root)
    if configuration is None:
        configuration = config_module.current_configuration()
    if workspace is None:
        from lading.workspace import load_workspace

        workspace = load_workspace(root_path)

    changed = 0
    workspace_manifest = root_path / "Cargo.toml"
    if _update_manifest(workspace_manifest, _WORKSPACE_SELECTORS, target_version):
        changed += 1

    excluded = set(configuration.bump.exclude)
    for crate in workspace.crates:
        if crate.name in excluded:
            continue
        if _update_manifest(crate.manifest_path, (("package",),), target_version):
            changed += 1

    if changed == 0:
        return f"No manifest changes required; all versions already {target_version}."
    return f"Updated version to {target_version} in {changed} manifest(s)."


def _update_manifest(
    manifest_path: Path,
    selectors: tuple[tuple[str, ...], ...],
    target_version: str,
) -> bool:
    """Apply ``target_version`` to each table described by ``selectors``."""
    document = _parse_manifest(manifest_path)
    changed = False
    for selector in selectors:
        table = _select_table(document, selector)
        changed |= _assign_version(table, target_version)
    if changed:
        _write_atomic_text(manifest_path, document.as_string())
    return changed


def _parse_manifest(manifest_path: Path) -> TOMLDocument:
    """Load ``manifest_path`` into a :class:`tomlkit` document."""
    content = manifest_path.read_text(encoding="utf-8")
    return parse_toml(content)


def _select_table(
    document: TOMLDocument | Table,
    keys: tuple[str, ...],
) -> Table | None:
    """Return the nested table located by ``keys`` if it exists."""
    if not keys:
        return document if isinstance(document, Table) else None
    current: object = document
    for key in keys:
        getter = getattr(current, "get", None)
        if getter is None:
            return None
        next_value = getter(key)
        if not isinstance(next_value, Table):
            return None
        current = next_value
    return current if isinstance(current, Table) else None


def _assign_version(table: Table | None, target_version: str) -> bool:
    """Update ``table['version']`` when ``table`` is present."""
    if table is None:
        return False
    current = table.get("version")
    if _value_matches(current, target_version):
        return False
    if isinstance(current, Item):
        replacement = string(target_version)
        with suppress(AttributeError):  # Preserve existing formatting and comments
            replacement._trivia = current._trivia  # type: ignore[attr-defined]
        table["version"] = replacement
    else:
        table["version"] = target_version
    return True


def _value_matches(value: object, expected: str) -> bool:
    """Return ``True`` when ``value`` already equals ``expected``."""
    if isinstance(value, Item):
        return value.value == expected
    return value == expected


def _write_atomic_text(manifest_path: Path, content: str) -> None:
    """Persist ``content`` to ``manifest_path`` atomically using UTF-8 encoding."""
    dirpath = manifest_path.parent
    fd, tmp_path = tempfile.mkstemp(
        dir=dirpath,
        prefix=f"{manifest_path.name}.",
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        Path(tmp_path).replace(manifest_path)
    finally:
        with suppress(FileNotFoundError):
            Path(tmp_path).unlink()
