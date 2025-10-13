"""Unit coverage for placeholder command implementations."""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from lading import config as config_module
from lading.commands import bump, publish
from lading.utils import normalise_workspace_root
from lading.workspace import WorkspaceCrate, WorkspaceDependency, WorkspaceGraph


def _make_config() -> config_module.LadingConfig:
    """Create a representative configuration instance for placeholder tests."""
    return config_module.LadingConfig(
        bump=config_module.BumpConfig(doc_files=("README.md",)),
        publish=config_module.PublishConfig(strip_patches="all"),
    )


def _make_workspace(root: Path) -> WorkspaceGraph:
    """Construct a representative workspace graph for placeholder tests."""
    crate_path = root / "crate"
    crate = WorkspaceCrate(
        id="crate-id",
        name="crate",
        version="0.1.0",
        manifest_path=crate_path / "Cargo.toml",
        root_path=crate_path,
        publish=True,
        readme_is_workspace=False,
        dependencies=(WorkspaceDependency(package_id="dep-id", name="dep", kind=None),),
    )
    dependency = WorkspaceCrate(
        id="dep-id",
        name="dep",
        version="0.1.0",
        manifest_path=(root / "dep" / "Cargo.toml"),
        root_path=root / "dep",
        publish=False,
        readme_is_workspace=True,
        dependencies=(),
    )
    return WorkspaceGraph(workspace_root=root, crates=(crate, dependency))


@pytest.mark.parametrize(
    "command",
    [bump.run, publish.run],
)
def test_command_run_normalises_paths(
    command: typ.Callable[[Path, config_module.LadingConfig, WorkspaceGraph], str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure the placeholder commands resolve to absolute paths."""
    workspace = Path("workspace")
    monkeypatch.chdir(tmp_path)
    expected = normalise_workspace_root(workspace)
    graph = _make_workspace(expected)
    message = command(workspace, _make_config(), graph)
    assert str(expected) in message


@pytest.mark.parametrize(
    "command",
    [bump.run, publish.run],
)
def test_command_run_fallbacks_to_current_configuration(
    command: typ.Callable[[Path], str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Commands fall back to the active configuration when none is provided."""
    workspace = Path("workspace")
    monkeypatch.chdir(tmp_path)
    fallback_config = _make_config()
    monkeypatch.setattr(config_module, "current_configuration", lambda: fallback_config)
    expected = normalise_workspace_root(workspace)
    graph = _make_workspace(expected)
    monkeypatch.setattr("lading.workspace.load_workspace", lambda root: graph)
    message = command(workspace)
    assert str(expected) in message


def test_bump_run_mentions_command(tmp_path: Path) -> None:
    """The bump placeholder response includes the command name."""
    graph = _make_workspace(tmp_path.resolve())
    message = bump.run(tmp_path, _make_config(), graph)
    assert message == (
        "bump placeholder invoked for "
        f"{tmp_path.resolve()} (crates: 2 crates, doc files: README.md)"
    )


def test_publish_run_mentions_command(tmp_path: Path) -> None:
    """The publish placeholder response includes the command name."""
    graph = _make_workspace(tmp_path.resolve())
    message = publish.run(tmp_path, _make_config(), graph)
    assert message == (
        "publish placeholder invoked for "
        f"{tmp_path.resolve()} (crates: 2 crates, strip patches: all)"
    )
