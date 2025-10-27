"""Behavioural fixtures for CLI scenarios."""

from __future__ import annotations

import json
import textwrap
import typing as typ

from pytest_bdd import given, parsers
from tomlkit import array, table
from tomlkit import document as make_document
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


def _update_manifest_version(
    manifest_path: Path,
    version: str,
    keys: tuple[str, ...],
) -> None:
    """Update version at nested ``keys`` path in the manifest at ``manifest_path``."""
    if not manifest_path.exists():
        message = f"Manifest not found: {manifest_path}"
        raise AssertionError(message)
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
    target = document
    for key in keys[:-1]:
        try:
            target = target[key]
        except KeyError as exc:  # pragma: no cover - defensive guard
            path = "/".join(keys)
            message = f"Key path {path!r} missing from manifest {manifest_path}"
            raise AssertionError(message) from exc
    target[keys[-1]] = version
    manifest_path.write_text(document.as_string(), encoding="utf-8")


def _update_crate_manifests(crates_root: Path, version: str) -> None:
    """Update version in all crate manifests under ``crates_root``."""
    if not crates_root.exists():
        message = f"Crates directory not found: {crates_root}"
        raise AssertionError(message)
    for child in crates_root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / "Cargo.toml"
        _update_manifest_version(
            manifest_path,
            version,
            ("package", "version"),
        )


@given(parsers.parse('the workspace manifests record version "{version}"'))
def given_workspace_versions_match(
    workspace_directory: Path,
    version: str,
) -> None:
    """Ensure the workspace and member manifests record ``version``."""
    workspace_manifest = workspace_directory / "Cargo.toml"
    _update_manifest_version(
        workspace_manifest,
        version,
        ("workspace", "package", "version"),
    )
    crates_root = workspace_directory / "crates"
    _update_crate_manifests(crates_root, version)


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
        stderr="",
    )


@given("cargo metadata describes a workspace with a dev dependency cycle")
def given_cargo_metadata_with_dev_dependency_cycle(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata where dev dependencies would falsely create a cycle."""
    install_cargo_stub(cmd_mox, monkeypatch)

    alpha_manifest = _create_test_crate(
        workspace_directory,
        "alpha",
        "0.1.0",
        dependencies_toml="""
            [dev-dependencies]
            beta = { version = "0.1.0", path = "../beta" }
        """,
    )
    beta_manifest = _create_test_crate(
        workspace_directory,
        "beta",
        "0.1.0",
        dependencies_toml="""
            [dependencies]
            alpha = { version = "0.1.0", path = "../alpha" }
        """,
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

    payload = {
        "workspace_root": str(workspace_directory),
        "packages": [
            _build_package_metadata(
                "alpha",
                alpha_manifest,
                dependencies=[
                    {
                        "name": "beta",
                        "package": "beta-id",
                        "kind": "dev",
                    }
                ],
            ),
            _build_package_metadata(
                "beta",
                beta_manifest,
                dependencies=[
                    {
                        "name": "alpha",
                        "package": "alpha-id",
                    }
                ],
            ),
        ],
        "workspace_members": ["alpha-id", "beta-id"],
    }

    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
        stderr="",
    )


@given("cargo metadata describes a workspace with a publish dependency cycle")
def given_cargo_metadata_with_dependency_cycle(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata for crates that form a dependency cycle."""
    install_cargo_stub(cmd_mox, monkeypatch)

    alpha_manifest = _create_test_crate(
        workspace_directory,
        "alpha",
        "0.1.0",
        dependencies_toml="""
            [dependencies]
            beta = { version = "0.1.0", path = "../beta" }
        """,
    )
    beta_manifest = _create_test_crate(
        workspace_directory,
        "beta",
        "0.1.0",
        dependencies_toml="""
            [dependencies]
            alpha = { version = "0.1.0", path = "../alpha" }
        """,
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

    payload = {
        "workspace_root": str(workspace_directory),
        "packages": [
            _build_package_metadata(
                "alpha",
                alpha_manifest,
                dependencies=[{"name": "beta", "package": "beta-id"}],
            ),
            _build_package_metadata(
                "beta",
                beta_manifest,
                dependencies=[{"name": "alpha", "package": "alpha-id"}],
            ),
        ],
        "workspace_members": ["alpha-id", "beta-id"],
    }

    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
        stderr="",
    )


@given(
    parsers.parse(
        'the workspace README contains a TOML dependency snippet for "{crate_name}"'
    )
)
def given_workspace_readme_snippet(workspace_directory: Path, crate_name: str) -> None:
    """Write a README with a TOML fence referencing ``crate_name``."""
    readme_path = workspace_directory / "README.md"
    content = textwrap.dedent(
        f"""
        # Usage

        ```toml
        [dependencies]
        {crate_name} = "0.1.0"
        ```
        """
    ).lstrip()
    readme_path.write_text(content, encoding="utf-8")


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
        stderr="",
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
    **metadata: typ.Any,  # noqa: ANN401 - fixtures accept arbitrary metadata fields
) -> dict[str, typ.Any]:
    """Construct the minimal package metadata payload for ``cargo metadata``."""
    dependencies = metadata.get("dependencies")
    publish = metadata.get("publish")
    return {
        "name": name,
        "version": version,
        "id": f"{name}-id",
        "manifest_path": str(manifest_path),
        "dependencies": [] if dependencies is None else dependencies,
        "publish": publish,
    }


