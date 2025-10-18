"""Integration-focused unit tests for the :mod:`lading.commands.bump` module."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from tomlkit import parse as parse_toml

from lading import config as config_module
from lading.commands import bump
from lading.workspace import WorkspaceDependency, WorkspaceGraph

from tests.unit.conftest import (
    _CrateSpec,
    _build_workspace_with_internal_deps,
    _create_alpha_crate,
    _create_beta_crate_with_dependencies,
    _load_version,
    _make_config,
    _make_workspace,
    _write_workspace_manifest,
)

if typ.TYPE_CHECKING:
    import pytest


def test_run_updates_workspace_and_members(tmp_path: Path) -> None:
    """`bump.run` updates the workspace and member manifest versions."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    message = bump.run(
        tmp_path, "1.2.3", configuration=configuration, workspace=workspace
    )
    assert message.splitlines() == [
        "Updated version to 1.2.3 in 3 manifest(s):",
        "- Cargo.toml",
        "- crates/alpha/Cargo.toml",
        "- crates/beta/Cargo.toml",
    ]
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "1.2.3"
    for crate in workspace.crates:
        assert _load_version(crate.manifest_path, ("package",)) == "1.2.3"


def test_run_updates_root_package_section(tmp_path: Path) -> None:
    """The workspace manifest `[package]` section also receives the new version."""
    workspace = _make_workspace(tmp_path)
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        "[package]\n"
        'name = "workspace"\n'
        'version = "0.1.0"\n\n'
        "[workspace]\n"
        'members = ["crates/alpha", "crates/beta"]\n\n'
        "[workspace.package]\n"
        'version = "0.1.0"\n'
    )
    configuration = _make_config()
    bump.run(tmp_path, "7.8.9", configuration=configuration, workspace=workspace)
    assert _load_version(manifest_path, ("package",)) == "7.8.9"
    assert _load_version(manifest_path, ("workspace", "package")) == "7.8.9"


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


def test_run_updates_internal_dependency_versions(tmp_path: Path) -> None:
    """Internal dependency requirements are updated across dependency sections."""
    alpha_crate = _create_alpha_crate(tmp_path)
    beta_crate = _create_beta_crate_with_dependencies(tmp_path, alpha_crate.id)
    _write_workspace_manifest(
        tmp_path,
        [
            "crates/alpha",
            "crates/beta",
        ],
    )
    workspace = WorkspaceGraph(
        workspace_root=tmp_path, crates=(alpha_crate, beta_crate)
    )

    configuration = _make_config()
    bump.run(tmp_path, "1.2.3", configuration=configuration, workspace=workspace)

    beta_document = parse_toml(beta_crate.manifest_path.read_text(encoding="utf-8"))
    assert beta_document["dependencies"]["alpha"].value == "^1.2.3"
    dev_entry = beta_document["dev-dependencies"]["alpha"]
    assert dev_entry["version"].value == "~1.2.3"
    assert dev_entry["path"].value == "../alpha"
    build_entry = beta_document["build-dependencies"]["alpha"]
    assert build_entry["version"].value == "1.2.3"
    assert build_entry["path"].value == "../alpha"


def test_run_updates_renamed_internal_dependency_versions(tmp_path: Path) -> None:
    """Aliased workspace dependencies are updated using their manifest name."""
    workspace, manifests = _build_workspace_with_internal_deps(
        tmp_path,
        specs=(
            _CrateSpec(name="alpha"),
            _CrateSpec(
                name="beta",
                manifest_extra="""
                [dependencies]
                alpha-core = { package = "alpha", version = "^0.1.0" }
                """,
                dependencies=(
                    WorkspaceDependency(
                        package_id="alpha-id",
                        name="alpha",
                        manifest_name="alpha-core",
                        kind=None,
                    ),
                ),
            ),
        ),
    )

    configuration = _make_config()
    bump.run(tmp_path, "2.3.4", configuration=configuration, workspace=workspace)

    beta_manifest = manifests["beta"]
    beta_document = parse_toml(beta_manifest.read_text(encoding="utf-8"))
    dependency_entry = beta_document["dependencies"]["alpha-core"]
    assert dependency_entry["version"].value == "^2.3.4"
    assert dependency_entry["package"].value == "alpha"


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


def test_run_reports_when_versions_already_match(tmp_path: Path) -> None:
    """Return a descriptive message when manifests already match the target."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    target_version = "0.1.0"
    message = bump.run(
        tmp_path,
        target_version,
        configuration=configuration,
        workspace=workspace,
    )
    assert message == "No manifest changes required; all versions already 0.1.0."


def test_run_dry_run_reports_changes_without_modifying_files(tmp_path: Path) -> None:
    """Dry-running the command reports planned changes without touching manifests."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    manifest_paths = [
        tmp_path / "Cargo.toml",
        *[crate.manifest_path for crate in workspace.crates],
    ]
    original_contents = {
        path: path.read_text(encoding="utf-8") for path in manifest_paths
    }

    message = bump.run(
        tmp_path,
        "1.2.3",
        configuration=configuration,
        workspace=workspace,
        dry_run=True,
    )

    assert message.splitlines() == [
        "Dry run; would update version to 1.2.3 in 3 manifest(s):",
        "- Cargo.toml",
        "- crates/alpha/Cargo.toml",
        "- crates/beta/Cargo.toml",
    ]
    for path in manifest_paths:
        assert path.read_text(encoding="utf-8") == original_contents[path]


def test_run_dry_run_reports_no_changes_when_versions_match(tmp_path: Path) -> None:
    """Dry run still reports when no manifest updates are necessary."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    message = bump.run(
        tmp_path,
        "0.1.0",
        configuration=configuration,
        workspace=workspace,
        dry_run=True,
    )

    assert (
        message == "Dry run; no manifest changes required; all versions already 0.1.0."
    )
