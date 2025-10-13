"""Workspace graph models and builders for :mod:`lading`."""

from __future__ import annotations

import typing as typ
from collections import abc as cabc
from pathlib import Path

import msgspec
from tomlkit import parse
from tomlkit.exceptions import TOMLKitError

WORKSPACE_ROOT_MISSING_MSG = "cargo metadata missing 'workspace_root'"

ALLOWED_DEP_KINDS: typ.Final[set[str]] = {"normal", "dev", "build"}


class WorkspaceModelError(RuntimeError):
    """Raised when the workspace model cannot be constructed."""


class WorkspaceDependency(msgspec.Struct, frozen=True, kw_only=True):
    """Represents a dependency between two workspace crates."""

    package_id: str
    name: str
    kind: typ.Literal["normal", "dev", "build"] | None = None


class WorkspaceCrate(msgspec.Struct, frozen=True, kw_only=True):
    """Represents a single crate discovered in the workspace."""

    id: str
    name: str
    version: str
    manifest_path: Path
    root_path: Path
    publish: bool
    readme_is_workspace: bool
    dependencies: tuple[WorkspaceDependency, ...]


class WorkspaceGraph(msgspec.Struct, frozen=True, kw_only=True):
    """Represents the crates and relationships for a workspace."""

    workspace_root: Path
    crates: tuple[WorkspaceCrate, ...]

    @property
    def crates_by_name(self) -> dict[str, WorkspaceCrate]:
        """Return a name-indexed mapping of workspace crates."""
        return {crate.name: crate for crate in self.crates}


def load_workspace(
    workspace_root: Path | str | None = None,
) -> WorkspaceGraph:
    """Return a :class:`WorkspaceGraph` constructed from ``cargo metadata``."""
    from lading.workspace.metadata import load_cargo_metadata

    metadata = load_cargo_metadata(workspace_root)
    return build_workspace_graph(metadata)


def build_workspace_graph(
    metadata: cabc.Mapping[str, typ.Any],
) -> WorkspaceGraph:
    """Convert ``cargo metadata`` output into :class:`WorkspaceGraph`."""
    try:
        workspace_root_value = metadata["workspace_root"]
    except KeyError as exc:
        raise WorkspaceModelError(WORKSPACE_ROOT_MISSING_MSG) from exc
    workspace_root = _normalise_workspace_root(workspace_root_value)
    packages = _expect_sequence(metadata.get("packages"), "packages")
    workspace_member_ids = tuple(
        _expect_string(member, "workspace_members[]")
        for member in _expect_sequence(
            metadata.get("workspace_members"), "workspace_members"
        )
    )
    package_lookup = _index_workspace_packages(packages, workspace_member_ids)
    crates: list[WorkspaceCrate] = []
    workspace_member_set = set(workspace_member_ids)
    for member_id in workspace_member_ids:
        raw_package = package_lookup.get(member_id)
        if raw_package is None:
            message = f"workspace member {member_id!r} missing from package list"
            raise WorkspaceModelError(message)
        crates.append(
            _build_crate(
                raw_package,
                package_lookup,
                workspace_member_set,
            )
        )
    return WorkspaceGraph(workspace_root=workspace_root, crates=tuple(crates))


def _index_workspace_packages(
    packages: cabc.Sequence[cabc.Mapping[str, typ.Any]],
    workspace_member_ids: cabc.Sequence[str],
) -> dict[str, cabc.Mapping[str, typ.Any]]:
    """Return mapping of workspace member IDs to package metadata."""
    member_set = set(workspace_member_ids)
    index: dict[str, cabc.Mapping[str, typ.Any]] = {}
    for package in packages:
        package_id = _expect_string(package.get("id"), "packages[].id")
        if package_id not in member_set:
            continue
        index[package_id] = package
    return index


def _build_crate(
    package: cabc.Mapping[str, typ.Any],
    package_lookup: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
    workspace_member_ids: set[str],
) -> WorkspaceCrate:
    """Construct a :class:`WorkspaceCrate` from ``cargo metadata`` package data."""
    package_id = _expect_string(package.get("id"), "packages[].id")
    name = _expect_string(package.get("name"), f"package {package_id!r} name")
    version = _expect_string(package.get("version"), f"package {package_id!r} version")
    manifest_path = _normalise_manifest_path(
        package.get("manifest_path"), f"package {package_id!r} manifest_path"
    )
    dependencies = _build_dependencies(package, package_lookup, workspace_member_ids)
    publish = _coerce_publish_setting(package.get("publish"), package_id)
    readme_is_workspace = _manifest_uses_workspace_readme(manifest_path)
    root_path = manifest_path.parent
    return WorkspaceCrate(
        id=package_id,
        name=name,
        version=version,
        manifest_path=manifest_path,
        root_path=root_path,
        publish=publish,
        readme_is_workspace=readme_is_workspace,
        dependencies=dependencies,
    )


def _build_dependencies(
    package: cabc.Mapping[str, typ.Any],
    package_lookup: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
    workspace_member_ids: set[str],
) -> tuple[WorkspaceDependency, ...]:
    """Return dependencies that reference other workspace members."""
    raw_dependencies = _expect_sequence(
        package.get("dependencies"),
        f"package {package.get('id')!r} dependencies",
        allow_none=True,
    )
    if raw_dependencies is None:
        return ()
    return tuple(
        dependency
        for dependency in (
            _as_workspace_dependency(entry, package_lookup, workspace_member_ids)
            for entry in raw_dependencies
        )
        if dependency is not None
    )


