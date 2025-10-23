"""Behavioural fixtures for CLI scenarios."""

from __future__ import annotations

import json
import textwrap
import typing as typ

from pytest_bdd import given, parsers
from tomlkit import array, table
from tomlkit import parse as parse_toml

from lading import config as config_module
from tests.helpers.workspace_helpers import install_cargo_stub

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from cmd_mox import CmdMox


@given("a workspace directory with configuration", target_fixture="workspace_directory")
def given_workspace_directory(tmp_path: Path) -> Path:
    """Provide a temporary workspace root for CLI exercises."""
    config_path = tmp_path / config_module.CONFIG_FILENAME
    config_path.write_text(
        '[bump]\n\n[publish]\nstrip_patches = "all"\n', encoding="utf-8"
    )
    return tmp_path


@given(parsers.parse('bump.documentation.globs contains "{pattern}"'))
def given_documentation_glob(workspace_directory: Path, pattern: str) -> None:
    """Append ``pattern`` to the documentation glob list in ``lading.toml``."""
    config_path = workspace_directory / config_module.CONFIG_FILENAME
    document = parse_toml(config_path.read_text(encoding="utf-8"))
    bump_table = document.get("bump")
    if bump_table is None:
        bump_table = table()
        document["bump"] = bump_table
    documentation_table = bump_table.get("documentation")
    if documentation_table is None:
        documentation_table = table()
        bump_table["documentation"] = documentation_table
    globs_value = documentation_table.get("globs")
    if globs_value is None:
        globs_array = array()
        documentation_table["globs"] = globs_array
    elif hasattr(globs_value, "append"):
        globs_array = globs_value
    else:  # pragma: no cover - defensive guard for unexpected config edits
        message = "bump.documentation.globs must be an array"
        raise AssertionError(message)
    globs_array.append(pattern)
    config_path.write_text(document.as_string(), encoding="utf-8")


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
    manifest_path: Path,
    version: str = "0.1.0",
    dependencies: list[dict[str, str]] | None = None,
    *,
    publish: bool | tuple[str, ...] | None = None,
) -> dict[str, typ.Any]:
    """Construct the minimal package metadata payload for ``cargo metadata``."""
    return {
        "name": name,
        "version": version,
        "id": f"{name}-id",
        "manifest_path": str(manifest_path),
        "dependencies": [] if dependencies is None else dependencies,
        "publish": publish,
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
            _build_package_metadata("alpha", alpha_manifest),
            _build_package_metadata(
                "beta", beta_manifest, dependencies=beta_dependency_entries
            ),
        ],
        "workspace_members": ["alpha-id", "beta-id"],
    }
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )


@given("cargo metadata describes a workspace with publish filtering cases")
def given_cargo_metadata_with_publish_filters(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata illustrating publishable, skipped, and missing crates."""
    install_cargo_stub(cmd_mox, monkeypatch)
    crate_specs: tuple[tuple[str, bool], ...] = (
        ("alpha", True),
        ("beta", False),
        ("gamma", True),
    )
    packages: list[dict[str, typ.Any]] = []
    member_entries: list[str] = []
    for name, publishable in crate_specs:
        crate_dir = workspace_directory / "crates" / name
        crate_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = crate_dir / "Cargo.toml"
        package_lines = [
            "[package]",
            f'name = "{name}"',
            'version = "0.1.0"',
        ]
        if not publishable:
            package_lines.append("publish = false")
        manifest_path.write_text("\n".join(package_lines) + "\n", encoding="utf-8")
        packages.append(
            _build_package_metadata(
                name,
                manifest_path,
                publish=False if not publishable else None,
            )
        )
        member_entries.append(f'"crates/{name}"')
    workspace_manifest = workspace_directory / "Cargo.toml"
    members_literal = ", ".join(member_entries)
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
        "packages": packages,
        "workspace_members": [f"{name}-id" for name, _ in crate_specs],
    }
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )


def _add_exclude_to_config(
    workspace_directory: Path,
    table_name: str,
    crate_name: str,
) -> None:
    """Ensure ``crate_name`` appears in the ``{table_name}.exclude`` configuration."""
    config_path = workspace_directory / config_module.CONFIG_FILENAME
    document = parse_toml(config_path.read_text(encoding="utf-8"))
    table_section = document.get(table_name)
    if table_section is None:
        table_section = table()
        document[table_name] = table_section
    exclude = table_section.get("exclude")
    if exclude is None:
        exclude = array()
        table_section["exclude"] = exclude
    if crate_name not in exclude:
        exclude.append(crate_name)
    config_path.write_text(document.as_string(), encoding="utf-8")


@given(parsers.parse('bump.exclude contains "{crate_name}"'))
def given_bump_exclude_contains(
    workspace_directory: Path,
    crate_name: str,
) -> None:
    """Ensure ``crate_name`` appears in the ``bump.exclude`` configuration."""
    _add_exclude_to_config(workspace_directory, "bump", crate_name)


@given(parsers.parse('publish.exclude contains "{crate_name}"'))
def given_publish_exclude_contains(
    workspace_directory: Path,
    crate_name: str,
) -> None:
    """Ensure ``crate_name`` appears in the ``publish.exclude`` configuration."""
    _add_exclude_to_config(workspace_directory, "publish", crate_name)
