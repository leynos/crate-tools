"""BDD steps focused on the publish subcommand."""

from __future__ import annotations

import dataclasses as dc
import typing as typ
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when

from lading.commands import publish
from lading.workspace import metadata as metadata_module

from . import config_fixtures as _config_fixtures  # noqa: F401
from . import manifest_fixtures as _manifest_fixtures  # noqa: F401
from . import metadata_fixtures as _metadata_fixtures  # noqa: F401

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

    from .test_common_steps import _run_cli  # noqa: F401
else:
    CmdMox = typ.Any  # type: ignore[assignment]


@dc.dataclass(frozen=True, slots=True)
class _CommandResponse:
    """Describe the outcome of a mocked command invocation."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


@pytest.fixture
def preflight_overrides() -> dict[tuple[str, ...], _CommandResponse]:
    """Provide per-scenario overrides for publish pre-flight commands."""

    return {}


@given("cmd-mox IPC socket is unset")
def given_cmd_mox_socket_unset(
    monkeypatch: pytest.MonkeyPatch, cmd_mox: CmdMox
) -> None:
    """Ensure cmd-mox stub usage fails due to a missing socket variable."""
    from cmd_mox import environment as env_mod

    del cmd_mox
    monkeypatch.delenv(env_mod.CMOX_IPC_SOCKET_ENV, raising=False)
    monkeypatch.setenv(metadata_module.CMD_MOX_STUB_ENV_VAR, "1")


@when(
    "I run publish pre-flight checks for that workspace",
    target_fixture="preflight_result",
)
def when_run_publish_preflight_checks(workspace_directory: Path) -> dict[str, typ.Any]:
    """Execute publish pre-flight checks directly and capture failures."""
    error: publish.PublishPreflightError | None = None
    try:
        publish._run_preflight_checks(workspace_directory, allow_dirty=False)
    except publish.PublishPreflightError as exc:
        error = exc
    return {"error": error}


def _register_preflight_commands(
    cmd_mox: CmdMox,
    overrides: dict[tuple[str, ...], _CommandResponse],
) -> None:
    """Install cmd-mox doubles for publish pre-flight commands."""

    defaults = {
        ("git", "status", "--porcelain"): _CommandResponse(exit_code=0),
        (
            "cargo",
            "check",
            "--workspace",
            "--all-targets",
        ): _CommandResponse(exit_code=0),
        (
            "cargo",
            "test",
            "--workspace",
            "--all-targets",
        ): _CommandResponse(exit_code=0),
    }
    defaults.update(overrides)
    for command, response in defaults.items():
        program, *args = command
        expectation_program = program
        expectation_args = tuple(args)
        if program == "cargo" and args and args[0] in {"check", "test"}:
            expectation_program = f"cargo::{args[0]}"
            expectation_args = tuple(args[1:])
        double = cmd_mox.stub(expectation_program)
        double.with_args(*expectation_args).returns(
            stdout=response.stdout,
            stderr=response.stderr,
            exit_code=response.exit_code,
        )


@when("I invoke lading publish with that workspace", target_fixture="cli_run")
def when_invoke_lading_publish(
    workspace_directory: Path,
    repo_root: Path,
    cmd_mox: CmdMox,
    preflight_overrides: dict[tuple[str, ...], _CommandResponse],
) -> dict[str, typ.Any]:
    """Execute the publish CLI via ``python -m`` and capture the result."""

    from .test_common_steps import _run_cli

    _register_preflight_commands(cmd_mox, preflight_overrides)
    return _run_cli(repo_root, workspace_directory, "publish")


@when(
    "I invoke lading publish with that workspace using --allow-dirty",
    target_fixture="cli_run",
)
def when_invoke_lading_publish_allow_dirty(
    workspace_directory: Path,
    repo_root: Path,
    cmd_mox: CmdMox,
    preflight_overrides: dict[tuple[str, ...], _CommandResponse],
) -> dict[str, typ.Any]:
    """Execute the publish CLI with ``--allow-dirty`` enabled."""

    from .test_common_steps import _run_cli

    _register_preflight_commands(cmd_mox, preflight_overrides)
    return _run_cli(repo_root, workspace_directory, "publish", "--allow-dirty")


@given("cargo check fails during publish pre-flight")
def given_cargo_check_fails(
    preflight_overrides: dict[tuple[str, ...], _CommandResponse],
) -> None:
    """Simulate a failing cargo check command."""

    preflight_overrides[("cargo", "check", "--workspace", "--all-targets")] = (
        _CommandResponse(exit_code=1, stderr="cargo check failed")
    )


@given("cargo test fails during publish pre-flight")
def given_cargo_test_fails(
    preflight_overrides: dict[tuple[str, ...], _CommandResponse],
) -> None:
    """Simulate a failing cargo test command."""

    preflight_overrides[("cargo", "test", "--workspace", "--all-targets")] = (
        _CommandResponse(exit_code=1, stderr="cargo test failed")
    )


@given("the workspace has uncommitted changes")
def given_workspace_dirty(
    preflight_overrides: dict[tuple[str, ...], _CommandResponse],
) -> None:
    """Simulate a dirty working tree for git status."""

    preflight_overrides[("git", "status", "--porcelain")] = _CommandResponse(
        exit_code=0,
        stdout=" M Cargo.toml\n",
    )


@then(parsers.parse('the publish command prints the publish plan for "{crate_name}"'))
def then_publish_prints_plan(cli_run: dict[str, typ.Any], crate_name: str) -> None:
    """Assert that the publish command emits a publication plan summary."""

    assert cli_run["returncode"] == 0
    workspace = cli_run["workspace"]
    lines = [line.strip() for line in cli_run["stdout"].splitlines() if line.strip()]
    assert lines[0] == f"Publish plan for {workspace}"
    assert "Strip patch strategy: all" in lines[1]
    assert f"- {crate_name} @ 0.1.0" in lines


@then(parsers.parse('the publish command lists crates in order "{crate_names}"'))
def then_publish_lists_crates_in_order(
    cli_run: dict[str, typ.Any], crate_names: str
) -> None:
    """Assert that publishable crates appear in the expected order."""

    expected = [name.strip() for name in crate_names.split(",") if name.strip()]
    lines = _publish_plan_lines(cli_run)
    header = f"Crates to publish ({len(expected)}):"
    assert header in lines
    section_index = lines.index(header)
    publish_lines: list[str] = []
    for line in lines[section_index + 1 :]:
        if not line.startswith("- "):
            break
        publish_lines.append(line[2:])
    actual = [entry.split(" @ ", 1)[0] for entry in publish_lines]
    assert actual == expected


@then("the publish command reports that no crates are publishable")
def then_publish_reports_none(cli_run: dict[str, typ.Any]) -> None:
    """Assert that the publish command highlights the empty publish list."""

    assert cli_run["returncode"] == 0
    lines = _publish_plan_lines(cli_run)
    assert "Crates to publish: none" in lines


def _publish_plan_lines(cli_run: dict[str, typ.Any]) -> list[str]:
    """Return trimmed publish plan output lines for ``cli_run``."""

    return [line.strip() for line in cli_run["stdout"].splitlines() if line.strip()]


def _extract_staging_root_from_plan(lines: list[str]) -> Path:
    """Return the staging root path parsed from publish plan ``lines``."""

    staging_line = next(
        (line for line in lines if line.startswith("Staged workspace at:")), None
    )
    assert staging_line is not None, "Staging location not found in publish plan output"
    return Path(staging_line.split(": ", 1)[1])


@then(
    parsers.parse('the publish command reports manifest-skipped crate "{crate_name}"')
)
def then_publish_reports_manifest_skip(
    cli_run: dict[str, typ.Any], crate_name: str
) -> None:
    """Assert the publish plan lists ``crate_name`` under manifest skips."""

    lines = _publish_plan_lines(cli_run)
    assert "Skipped (publish = false):" in lines
    section_index = lines.index("Skipped (publish = false):")
    skipped = lines[section_index + 1 :]
    assert f"- {crate_name}" in skipped


@then(
    parsers.parse(
        'the publish command reports configuration-skipped crate "{crate_name}"'
    )
)
def then_publish_reports_configuration_skip(
    cli_run: dict[str, typ.Any], crate_name: str
) -> None:
    """Assert the publish plan lists ``crate_name`` under configuration skips."""

    lines = _publish_plan_lines(cli_run)
    assert "Skipped via publish.exclude:" in lines
    section_index = lines.index("Skipped via publish.exclude:")
    skipped = lines[section_index + 1 :]
    assert f"- {crate_name}" in skipped


@then(
    parsers.parse(
        'the publish command reports configuration-skipped crates "{crate_names}"'
    )
)
def then_publish_reports_multiple_configuration_skips(
    cli_run: dict[str, typ.Any], crate_names: str
) -> None:
    """Assert the publish plan lists all configuration exclusions."""

    expected_names = [name.strip() for name in crate_names.split(",") if name.strip()]
    lines = _publish_plan_lines(cli_run)
    assert "Skipped via publish.exclude:" in lines
    section_index = lines.index("Skipped via publish.exclude:")
    skipped = lines[section_index + 1 :]
    for name in expected_names:
        assert f"- {name}" in skipped


@then(parsers.parse('the publish command reports missing exclusion "{name}"'))
def then_publish_reports_missing_exclusion(
    cli_run: dict[str, typ.Any], name: str
) -> None:
    """Assert the publish plan reports the missing exclusion ``name``."""

    lines = _publish_plan_lines(cli_run)
    assert "Configured exclusions not found in workspace:" in lines
    section_index = lines.index("Configured exclusions not found in workspace:")
    missing = lines[section_index + 1 :]
    assert f"- {name}" in missing


@then(parsers.parse('the publish command omits section "{header}"'))
def then_publish_omits_section(cli_run: dict[str, typ.Any], header: str) -> None:
    """Assert that the publish plan does not mention ``header``."""

    lines = _publish_plan_lines(cli_run)
    assert header not in lines


@then(
    parsers.parse(
        'the publish staging directory for crate "{crate_name}" '
        "contains the workspace README"
    )
)
def then_publish_staging_contains_readme(
    cli_run: dict[str, typ.Any], crate_name: str
) -> None:
    """Assert that staging propagated the workspace README into ``crate_name``."""

    lines = _publish_plan_lines(cli_run)
    staging_root = _extract_staging_root_from_plan(lines)
    staged_readme = staging_root / "crates" / crate_name / "README.md"
    assert staged_readme.exists()

    workspace_root = Path(cli_run["workspace"])
    source_readme = workspace_root / "README.md"
    assert source_readme.exists()
    assert staged_readme.read_text(encoding="utf-8") == source_readme.read_text(
        encoding="utf-8"
    )


@then(
    parsers.parse(
        'the publish plan lists copied workspace README for crate "{crate_name}"'
    )
)
def then_publish_lists_copied_readme(
    cli_run: dict[str, typ.Any], crate_name: str
) -> None:
    """Assert that the publish plan lists the staged README for ``crate_name``."""

    lines = _publish_plan_lines(cli_run)
    staging_root = _extract_staging_root_from_plan(lines)
    expected_relative = Path("crates") / crate_name / "README.md"
    expected_entry = f"- {expected_relative.as_posix()}"
    assert expected_entry in lines

    # The formatting helper reports relative paths when possible, so verify
    # that the corresponding staged README exists where the CLI claims.
    staged_readme = staging_root / expected_relative
    assert staged_readme.exists()


@then(
    "the publish pre-flight error contains "
    '"cmd-mox stub requested for publish pre-flight but CMOX_IPC_SOCKET is unset"'
)
def then_publish_preflight_reports_missing_socket(
    preflight_result: dict[str, typ.Any],
) -> None:
    """Assert that publish pre-flight checks report the missing socket."""
    error = preflight_result.get("error")
    assert isinstance(error, publish.PublishPreflightError)
    assert (
        "cmd-mox stub requested for publish pre-flight but CMOX_IPC_SOCKET is unset"
        in str(error)
    )