def _validate_dependency_mapping(
    entry: cabc.Mapping[str, typ.Any] | object,
) -> cabc.Mapping[str, typ.Any]:
    """Return ``entry`` as a mapping or raise if it is not."""
    if not isinstance(entry, cabc.Mapping):
        message = "dependency entries must be mappings"
        raise WorkspaceModelError(message)
    return entry


def _lookup_workspace_target(
    entry: cabc.Mapping[str, typ.Any],
    package_lookup: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
    workspace_member_ids: set[str],
) -> tuple[str, str] | None:
    """Return the dependency target id and name when in the workspace."""
    target_id = entry.get("package")
    if not isinstance(target_id, str) or target_id not in workspace_member_ids:
        return None
    target_package = package_lookup.get(target_id)
    if target_package is None:
        return None
    target_name = _expect_string(
        target_package.get("name"), f"package {target_id!r} name"
    )
    return target_id, target_name


def _validate_dependency_kind(
    entry: cabc.Mapping[str, typ.Any],
) -> typ.Literal["normal", "dev", "build"] | None:
    """Return a validated dependency kind literal when present."""
    kind_value = entry.get("kind")
    if kind_value is None:
        return None
    if not isinstance(kind_value, str):
        message = (
            f"dependency kind must be string; received {type(kind_value).__name__}"
        )
        raise WorkspaceModelError(message)
    if kind_value not in ALLOWED_DEP_KINDS:
        message = f"unsupported dependency kind {kind_value!r}"
        raise WorkspaceModelError(message)
    return typ.cast("typ.Literal['normal', 'dev', 'build']", kind_value)


def _as_workspace_dependency(
    entry: cabc.Mapping[str, typ.Any] | object,
    package_lookup: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
    workspace_member_ids: set[str],
) -> WorkspaceDependency | None:
    """Convert ``entry`` into a :class:`WorkspaceDependency` when possible."""
    dependency = _validate_dependency_mapping(entry)
    target = _lookup_workspace_target(dependency, package_lookup, workspace_member_ids)
    if target is None:
        return None
    target_id, target_name = target
    kind_literal = _validate_dependency_kind(dependency)
    return WorkspaceDependency(
        package_id=target_id,
        name=target_name,
        kind=kind_literal,
    )


def _normalise_workspace_root(value: object) -> Path:
    """Return ``value`` as an absolute workspace root path."""
    if not isinstance(value, str | Path):
        message = (
            f"workspace_root must be a path string; received {type(value).__name__}"
        )
        raise WorkspaceModelError(message)
    from lading.utils.path import normalise_workspace_root

    return normalise_workspace_root(value)


def _normalise_manifest_path(value: object, field_name: str) -> Path:
    """Return ``value`` as an absolute :class:`Path` to a manifest."""
    if not isinstance(value, str | Path):
        message = f"{field_name} must be a path string; received {type(value).__name__}"
        raise WorkspaceModelError(message)
    path_value = Path(value).expanduser()
    return path_value.resolve(strict=False)


def _expect_sequence(
    value: object,
    field_name: str,
    *,
    allow_none: bool = False,
) -> cabc.Sequence[object] | None:
    """Ensure ``value`` is a sequence (optionally ``None``)."""
    if value is None:
        if allow_none:
            return None
        message = f"{field_name} must be a sequence"
        raise WorkspaceModelError(message)
    if isinstance(value, cabc.Sequence) and not isinstance(
        value, str | bytes | bytearray
    ):
        return value
    message = f"{field_name} must be a sequence; received {type(value).__name__}"
    raise WorkspaceModelError(message)


def _expect_string(value: object, field_name: str) -> str:
    """Return ``value`` when it is a string, otherwise raise an error."""
    if isinstance(value, str):
        return value
    message = f"{field_name} must be a string; received {type(value).__name__}"
    raise WorkspaceModelError(message)


def _coerce_publish_setting(value: object, package_id: str) -> bool:
    """Return whether ``package_id`` should be considered publishable."""
    if value is None:
        return True
    if value is False:
        return False
    if value is True:
        return True
    if isinstance(value, cabc.Sequence) and not isinstance(
        value, str | bytes | bytearray
    ):
        return bool(tuple(value))
    message = (
        f"publish setting for package {package_id!r} must be false, a list, or null"
    )
    raise WorkspaceModelError(message)


def _manifest_uses_workspace_readme(manifest_path: Path) -> bool:
    """Return ``True`` when ``readme.workspace`` is set in ``manifest_path``."""
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        message = f"manifest not found: {manifest_path}"
        raise WorkspaceModelError(message) from exc
    try:
        document = parse(text)
    except TOMLKitError as exc:
        message = f"failed to parse manifest {manifest_path}: {exc}"
        raise WorkspaceModelError(message) from exc
    package_table = document.get("package")
    if not isinstance(package_table, cabc.Mapping):
        return False
    readme_value = package_table.get("readme")
    if isinstance(readme_value, cabc.Mapping):
        workspace_flag = readme_value.get("workspace")
        return bool(workspace_flag)
    return False
