"""Behavioural tests for the initial lading CLI scaffolding."""

from __future__ import annotations

import subprocess
import sys
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

from pytest_bdd import given, scenarios, then, when

from lading import config as config_module

scenarios("../features/cli.feature")


@given("a workspace directory with configuration", target_fixture="workspace_directory")
def given_workspace_directory(tmp_path: Path) -> Path:
    """Provide a temporary workspace root for CLI exercises."""
    config_path = tmp_path / config_module.CONFIG_FILENAME
    config_path.write_text(
        '[bump]\ndoc_files = ["README.md"]\n\n[publish]\nstrip_patches = "all"\n'
    )
    return tmp_path


@given(
    "a workspace directory without configuration",
    target_fixture="workspace_directory",
)
def given_workspace_without_configuration(tmp_path: Path) -> Path:
    """Provide a workspace root without a configuration file."""
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


@then("the command reports the workspace path and doc files")
def then_command_reports_workspace(cli_run: dict[str, typ.Any]) -> None:
    """Assert that the placeholder message mentions the workspace."""
    assert cli_run["returncode"] == 0
    workspace = cli_run["workspace"]
    stdout = cli_run["stdout"]
    assert f"bump placeholder invoked for {workspace}" in stdout
    assert "(doc files: README.md)" in stdout


@then("the publish command reports the workspace path and strip patches")
def then_publish_reports_workspace(cli_run: dict[str, typ.Any]) -> None:
    """Assert that the publish placeholder message mentions the workspace."""
    assert cli_run["returncode"] == 0
    workspace = cli_run["workspace"]
    stdout = cli_run["stdout"]
    assert f"publish placeholder invoked for {workspace}" in stdout
    assert "(strip patches: all)" in stdout


@then("the CLI reports a missing configuration error")
def then_cli_reports_missing_configuration(cli_run: dict[str, typ.Any]) -> None:
    """Assert the CLI surfaces missing configuration errors."""
    assert cli_run["returncode"] == 1
    stderr = cli_run["stderr"]
    expected_path = cli_run["workspace"] / config_module.CONFIG_FILENAME
    assert (
        f"Configuration error: Configuration file not found: {expected_path}" in stderr
    )
