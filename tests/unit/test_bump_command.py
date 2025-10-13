"""Unit tests for the :mod:`lading.commands.bump` module."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from tomlkit import parse as parse_toml

from lading import config as config_module
from lading.commands import bump
from lading.workspace import WorkspaceCrate, WorkspaceGraph

if typ.TYPE_CHECKING:
    import pytest


def _write_workspace_manifest(root: Path, members: list[str]) -> Path:
    """Create a minimal workspace manifest with the provided members."""
    manifest = root / "Cargo.toml"
    entries = ", ".join(f'"{member}"' for member in members)
    manifest.write_text(
        "[workspace]\n"
        f"members = [{entries}]\n\n"
        "[workspace.package]\n"
        'version = "0.1.0"\n'
    )
    return manifest


def _make_workspace(tmp_path: Path) -> WorkspaceGraph:
    """Construct a workspace graph with two member crates."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    members = ["crates/alpha", "crates/beta"]
    _write_workspace_manifest(tmp_path, members)
    crates: list[WorkspaceCrate] = []
    for member in members:
        crate_dir = tmp_path / member
        crate_dir.mkdir(parents=True)
        manifest_path = crate_dir / "Cargo.toml"
        manifest_path.write_text(
            f'[package]\nname = "{crate_dir.name}"\nversion = "0.1.0"\n'
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
    document = parse_toml(path.read_text())
    current = document
    for key in table:
        current = current[key]
    return current["version"]


def _make_config(**kwargs: str | tuple[str, ...]) -> config_module.LadingConfig:
    """Construct a configuration instance for tests."""
    bump_config = config_module.BumpConfig(**kwargs)
    return config_module.LadingConfig(bump=bump_config)


def test_run_updates_workspace_and_members(tmp_path: Path) -> None:
    """`bump.run` updates the workspace and member manifest versions."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    message = bump.run(
        tmp_path, "1.2.3", configuration=configuration, workspace=workspace
    )
    assert message == "Updated version to 1.2.3 in 3 manifest(s)."
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "1.2.3"
    for crate in workspace.crates:
        assert _load_version(crate.manifest_path, ("package",)) == "1.2.3"


def test_run_skips_excluded_crates(tmp_path: Path) -> None:
    """Crates listed in `bump.exclude` retain their original version."""
    workspace = _make_workspace(tmp_path)
    excluded = workspace.crates[0]
    configuration = _make_config(exclude=(excluded.name,))
    bump.run(tmp_path, "2.0.0", configuration=configuration, workspace=workspace)
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "2.0.0"
    assert _load_version(excluded.manifest_path, ("package",)) == "0.1.0"
    included = workspace.crates[1]
    assert _load_version(included.manifest_path, ("package",)) == "2.0.0"


def test_run_normalises_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command resolves the workspace root before applying updates."""
    workspace_root = tmp_path / "workspace-root"
    workspace = _make_workspace(workspace_root)
    configuration = _make_config()
    relative = Path("workspace-root")
    monkeypatch.chdir(tmp_path)
    bump.run(relative, "3.4.5", configuration=configuration, workspace=workspace)
    manifest_path = workspace_root / "Cargo.toml"
    assert _load_version(manifest_path, ("workspace", "package")) == "3.4.5"


def test_run_uses_loaded_configuration_and_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bump.run` loads the configuration and workspace when omitted."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    monkeypatch.setattr(config_module, "current_configuration", lambda: configuration)
    monkeypatch.setattr("lading.workspace.load_workspace", lambda root: workspace)
    bump.run(tmp_path, "9.9.9")
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "9.9.9"
