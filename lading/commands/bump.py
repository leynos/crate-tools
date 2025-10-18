"""Version bumping command implementation."""

from __future__ import annotations

import os
import re
import tempfile
import typing as typ
from contextlib import suppress
from dataclasses import dataclass, field  # noqa: ICN003
from pathlib import Path

from tomlkit import parse as parse_toml
from tomlkit import string
from tomlkit.items import InlineTable, Item, Table

from lading import config as config_module
from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from tomlkit.toml_document import TOMLDocument

    from lading.config import LadingConfig
    from lading.workspace import WorkspaceCrate, WorkspaceGraph
else:  # pragma: no cover - provide runtime placeholders for type checking imports
    LadingConfig = WorkspaceCrate = WorkspaceGraph = TOMLDocument = typ.Any

_WORKSPACE_SELECTORS: typ.Final[tuple[tuple[str, ...], ...]] = (
    ("package",),
    ("workspace", "package"),
)

_DEPENDENCY_SECTION_BY_KIND: typ.Final[dict[str | None, str]] = {
    None: "dependencies",
    "normal": "dependencies",
    "dev": "dev-dependencies",
    "build": "build-dependencies",
}

_NON_DIGIT_PREFIX: typ.Final[re.Pattern[str]] = re.compile(r"^([^\d]*)")


@dataclass(frozen=True)
class BumpOptions:
    """Configuration options for bump operations."""

    dry_run: bool = False
    configuration: LadingConfig | None = None
    workspace: WorkspaceGraph | None = None
    dependency_sections: typ.Mapping[str, typ.Collection[str]] | None = field(
        default=None
    )


def run(
    workspace_root: Path | str,
    target_version: str,
    options: BumpOptions | None = None,
) -> str:
    """Update workspace and crate manifest versions to ``target_version``."""
    options = BumpOptions() if options is None else options
    root_path = normalise_workspace_root(workspace_root)
    configuration = options.configuration
    if configuration is None:
        configuration = config_module.current_configuration()
    workspace = options.workspace
    if workspace is None:
        from lading.workspace import load_workspace

        workspace = load_workspace(root_path)
    base_options = BumpOptions(
        dry_run=options.dry_run,
        configuration=configuration,
        workspace=workspace,
    )

    excluded = set(configuration.bump.exclude)
    updated_crate_names = {
        crate.name for crate in workspace.crates if crate.name not in excluded
    }

    changed_manifests: list[Path] = []
    workspace_manifest = root_path / "Cargo.toml"
    workspace_dependency_sections = _workspace_dependency_sections(updated_crate_names)
    if _update_manifest(
        workspace_manifest,
        _WORKSPACE_SELECTORS,
        target_version,
        BumpOptions(
            dry_run=base_options.dry_run,
            configuration=base_options.configuration,
            workspace=base_options.workspace,
            dependency_sections=workspace_dependency_sections,
        ),
    ):
        changed_manifests.append(workspace_manifest)

    changed_manifests.extend(
        crate.manifest_path
        for crate in workspace.crates
        if _update_crate_manifest(
            crate,
            excluded,
            updated_crate_names,
            target_version,
            base_options,
        )
    )

    return _format_result_message(
        changed_manifests,
        target_version,
        dry_run=base_options.dry_run,
        workspace_root=root_path,
    )


def _update_crate_manifest(
    crate: WorkspaceCrate,
    excluded: typ.Collection[str],
    updated_crate_names: typ.Collection[str],
    target_version: str,
    options: BumpOptions,
) -> bool:
    """Apply updates for ``crate`` while respecting exclusion rules."""
    dependency_sections = _dependency_sections_for_crate(crate, updated_crate_names)
    if crate.name in excluded:
        selectors: tuple[tuple[str, ...], ...] = ()
    else:
        selectors = (("package",),)
    if not selectors and not dependency_sections:
        return False
    return _update_manifest(
        crate.manifest_path,
        selectors,
        target_version,
        BumpOptions(
            dry_run=options.dry_run,
            configuration=options.configuration,
            workspace=options.workspace,
            dependency_sections=dependency_sections,
        ),
    )


def _format_result_message(
    changed_manifests: typ.Sequence[Path],
    target_version: str,
    *,
    dry_run: bool,
    workspace_root: Path,
) -> str:
    """Summarise the bump outcome for CLI presentation."""
    if not changed_manifests:
        base = f"No manifest changes required; all versions already {target_version}."
        if dry_run:
            return f"Dry run; {base[0].lower()}{base[1:]}"
        return base

    count = len(changed_manifests)
    if dry_run:
        header = (
            f"Dry run; would update version to {target_version} in {count} manifest(s):"
        )
    else:
        header = f"Updated version to {target_version} in {count} manifest(s):"
    formatted_paths = [
        f"- {_format_manifest_path(manifest_path, workspace_root)}"
        for manifest_path in changed_manifests
    ]
    return "\n".join([header, *formatted_paths])


def _format_manifest_path(manifest_path: Path, workspace_root: Path) -> str:
    """Return ``manifest_path`` relative to ``workspace_root`` when possible."""
    try:
        relative = manifest_path.relative_to(workspace_root)
    except ValueError:
        return str(manifest_path)
    return str(relative)


