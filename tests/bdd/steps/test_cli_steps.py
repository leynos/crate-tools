"""Behavioural tests for the initial lading CLI scaffolding."""

from __future__ import annotations

import dataclasses as dc
import json
import subprocess
import sys
import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from cmd_mox import CmdMox

from pytest_bdd import given, parsers, scenarios, then, when
from tomlkit import array, table
from tomlkit import parse as parse_toml
from tomlkit.items import InlineTable, Item, Table

from lading import config as config_module
from tests.helpers.workspace_helpers import install_cargo_stub

scenarios("../features/cli.feature")


@given("a workspace directory with configuration", target_fixture="workspace_directory")
def given_workspace_directory(tmp_path: Path) -> Path:
    """Provide a temporary workspace root for CLI exercises."""
    config_path = tmp_path / config_module.CONFIG_FILENAME
    config_path.write_text(
        '[bump]\n\n[publish]\nstrip_patches = "all"\n', encoding="utf-8"
    )
    return tmp_path


@given(parsers.parse('the workspace manifests record version "{version}"'))
def given_workspace_versions_match(
    workspace_directory: Path,
    version: str,
) -> None:
    """Ensure the workspace and member manifests record ``version``."""
    workspace_manifest = workspace_directory / "Cargo.toml"
    if not workspace_manifest.exists():
        message = f"Workspace manifest not found: {workspace_manifest}"
        raise AssertionError(message)
    workspace_document = parse_toml(workspace_manifest.read_text(encoding="utf-8"))
    workspace_document["workspace"]["package"]["version"] = version
    workspace_manifest.write_text(workspace_document.as_string(), encoding="utf-8")

    crate_manifest = workspace_directory / "crates" / "alpha" / "Cargo.toml"
    if not crate_manifest.exists():
        message = f"Crate manifest not found: {crate_manifest}"
        raise AssertionError(message)
    crate_document = parse_toml(crate_manifest.read_text(encoding="utf-8"))
    crate_document["package"]["version"] = version
    crate_manifest.write_text(crate_document.as_string(), encoding="utf-8")


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
        textwrap.dedent(
            """
            [workspace]
            members = ["crates/alpha"]

            [workspace.package]
            version = "0.1.0"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    manifest_path.write_text(
        """
        [package]
        name = "alpha"
        version = "0.1.0"
        readme.workspace = true
        """,
        encoding="utf-8",
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


@given(
    "cargo metadata describes a workspace with crates alpha and beta",
)
def given_cargo_metadata_two_crates(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata for a workspace containing two crates."""
    install_cargo_stub(cmd_mox, monkeypatch)
    crate_names = ("alpha", "beta")
    crate_entries = []
    members: list[str] = []
    for name in crate_names:
        crate_dir = workspace_directory / "crates" / name
        crate_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = crate_dir / "Cargo.toml"
        manifest_path.write_text(
            textwrap.dedent(
                f"""
                [package]
                name = "{name}"
                version = "0.1.0"
                readme.workspace = true
                """
            ).lstrip(),
            encoding="utf-8",
        )
        crate_entries.append(
            {
                "name": name,
                "version": "0.1.0",
                "id": f"{name}-id",
                "manifest_path": str(manifest_path),
                "dependencies": [],
                "publish": None,
            }
        )
        members.append(f"crates/{name}")
    workspace_manifest = workspace_directory / "Cargo.toml"
    members_literal = ", ".join(f'"{member}"' for member in members)
    workspace_manifest.write_text(
        textwrap.dedent(
            f"""
            [workspace]
            members = [{members_literal}]

            [workspace.package]
            version = "0.1.0"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    payload = {
        "workspace_root": str(workspace_directory),
        "packages": crate_entries,
        "workspace_members": [f"{name}-id" for name in crate_names],
    }
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )


def _create_test_crate(
    workspace_dir: Path,
    crate_name: str,
    version: str,
    dependencies_toml: str = "",
) -> Path:
    """Create a crate manifest under ``workspace_dir`` for behavioural fixtures."""
    crate_dir = workspace_dir / "crates" / crate_name
    crate_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = crate_dir / "Cargo.toml"

    sections = [
        textwrap.dedent(
            f"""
            [package]
            name = "{crate_name}"
            version = "{version}"
            """
        ).strip()
    ]
    if dependencies_toml:
        sections.append(textwrap.dedent(dependencies_toml).strip())

    manifest_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return manifest_path


def _build_package_metadata(
    name: str,
    version: str,
    manifest_path: Path,
    dependencies: list[dict[str, str]] | None = None,
) -> dict:
    """Construct the minimal package metadata payload for ``cargo metadata``."""
    return {
        "name": name,
        "version": version,
        "id": f"{name}-id",
        "manifest_path": str(manifest_path),
        "dependencies": [] if dependencies is None else dependencies,
        "publish": None,
    }


@given(
    "cargo metadata describes a workspace with internal dependency requirements",
)
def given_cargo_metadata_with_internal_dependencies(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata for a workspace where beta depends on alpha across sections."""
    install_cargo_stub(cmd_mox, monkeypatch)
    alpha_manifest = _create_test_crate(workspace_directory, "alpha", "0.1.0")
    beta_dependencies = """
        [dependencies]
        alpha = "^0.1.0"

        [dev-dependencies]
        alpha = { version = "~0.1.0", path = "../alpha" }

        [build-dependencies.alpha]
        version = "0.1.0"
        path = "../alpha"
    """
    beta_manifest = _create_test_crate(
        workspace_directory, "beta", "0.1.0", dependencies_toml=beta_dependencies
    )

    workspace_manifest = workspace_directory / "Cargo.toml"
    workspace_manifest.write_text(
        textwrap.dedent(
            """
            [workspace]
            members = ["crates/alpha", "crates/beta"]

            [workspace.package]
            version = "0.1.0"
            """
        ).lstrip(),
        encoding="utf-8",
    )

    beta_dependency_entries = [
        {"name": "alpha", "package": "alpha-id"},
        {"name": "alpha", "package": "alpha-id", "kind": "dev"},
        {"name": "alpha", "package": "alpha-id", "kind": "build"},
    ]
    payload = {
        "workspace_root": str(workspace_directory),
        "packages": [
            _build_package_metadata("alpha", "0.1.0", alpha_manifest),
            _build_package_metadata(
                "beta", "0.1.0", beta_manifest, dependencies=beta_dependency_entries
            ),
        ],
        "workspace_members": ["alpha-id", "beta-id"],
    }
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )


@given(parsers.parse('bump.exclude contains "{crate_name}"'))
def given_bump_exclude_contains(
    workspace_directory: Path,
    crate_name: str,
) -> None:
    """Ensure ``crate_name`` appears in the ``bump.exclude`` configuration."""
    config_path = workspace_directory / config_module.CONFIG_FILENAME
    document = parse_toml(config_path.read_text(encoding="utf-8"))
    bump_table = document.get("bump")
    if bump_table is None:
        bump_table = table()
        document["bump"] = bump_table
    exclude = bump_table.get("exclude")
    if exclude is None:
        exclude = array()
        bump_table["exclude"] = exclude
    if crate_name not in exclude:
        exclude.append(crate_name)
    config_path.write_text(document.as_string(), encoding="utf-8")


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
        *command_args,
    ]
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


@then(parsers.parse("the CLI exits with code {expected:d}"))
def then_cli_exit_code(cli_run: dict[str, typ.Any], expected: int) -> None:
    """Assert that the CLI terminated with ``expected`` exit code."""
    assert cli_run["returncode"] == expected


@then(parsers.parse('the stderr contains "{expected}"'))
def then_stderr_contains(cli_run: dict[str, typ.Any], expected: str) -> None:
    """Assert that ``expected`` appears in the captured stderr output."""
    assert expected in cli_run["stderr"]


@then(parsers.parse('the workspace manifest version is "{version}"'))
def then_workspace_manifest_version(
    cli_run: dict[str, typ.Any],
    version: str,
) -> None:
    """Validate the workspace manifest was updated to ``version``."""
    manifest_path = cli_run["workspace"] / "Cargo.toml"
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
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
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
    assert document["package"]["version"] == version


def _extract_dependency_requirement(entry: object) -> str:
    """Return the version requirement string recorded in a dependency entry."""
    if isinstance(entry, Item):
        value = entry.value
        if isinstance(value, str):
            return value
    if isinstance(entry, str):
        return entry
    if isinstance(entry, InlineTable | Table):
        version_value = entry.get("version")
        return _extract_dependency_requirement(version_value)
    message = f"Dependency version entry is not a string: {entry!r}"
    raise AssertionError(message)


@dc.dataclass(frozen=True, slots=True)
class DependencyCheck:
    """Specification for checking a dependency requirement."""

    crate_name: str
    dependency_name: str
    section: str
    expected_requirement: str


def then_dependency_requirement(
    cli_run: dict[str, typ.Any],
    check: DependencyCheck,
) -> None:
    """Assert that an internal dependency requirement reflects the new version."""
    crate_name = check.crate_name
    dependency_name = check.dependency_name
    section = check.section
    expected = check.expected_requirement
    manifest_path = cli_run["workspace"] / "crates" / crate_name / "Cargo.toml"
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
    try:
        dependency_table = document[section]
    except KeyError as exc:  # pragma: no cover - defensive guard
        message = f"Section {section!r} missing from manifest {manifest_path}"
        raise AssertionError(message) from exc
    entry = dependency_table.get(dependency_name)
    if entry is None:
        message = (
            "Dependency "
            f"{dependency_name!r} missing from section {section!r} in {manifest_path}"
        )
        raise AssertionError(message)
    requirement = _extract_dependency_requirement(entry)
    assert requirement == expected


@then(
    parsers.parse(
        'the dependency "{dependency_spec}" has requirement "{expected}"'
    )
)
def _then_dependency_requirement_step(
    cli_run: dict[str, typ.Any],
    dependency_spec: str,
    expected: str,
) -> None:
    """Assert that an internal dependency requirement reflects the new version.

    The dependency_spec should be in the format: "crate_name:dependency_name@section"
    Example: "beta:alpha@dependencies"
    """
    parts = dependency_spec.split(":", maxsplit=1)
    if len(parts) != 2:
        message = (
            "Dependency specification must contain exactly one ':' separator: "
            f"{dependency_spec!r}"
        )
        raise AssertionError(message)
    crate_name, dep_segment = parts
    dep_and_section = dep_segment.split("@", maxsplit=1)
    if len(dep_and_section) != 2:
        message = (
            "Dependency specification must contain exactly one '@' separator: "
            f"{dependency_spec!r}"
        )
        raise AssertionError(message)
    dependency_name, section = dep_and_section
    then_dependency_requirement(
        cli_run,
        DependencyCheck(
            crate_name=crate_name,
            dependency_name=dependency_name,
            section=section,
            expected_requirement=expected,
        ),
    )


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
