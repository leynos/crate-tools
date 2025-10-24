"""BDD steps focused on the bump subcommand."""

from __future__ import annotations

import typing as typ

from pytest_bdd import parsers, then, when

from . import fixtures as _fixtures  # noqa: F401

if typ.TYPE_CHECKING:
    from pathlib import Path

    from .test_common_steps import _run_cli  # noqa: F401


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
    from .test_common_steps import _run_cli

    return _run_cli(repo_root, workspace_directory, "bump", version)


@when(
    parsers.parse("I invoke lading bump {version} with that workspace using --dry-run"),
    target_fixture="cli_run",
)
def when_invoke_lading_bump_dry_run(
    version: str,
    workspace_directory: Path,
    repo_root: Path,
) -> dict[str, typ.Any]:
    """Execute the bump CLI in dry-run mode via ``python -m``."""
    from .test_common_steps import _run_cli

    return _run_cli(repo_root, workspace_directory, "bump", version, "--dry-run")


@then(parsers.parse('the bump command reports manifest updates for "{version}"'))
def then_command_reports_workspace(cli_run: dict[str, typ.Any], version: str) -> None:
    """Assert that the bump command reports the updated manifests."""
    assert cli_run["returncode"] == 0
    stdout = cli_run["stdout"]
    assert "Updated version to " in stdout
    assert version in stdout


@then(parsers.parse('the bump command reports no manifest changes for "{version}"'))
def then_command_reports_no_changes(
    cli_run: dict[str, typ.Any],
    version: str,
) -> None:
    """Assert that the bump command reports that no updates were required."""
    assert cli_run["returncode"] == 0
    stdout = cli_run["stdout"]
    assert "No manifest changes required" in stdout
    assert f"already {version}" in stdout


@then(parsers.parse('the bump command reports a dry-run plan for "{version}"'))
def then_command_reports_dry_run(
    cli_run: dict[str, typ.Any],
    version: str,
) -> None:
    """Assert that the bump command reports the dry-run summary."""
    assert cli_run["returncode"] == 0
    stdout = cli_run["stdout"]
    assert "Dry run;" in stdout
    assert f"would update version to {version}" in stdout


@then(parsers.parse('the bump command reports an invalid version error for "{version}"'))
def then_bump_reports_invalid_version(
    cli_run: dict[str, typ.Any], version: str
) -> None:
    """Assert that invalid versions cause the command to fail with details."""
    assert cli_run["returncode"] == 1
    stderr = cli_run["stderr"]
    assert f"Invalid version argument '{version}'" in stderr


@then(parsers.parse('the CLI output lists manifest paths "{first}" and "{second}"'))
def then_cli_output_lists_manifest_paths(
    cli_run: dict[str, typ.Any],
    first: str,
    second: str,
) -> None:
    """Assert that the CLI output lists the expected manifest paths."""
    assert cli_run["returncode"] == 0
    expected_lines = [first, second]
    stdout_lines = [line.strip() for line in cli_run["stdout"].splitlines()]
    manifest_lines = [line for line in stdout_lines if line.startswith("- ")]
    assert manifest_lines == expected_lines


@then(parsers.parse('the CLI output lists documentation path "{expected}"'))
def then_cli_output_lists_documentation_path(
    cli_run: dict[str, typ.Any], expected: str
) -> None:
    """Assert that the CLI output includes ``expected`` as a documentation line."""
    assert cli_run["returncode"] == 0
    stdout_lines = [line.strip() for line in cli_run["stdout"].splitlines()]
    assert expected in stdout_lines


@then(parsers.parse('the documentation file "{relative_path}" contains "{expected}"'))
def then_documentation_contains(
    cli_run: dict[str, typ.Any], relative_path: str, expected: str
) -> None:
    """Assert that ``expected`` appears in the specified documentation file."""
    doc_path = cli_run["workspace"] / relative_path
    normalised_expected = expected.replace(r"\"", '"')
    contents = doc_path.read_text(encoding="utf-8")
    assert normalised_expected in contents
