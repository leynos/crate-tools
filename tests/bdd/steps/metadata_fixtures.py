"""Cargo metadata fixtures used by behavioural CLI tests."""

from __future__ import annotations

import json
import textwrap
import typing as typ

from pytest_bdd import given

from tests.bdd.steps.test_data_helpers import (
    _build_package_metadata,
    _create_test_crate,
)
from tests.helpers.workspace_helpers import install_cargo_stub

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from cmd_mox import CmdMox


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


@given("cargo metadata describes a workspace with internal dependency requirements")
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
