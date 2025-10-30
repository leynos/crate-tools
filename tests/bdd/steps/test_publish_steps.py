"""BDD steps focused on the publish subcommand."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from pytest_bdd import parsers, then, when

from . import config_fixtures as _config_fixtures  # noqa: F401
from . import manifest_fixtures as _manifest_fixtures  # noqa: F401
from . import metadata_fixtures as _metadata_fixtures  # noqa: F401

if typ.TYPE_CHECKING:
    from .test_common_steps import _run_cli  # noqa: F401


@when("I invoke lading publish with that workspace", target_fixture="cli_run")
def when_invoke_lading_publish(
    workspace_directory: Path,
    repo_root: Path,
) -> dict[str, typ.Any]:
    """Execute the publish CLI via ``python -m`` and capture the result."""
    from .test_common_steps import _run_cli

    return _run_cli(repo_root, workspace_directory, "publish")


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
    assert staging_line is not None
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
