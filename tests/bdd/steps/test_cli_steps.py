"""Behavioural tests for the initial lading CLI scaffolding."""

from __future__ import annotations

import subprocess
import sys
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

from pytest_bdd import given, scenarios, then, when

scenarios("../features/cli.feature")


@given("a workspace directory", target_fixture="workspace_directory")
def given_workspace_directory(tmp_path: Path) -> Path:
    """Provide a temporary workspace root for CLI exercises."""
    return tmp_path


def _run_cli(
    cmd_mox: CmdMox,
    repo_root: Path,
    workspace_directory: Path,
    subcommand: str,
) -> dict[str, typ.Any]:
    command = [
        sys.executable,
        "-m",
        "lading.cli",
        "--workspace-root",
        str(workspace_directory),
        subcommand,
    ]
    cmd_mox.spy(sys.executable).passthrough()
    cmd_mox.spy(Path(sys.executable).name).passthrough()
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "workspace": workspace_directory.resolve(),
    }


@when("I invoke lading bump with that workspace", target_fixture="cli_run")
def when_invoke_lading_bump(
    cmd_mox: CmdMox,
    workspace_directory: Path,
    repo_root: Path,
) -> dict[str, typ.Any]:
    """Execute the bump CLI via ``python -m`` and capture the result."""
    return _run_cli(cmd_mox, repo_root, workspace_directory, "bump")


@when("I invoke lading publish with that workspace", target_fixture="cli_run")
def when_invoke_lading_publish(
    cmd_mox: CmdMox,
    workspace_directory: Path,
    repo_root: Path,
) -> dict[str, typ.Any]:
    """Execute the publish CLI via ``python -m`` and capture the result."""
    return _run_cli(cmd_mox, repo_root, workspace_directory, "publish")


@then("the command reports the workspace path")
def then_command_reports_workspace(cli_run: dict[str, typ.Any]) -> None:
    """Assert that the placeholder message mentions the workspace."""
    assert cli_run["returncode"] == 0
    workspace = cli_run["workspace"]
    assert f"bump placeholder invoked for {workspace}" in cli_run["stdout"]


@then("the publish command reports the workspace path")
def then_publish_reports_workspace(cli_run: dict[str, typ.Any]) -> None:
    """Assert that the publish placeholder message mentions the workspace."""
    assert cli_run["returncode"] == 0
    workspace = cli_run["workspace"]
    assert f"publish placeholder invoked for {workspace}" in cli_run["stdout"]
