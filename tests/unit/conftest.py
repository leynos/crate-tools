"""Test fixtures and helpers for :mod:`lading.commands.bump` unit tests."""

from __future__ import annotations

import dataclasses as dc
import textwrap
import typing as typ

from tomlkit import parse as parse_toml

from lading import config as config_module
from lading.workspace import WorkspaceCrate, WorkspaceDependency, WorkspaceGraph

if typ.TYPE_CHECKING:
    from pathlib import Path


@dc.dataclass(frozen=True, slots=True)
class _CrateSpec:
    """Specification for constructing workspace crates in tests."""

    name: str
    manifest_extra: str = ""
    dependencies: tuple[WorkspaceDependency, ...] = ()
    version: str = "0.1.0"


def _write_workspace_manifest(root: Path, members: tuple[str, ...]) -> Path:
    """Create a minimal workspace manifest with the provided members."""
    manifest = root / "Cargo.toml"
    entries = ", ".join(f'"{member}"' for member in members)
    manifest.write_text(
        "[workspace]\n"
        f"members = [{entries}]\n\n"
        "[workspace.package]\n"
        'version = "0.1.0"\n',
        encoding="utf-8",
    )
    return manifest


def _write_crate_manifest(
    manifest_path: Path,
    *,
    name: str,
    version: str,
    extra_sections: str = "",
) -> None:
    """Write a crate manifest with optional dependency sections."""
    content = textwrap.dedent(
        f"""
        [package]
        name = "{name}"
        version = "{version}"
        """
    ).lstrip()
    if extra_sections:
        content += "\n" + textwrap.dedent(extra_sections).strip() + "\n"
    manifest_path.write_text(content, encoding="utf-8")


def _build_workspace_with_internal_deps(
    root: Path, *, specs: tuple[_CrateSpec, ...]
) -> tuple[WorkspaceGraph, dict[str, Path]]:
    """Create a workspace populated with crates and return manifest paths."""
    root.mkdir(parents=True, exist_ok=True)
    members = tuple(f"crates/{spec.name}" for spec in specs)
    _write_workspace_manifest(root, members)

    manifests: dict[str, Path] = {}
    crates: list[WorkspaceCrate] = []
    for spec in specs:
        crate_dir = root / "crates" / spec.name
        crate_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = crate_dir / "Cargo.toml"
        _write_crate_manifest(
            manifest_path,
            name=spec.name,
            version=spec.version,
            extra_sections=spec.manifest_extra,
        )
        manifests[spec.name] = manifest_path
        crates.append(
            WorkspaceCrate(
                id=f"{spec.name}-id",
                name=spec.name,
                version=spec.version,
                manifest_path=manifest_path,
                root_path=crate_dir,
                publish=True,
                readme_is_workspace=False,
                dependencies=spec.dependencies,
            )
        )
    workspace = WorkspaceGraph(workspace_root=root, crates=tuple(crates))
    return workspace, manifests


def _make_workspace(tmp_path: Path) -> WorkspaceGraph:
    """Construct a workspace graph with two member crates."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    members = ("crates/alpha", "crates/beta")
    _write_workspace_manifest(tmp_path, members)
    crates: list[WorkspaceCrate] = []
    for member in members:
        crate_dir = tmp_path / member
        crate_dir.mkdir(parents=True)
        manifest_path = crate_dir / "Cargo.toml"
        manifest_path.write_text(
            f'[package]\nname = "{crate_dir.name}"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        crates.append(
            WorkspaceCrate(
                id=f"{crate_dir.name}-id",
                name=crate_dir.name,
                version="0.1.0",
                manifest_path=manifest_path,
                root_path=crate_dir,
                publish=True,
                readme_is_workspace=False,
                dependencies=(),
            )
        )
    return WorkspaceGraph(workspace_root=tmp_path, crates=tuple(crates))


def _load_version(path: Path, table: tuple[str, ...]) -> str:
    """Return the version string stored at ``table`` within ``path``."""
    document = parse_toml(path.read_text(encoding="utf-8"))
    current = document
    for key in table:
        current = current[key]
    return current["version"]


def _make_config(**kwargs: str | tuple[str, ...]) -> config_module.LadingConfig:
    """Construct a configuration instance for tests."""
    bump_config = config_module.BumpConfig(**kwargs)
    return config_module.LadingConfig(bump=bump_config)


def _create_alpha_crate(workspace_root: Path) -> WorkspaceCrate:
    """Create the alpha crate and return its workspace representation."""
    alpha_dir = workspace_root / "crates" / "alpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    alpha_manifest = alpha_dir / "Cargo.toml"
    alpha_manifest.write_text(
        '[package]\nname = "alpha"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return WorkspaceCrate(
        id="alpha-id",
        name="alpha",
        version="0.1.0",
        manifest_path=alpha_manifest,
        root_path=alpha_dir,
        publish=True,
        readme_is_workspace=False,
        dependencies=(),
    )


def _create_beta_crate_with_dependencies(
    workspace_root: Path, alpha_id: str
) -> WorkspaceCrate:
    """Create the beta crate with dependency entries referencing alpha."""
    beta_dir = workspace_root / "crates" / "beta"
    beta_dir.mkdir(parents=True, exist_ok=True)
    beta_manifest = beta_dir / "Cargo.toml"
    beta_manifest.write_text(
        textwrap.dedent(
            """
            [package]
            name = "beta"
            version = "0.1.0"

            [dependencies]
            alpha = "^0.1.0"

            [dev-dependencies]
            alpha = { version = "~0.1.0", path = "../alpha" }

            [build-dependencies.alpha]
            version = "0.1.0"
            path = "../alpha"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return WorkspaceCrate(
        id="beta-id",
        name="beta",
        version="0.1.0",
        manifest_path=beta_manifest,
        root_path=beta_dir,
        publish=True,
        readme_is_workspace=False,
        dependencies=(
            WorkspaceDependency(
                package_id=alpha_id,
                name="alpha",
                manifest_name="alpha",
                kind=None,
            ),
            WorkspaceDependency(
                package_id=alpha_id,
                name="alpha",
                manifest_name="alpha",
                kind="dev",
            ),
            WorkspaceDependency(
                package_id=alpha_id,
                name="alpha",
                manifest_name="alpha",
                kind="build",
            ),
        ),
    )
