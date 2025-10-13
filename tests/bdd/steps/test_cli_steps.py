"""Behavioural tests for the initial lading CLI scaffolding."""

from __future__ import annotations

import json
import subprocess
import sys
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from cmd_mox import CmdMox

from pytest_bdd import given, parsers, scenarios, then, when
from tomlkit import parse as parse_toml

from lading import config as config_module
from tests.helpers.workspace_helpers import install_cargo_stub

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


@given("cargo metadata describes a sample workspace")
def given_cargo_metadata_sample(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub ``cargo metadata`` for CLI behavioural tests."""
    install_cargo_stub(cmd_mox, monkeypatch)
    crate_dir = workspace_directory / "crates" / "alpha"
    crate_dir.mkdir(parents=True)
    manifest_path = crate_dir / "Cargo.toml"
    workspace_manifest = workspace_directory / "Cargo.toml"
    workspace_manifest.write_text(
        """
        [workspace]
        members = ["crates/alpha"]

        [workspace.package]
        version = "0.1.0"
        """
    )
    manifest_path.write_text(
        """
        [package]
        name = "alpha"
        version = "0.1.0"
        readme.workspace = true
        """
    )
    payload = {
        "workspace_root": str(workspace_directory),
        "packages": [
            {
                "name": "alpha",
                "version": "0.1.0",
                "id": "alpha-id",
                "manifest_path": str(manifest_path),
                "dependencies": [],
                "publish": None,
            }
        ],
        "workspace_members": ["alpha-id"],
    }
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )


def _run_cli(
    repo_root: Path,
    workspace_directory: Path,
    *command_args: str,
) -> dict[str, typ.Any]:
    command = [
        sys.executable,
        "-m",
        "lading.cli",
        "--workspace-root",
        str(workspace_directory),
    ]
    command.extend(command_args)
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


@when(
    parsers.parse("I invoke lading bump {version} with that workspace"),
    target_fixture="cli_run",
)
def when_invoke_lading_bump(
    version: str,
    workspace_directory: Path,
    repo_root: Path,
) -> dict[str, typ.Any]:
    """Execute the bump CLI via ``python -m`` and capture the result."""
    return _run_cli(repo_root, workspace_directory, "bump", version)


@when("I invoke lading publish with that workspace", target_fixture="cli_run")
def when_invoke_lading_publish(
    workspace_directory: Path,
    repo_root: Path,
) -> dict[str, typ.Any]:
    """Execute the publish CLI via ``python -m`` and capture the result."""
    return _run_cli(repo_root, workspace_directory, "publish")


@then(parsers.parse('the bump command reports manifest updates for "{version}"'))
def then_command_reports_workspace(cli_run: dict[str, typ.Any], version: str) -> None:
    """Assert that the bump command reports the updated manifests."""
    assert cli_run["returncode"] == 0
    stdout = cli_run["stdout"]
    assert f"Updated version to {version}" in stdout


@then(parsers.parse('the workspace manifest version is "{version}"'))
def then_workspace_manifest_version(
    cli_run: dict[str, typ.Any],
    version: str,
) -> None:
    """Validate the workspace manifest was updated to ``version``."""
    manifest_path = cli_run["workspace"] / "Cargo.toml"
    document = parse_toml(manifest_path.read_text())
    workspace_package = document["workspace"]["package"]
    assert workspace_package["version"] == version


@then(parsers.parse('the crate "{crate_name}" manifest version is "{version}"'))
def then_crate_manifest_version(
    cli_run: dict[str, typ.Any],
    crate_name: str,
    version: str,
) -> None:
    """Validate the crate manifest was updated to ``version``."""
    manifest_path = cli_run["workspace"] / "crates" / crate_name / "Cargo.toml"
    document = parse_toml(manifest_path.read_text())
    assert document["package"]["version"] == version


@then("the publish command reports the workspace path, crate count, and strip patches")
def then_publish_reports_workspace(cli_run: dict[str, typ.Any]) -> None:
    """Assert that the publish placeholder message mentions the workspace."""
    assert cli_run["returncode"] == 0
    workspace = cli_run["workspace"]
    stdout = cli_run["stdout"]
    assert f"publish placeholder invoked for {workspace}" in stdout
    assert "(crates: 1 crate, strip patches: all)" in stdout


@then("the CLI reports a missing configuration error")
def then_cli_reports_missing_configuration(cli_run: dict[str, typ.Any]) -> None:
    """Assert the CLI surfaces missing configuration errors."""
    assert cli_run["returncode"] == 1
    stderr = cli_run["stderr"]
    expected_path = cli_run["workspace"] / config_module.CONFIG_FILENAME
    assert (
        f"Configuration error: Configuration file not found: {expected_path}" in stderr
    )
