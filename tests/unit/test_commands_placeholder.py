"""Unit coverage for placeholder command implementations."""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from lading import config as config_module
from lading.commands import bump, publish
from lading.utils import normalise_workspace_root


def _make_config() -> config_module.LadingConfig:
    """Create a representative configuration instance for placeholder tests."""
    return config_module.LadingConfig(
        bump=config_module.BumpConfig(doc_files=("README.md",)),
        publish=config_module.PublishConfig(strip_patches="all"),
    )


@pytest.mark.parametrize(
    "command",
    [bump.run, publish.run],
)
def test_command_run_normalises_paths(
    command: typ.Callable[[Path, config_module.LadingConfig], str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure the placeholder commands resolve to absolute paths."""
    workspace = Path("workspace")
    monkeypatch.chdir(tmp_path)
    message = command(workspace, _make_config())
    expected = normalise_workspace_root(workspace)
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
    message = command(workspace)
    expected = normalise_workspace_root(workspace)
    assert str(expected) in message


def test_bump_run_mentions_command(tmp_path: Path) -> None:
    """The bump placeholder response includes the command name."""
    message = bump.run(tmp_path, _make_config())
    assert message == (
        f"bump placeholder invoked for {tmp_path.resolve()} (doc files: README.md)"
    )


def test_publish_run_mentions_command(tmp_path: Path) -> None:
    """The publish placeholder response includes the command name."""
    message = publish.run(tmp_path, _make_config())
    assert message == (
        f"publish placeholder invoked for {tmp_path.resolve()} (strip patches: all)"
    )
