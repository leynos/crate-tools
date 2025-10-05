"""Unit tests for the lading CLI scaffolding."""

from __future__ import annotations

import os
import typing as typ

import pytest

from lading import cli
from lading.commands import bump as bump_command
from lading.commands import publish as publish_command
from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType


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


def test_extract_workspace_override_requires_value_equals() -> None:
    """Reject ``--workspace-root=`` when no value is supplied."""
    with pytest.raises(SystemExit):
        cli._extract_workspace_override(["--workspace-root="])


def test_normalise_workspace_root_defaults_to_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default workspace resolution uses the current working directory."""
    monkeypatch.chdir(tmp_path)
    resolved = normalise_workspace_root(None)
    assert resolved == tmp_path.resolve()


@pytest.mark.parametrize(
    ("command_module", "command_name", "placeholder_text", "cli_args"),
    [
        (
            bump_command,
            "bump",
            "bump placeholder",
            ["--workspace-root", "{tmp_path}", "bump"],
        ),
        (
            publish_command,
            "publish",
            "publish placeholder",
            ["publish", "--workspace-root", "{tmp_path}"],
        ),
    ],
)
def test_main_dispatches_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command_module: ModuleType,
    command_name: str,
    placeholder_text: str,
    cli_args: list[str],
) -> None:
    """Route subcommands through their placeholder implementations."""
    called: dict[str, Path] = {}

    def fake_run(workspace_root: Path) -> str:
        called["workspace_root"] = workspace_root
        return placeholder_text

    monkeypatch.setattr(command_module, "run", fake_run)
    args = [arg.replace("{tmp_path}", str(tmp_path)) for arg in cli_args]
    assert command_name in args
    exit_code = cli.main(args)
    assert exit_code == 0
    assert called["workspace_root"] == tmp_path.resolve()
    captured = capsys.readouterr()
    assert placeholder_text in captured.out


def test_main_handles_missing_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return an error when no subcommand is provided."""
    exit_code = cli.main([])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Usage" in captured.out


def test_main_handles_invalid_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report an error when the subcommand is unknown."""
    exit_code = cli.main(["invalid"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "Unknown command" in captured.out


@pytest.mark.parametrize(
    ("exception", "expected_exit_code", "expected_message"),
    [
        (KeyboardInterrupt(), 130, "Operation cancelled"),
        (RuntimeError("boom"), 1, "Unexpected error"),
    ],
)
def test_main_handles_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    exception: BaseException,
    expected_exit_code: int,
    expected_message: str,
) -> None:
    """Handle exceptions during command execution."""

    def boom(_: typ.Sequence[str]) -> int:
        raise exception

    monkeypatch.setattr(cli, "_dispatch_and_print", boom)
    exit_code = cli.main(["bump", "--workspace-root", str(tmp_path)])
    assert exit_code == expected_exit_code
    captured = capsys.readouterr()
    assert expected_message in captured.err


def test_cyclopts_invoke_uses_workspace_env(tmp_path: Path) -> None:
    """Invoke the Cyclopts app directly with workspace override propagation."""
    result = cli.app(["bump", "--workspace-root", str(tmp_path)])
    assert result == f"bump placeholder invoked for {tmp_path.resolve()}"


def test_workspace_env_sets_and_restores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the workspace variable only exists while the context is active."""
    monkeypatch.delenv(cli.WORKSPACE_ROOT_ENV_VAR, raising=False)
    with cli._workspace_env(tmp_path):
        assert os.environ[cli.WORKSPACE_ROOT_ENV_VAR] == str(tmp_path)
    assert cli.WORKSPACE_ROOT_ENV_VAR not in os.environ
