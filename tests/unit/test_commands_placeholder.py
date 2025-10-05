"""Unit coverage for placeholder command implementations."""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from lading.commands import bump, publish
from lading.utils import normalise_workspace_root


@pytest.mark.parametrize(
    "command",
    [bump.run, publish.run],
)
def test_command_run_normalises_paths(
    command: typ.Callable[[Path], str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure the placeholder commands resolve to absolute paths."""
    workspace = Path("workspace")
    monkeypatch.chdir(tmp_path)
    message = command(workspace)
    expected = normalise_workspace_root(workspace)
    assert message.endswith(str(expected))


def test_bump_run_mentions_command(tmp_path: Path) -> None:
    """The bump placeholder response includes the command name."""
    message = bump.run(tmp_path)
    assert message == f"bump placeholder invoked for {tmp_path.resolve()}"


def test_publish_run_mentions_command(tmp_path: Path) -> None:
    """The publish placeholder response includes the command name."""
    message = publish.run(tmp_path)
    assert message == f"publish placeholder invoked for {tmp_path.resolve()}"