def _update_manifest(
    manifest_path: Path,
    selectors: tuple[tuple[str, ...], ...],
    target_version: str,
    options: BumpOptions,
) -> bool:
    """Apply ``target_version`` to each table described by ``selectors``."""
    document = _parse_manifest(manifest_path)
    changed = False
    for selector in selectors:
        table = _select_table(document, selector)
        changed |= _assign_version(table, target_version)
    if options.dependency_sections:
        changed |= _update_dependency_sections(
            document, options.dependency_sections, target_version
        )
    if changed and not options.dry_run:
        _write_atomic_text(manifest_path, document.as_string())
    return changed


def _workspace_dependency_sections(
    updated_crates: typ.Collection[str],
) -> dict[str, set[str]]:
    """Return dependency names to update for the workspace manifest."""
    crate_names = {name for name in updated_crates if name}
    if not crate_names:
        return {}
    return {
        "dependencies": set(crate_names),
        "dev-dependencies": set(crate_names),
        "build-dependencies": set(crate_names),
    }


def _dependency_sections_for_crate(
    crate: WorkspaceCrate,
    updated_crates: typ.Collection[str],
) -> dict[str, set[str]]:
    """Return dependency names grouped by section for ``crate``."""
    if not crate.dependencies:
        return {}
    targets = {name for name in updated_crates if name}
    if not targets:
        return {}
    sections: dict[str, set[str]] = {}
    for dependency in crate.dependencies:
        if dependency.name not in targets:
            continue
        section = _DEPENDENCY_SECTION_BY_KIND.get(dependency.kind, "dependencies")
        # ``manifest_name`` preserves the dependency key used in the manifest.
        # When a crate is aliased (e.g. ``alpha-core = { package = "alpha" }``)
        # the workspace dependency name remains ``alpha`` while the manifest
        # entry becomes ``alpha-core``. Recording the manifest key ensures the
        # corresponding table entry can be located and updated.
        sections.setdefault(section, set()).add(dependency.manifest_name)
    return sections


def _update_dependency_sections(
    document: TOMLDocument,
    dependency_sections: typ.Mapping[str, typ.Collection[str]],
    target_version: str,
) -> bool:
    """Apply ``target_version`` to dependency entries for the provided sections."""
    changed = False
    for section, names in dependency_sections.items():
        if not names:
            continue
        table = _select_table(document, (section,))
        if table is None:
            continue
        changed |= _update_dependency_table(table, names, target_version)
    return changed


def _update_dependency_table(
    table: Table,
    dependency_names: typ.Collection[str],
    target_version: str,
) -> bool:
    """Update dependency requirements within ``table`` for ``dependency_names``."""
    changed = False
    for name in dependency_names:
        if name not in table:
            continue
        entry = table[name]
        if _update_dependency_entry(table, name, entry, target_version):
            changed = True
    return changed


def _update_dependency_entry(
    container: Table,
    key: str,
    entry: object,
    target_version: str,
) -> bool:
    """Update a dependency entry with ``target_version`` if it records a version."""
    if isinstance(entry, InlineTable | Table):
        return _assign_dependency_version_field(entry, target_version)
    replacement = _prepare_version_replacement(entry, target_version)
    if replacement is None:
        return False
    container[key] = replacement
    return True


def _assign_dependency_version_field(
    container: InlineTable | Table,
    target_version: str,
) -> bool:
    """Update the ``version`` key of ``container`` if present."""
    current = container.get("version")
    replacement = _prepare_version_replacement(current, target_version)
    if replacement is None:
        return False
    container["version"] = replacement
    return True


def _prepare_version_replacement(
    value: object,
    target_version: str,
) -> Item | None:
    """Return an updated requirement value when ``value`` stores a string."""
    current = _value_as_string(value)
    if current is None:
        return None
    replacement_text = _compose_requirement(current, target_version)
    if replacement_text == current:
        return None
    replacement = string(replacement_text)
    if isinstance(value, Item):
        with suppress(AttributeError):  # Preserve inline comments and whitespace trivia
            replacement._trivia = value._trivia  # type: ignore[attr-defined]
    return replacement


def _value_as_string(value: object) -> str | None:
    """Return ``value`` as a string if possible."""
    raw_value = value.value if isinstance(value, Item) else value
    if isinstance(raw_value, str):
        return raw_value
    return None


def _compose_requirement(existing: str, target_version: str) -> str:
    """Prefix ``target_version`` with any non-numeric operator from ``existing``."""
    match = _NON_DIGIT_PREFIX.match(existing)
    if not match:
        return target_version
    prefix = match.group(1)
    if not prefix or prefix == existing:
        return target_version
    return f"{prefix}{target_version}"


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
    existing_mode: int | None = None
    with suppress(FileNotFoundError):
        existing_mode = manifest_path.stat().st_mode
    fd, tmp_path = tempfile.mkstemp(
        dir=dirpath,
        prefix=f"{manifest_path.name}.",
        text=True,
    )
    try:
        if existing_mode is not None:
            with suppress(AttributeError):
                os.fchmod(fd, existing_mode)  # not available on Windows
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        Path(tmp_path).replace(manifest_path)
    finally:
        with suppress(FileNotFoundError):
            Path(tmp_path).unlink()
