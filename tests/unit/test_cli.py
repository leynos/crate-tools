"""Unit tests for the lading CLI scaffolding."""

from __future__ import annotations

import typing as typ

import pytest

from lading import cli
from lading.commands import bump as bump_command
from lading.commands import publish as publish_command

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("tokens", "expected_workspace", "expected_remaining"),
    [
        ([], None, []),
        (["bump"], None, ["bump"]),
        (["--workspace-root", "workspace", "publish"], "workspace", ["publish"]),
        (["--workspace-root=workspace", "bump"], "workspace", ["bump"]),
        (["bump", "--workspace-root", "workspace"], "workspace", ["bump"]),
        (
            [
                "--workspace-root=first",
                "--workspace-root",
                "second",
                "publish",
            ],
            "second",
            ["publish"],
        ),
    ],
)
def test_extract_workspace_override(
    tokens: typ.Sequence[str],
    expected_workspace: str | None,
    expected_remaining: list[str],
) -> None:
    """Extract workspace overrides from CLI tokens."""
    workspace, remaining = cli._extract_workspace_override(tokens)
    assert workspace == expected_workspace
    assert remaining == expected_remaining


def test_extract_workspace_override_requires_value() -> None:
    """Require a value whenever ``--workspace-root`` appears."""
    with pytest.raises(SystemExit):
        cli._extract_workspace_override(["--workspace-root"])


def test_main_dispatches_bump(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Route the bump subcommand through the placeholder implementation."""
    called: dict[str, Path] = {}

    def fake_run(workspace_root: Path) -> str:
        called["workspace_root"] = workspace_root
        return "bump placeholder"

    monkeypatch.setattr(bump_command, "run", fake_run)
    exit_code = cli.main(["--workspace-root", str(tmp_path), "bump"])
    assert exit_code == 0
    assert called["workspace_root"] == tmp_path.resolve()
    captured = capsys.readouterr()
    assert "bump placeholder" in captured.out


def test_main_dispatches_publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Route the publish subcommand through the placeholder implementation."""
    called: dict[str, Path] = {}

    def fake_run(workspace_root: Path) -> str:
        called["workspace_root"] = workspace_root
        return "publish placeholder"

    monkeypatch.setattr(publish_command, "run", fake_run)
    exit_code = cli.main(["publish", "--workspace-root", str(tmp_path)])
    assert exit_code == 0
    assert called["workspace_root"] == tmp_path.resolve()
    captured = capsys.readouterr()
    assert "publish placeholder" in captured.out


def test_cyclopts_invoke_uses_workspace_env(tmp_path: Path) -> None:
    """Invoke the Cyclopts app directly with workspace override propagation."""
    result = cli.app(["bump", "--workspace-root", str(tmp_path)])
    assert result == f"bump placeholder invoked for {tmp_path.resolve()}"