def _install_publish_filter_metadata(
    workspace_directory: Path,
    crate_specs: typ.Sequence[tuple[str, bool]],
    *,
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stub ``cargo metadata`` responses for publish filtering exercises."""
    install_cargo_stub(cmd_mox, monkeypatch)
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
                publish=None if publishable else False,
            )
        )
        member_entries.append(f"crates/{name}")

    workspace_manifest = workspace_directory / "Cargo.toml"
    members_literal = ", ".join(f'"{member}"' for member in member_entries)
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
        stderr="",
    )


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
        stderr="",
    )


@given("cargo metadata describes a workspace with publish filtering cases")
def given_cargo_metadata_with_publish_filters(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata illustrating publishable, skipped, and missing crates."""
    _install_publish_filter_metadata(
        workspace_directory,
        (
            ("alpha", True),
            ("beta", False),
            ("gamma", True),
            ("delta", True),
        ),
        cmd_mox=cmd_mox,
        monkeypatch=monkeypatch,
    )


@given("cargo metadata describes a workspace with no publishable crates")
def given_cargo_metadata_without_publishable_crates(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata where manifest settings block every crate from publishing."""
    _install_publish_filter_metadata(
        workspace_directory,
        (
            ("alpha", False),
            ("beta", False),
        ),
        cmd_mox=cmd_mox,
        monkeypatch=monkeypatch,
    )


@given("cargo metadata describes a workspace with a publish dependency chain")
def given_cargo_metadata_with_dependency_chain(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub metadata for crates that depend on one another in sequence."""
    install_cargo_stub(cmd_mox, monkeypatch)

    alpha_manifest = _create_test_crate(workspace_directory, "alpha", "0.1.0")
    beta_manifest = _create_test_crate(
        workspace_directory,
        "beta",
        "0.1.0",
        dependencies_toml="""
            [dependencies]
            alpha = { version = "0.1.0", path = "../alpha" }
        """,
    )
    gamma_manifest = _create_test_crate(
        workspace_directory,
        "gamma",
        "0.1.0",
        dependencies_toml="""
            [dependencies]
            beta = { version = "0.1.0", path = "../beta" }
        """,
    )

    workspace_manifest = workspace_directory / "Cargo.toml"
    workspace_manifest.write_text(
        textwrap.dedent(
            """
            [workspace]
            members = ["crates/alpha", "crates/beta", "crates/gamma"]

            [workspace.package]
            version = "0.1.0"
            """
        ).lstrip(),
        encoding="utf-8",
    )

    payload = {
        "workspace_root": str(workspace_directory),
        "packages": [
            _build_package_metadata("alpha", alpha_manifest),
            _build_package_metadata(
                "beta",
                beta_manifest,
                dependencies=[{"name": "alpha", "package": "alpha-id"}],
            ),
            _build_package_metadata(
                "gamma",
                gamma_manifest,
                dependencies=[{"name": "beta", "package": "beta-id"}],
            ),
        ],
        "workspace_members": ["alpha-id", "beta-id", "gamma-id"],
    }

    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def _add_exclude_to_config(
    workspace_directory: Path,
    table_name: str,
    crate_name: str,
) -> None:
    """Ensure ``crate_name`` appears in the ``{table_name}.exclude`` configuration."""
    config_path = workspace_directory / config_module.CONFIG_FILENAME
    if config_path.exists():
        doc = parse_toml(config_path.read_text(encoding="utf-8"))
    else:
        doc = make_document()
    table_section = doc.get(table_name)
    if table_section is None:
        table_section = table()
        doc[table_name] = table_section
    exclude = table_section.get("exclude")
    if exclude is None:
        exclude = array()
        table_section["exclude"] = exclude
    if crate_name not in exclude:
        exclude.append(crate_name)
    config_path.write_text(doc.as_string(), encoding="utf-8")


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


@given(parsers.parse('publish.order is "{order}"'))
def given_publish_order_is(workspace_directory: Path, order: str) -> None:
    """Set the publish order configuration to ``order``."""
    names = [name.strip() for name in order.split(",") if name.strip()]
    config_path = workspace_directory / config_module.CONFIG_FILENAME
    if config_path.exists():
        doc = parse_toml(config_path.read_text(encoding="utf-8"))
    else:
        doc = make_document()
    publish_table = doc.get("publish")
    if publish_table is None:
        publish_table = table()
        doc["publish"] = publish_table
    order_array = array()
    for name in names:
        order_array.append(name)
    publish_table["order"] = order_array
    config_path.write_text(doc.as_string(), encoding="utf-8")
