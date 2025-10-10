"""Tests for the ``cargo metadata`` wrapper."""

from __future__ import annotations

import dataclasses as dc
import json
import textwrap
import typing as typ

import pytest

from lading.workspace import (
    CargoExecutableNotFoundError,
    CargoMetadataError,
    WorkspaceDependency,
    WorkspaceGraph,
    WorkspaceModelError,
    build_workspace_graph,
    load_cargo_metadata,
    load_workspace,
)
from lading.workspace import metadata as metadata_module
from tests.helpers.workspace_helpers import install_cargo_stub

_METADATA_PAYLOAD: typ.Final[dict[str, typ.Any]] = {
    "workspace_root": "./",
    "packages": [],
}

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


@pytest.mark.parametrize(
    ("stdout_data", "stderr_data"),
    [
        pytest.param(
            json.dumps(_METADATA_PAYLOAD),
            "",
            id="text",
        ),
        pytest.param(
            json.dumps(_METADATA_PAYLOAD).encode("utf-8"),
            b"",
            id="bytes",
        ),
    ],
)
def test_load_cargo_metadata_handles_stdout_variants(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stdout_data: str | bytes,
    stderr_data: str | bytes,
) -> None:
    """Successful invocations should return parsed JSON for text and byte streams."""
    install_cargo_stub(cmd_mox, monkeypatch)
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=stdout_data,
        stderr=stderr_data,
    )

    result = load_cargo_metadata(tmp_path)

    assert result == _METADATA_PAYLOAD


def test_load_cargo_metadata_missing_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Absent ``cargo`` binaries should raise ``CargoExecutableNotFoundError``."""

    def _raise() -> None:
        raise CargoExecutableNotFoundError

    monkeypatch.setattr(metadata_module, "_ensure_command", _raise)

    with pytest.raises(CargoExecutableNotFoundError):
        load_cargo_metadata(tmp_path)


def test_load_cargo_metadata_error_decodes_byte_streams(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failure messages should be decoded when provided as bytes."""
    install_cargo_stub(cmd_mox, monkeypatch)
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=101,
        stdout=b"",
        stderr=b"manifest missing",
    )

    with pytest.raises(CargoMetadataError) as excinfo:
        load_cargo_metadata(tmp_path)

    assert "manifest missing" in str(excinfo.value)


@dc.dataclass(frozen=True, slots=True)
class ErrorScenario:
    """Test scenario for cargo metadata error cases."""

    exit_code: int
    stdout: str
    stderr: str
    expected_message: str


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            ErrorScenario(
                exit_code=101,
                stdout="",
                stderr="could not read manifest",
                expected_message="could not read manifest",
            ),
            id="non_zero_exit_with_stderr",
        ),
        pytest.param(
            ErrorScenario(
                exit_code=101,
                stdout="",
                stderr="",
                expected_message="cargo metadata exited with status 101",
            ),
            id="non_zero_exit_empty_output",
        ),
        pytest.param(
            ErrorScenario(
                exit_code=0,
                stdout="[]",
                stderr="",
                expected_message="non-object",
            ),
            id="non_object_json",
        ),
        pytest.param(
            ErrorScenario(
                exit_code=0,
                stdout="{]",
                stderr="",
                expected_message="invalid JSON",
            ),
            id="malformed_json",
        ),
    ],
)
def test_load_cargo_metadata_error_scenarios(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: ErrorScenario,
) -> None:
    """Error cases should raise :class:`CargoMetadataError` with detail."""
    install_cargo_stub(cmd_mox, monkeypatch)
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=scenario.exit_code,
        stdout=scenario.stdout,
        stderr=scenario.stderr,
    )

    with pytest.raises(CargoMetadataError) as excinfo:
        load_cargo_metadata(tmp_path)

    assert scenario.expected_message in str(excinfo.value)


def test_ensure_command_raises_on_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify ``CommandNotFound`` is surfaced as ``CargoExecutableNotFoundError``."""

    class _RaisingLocal:
        def __getitem__(self, name: str) -> typ.NoReturn:
            raise metadata_module.CommandNotFound(name, ["/usr/bin"])

    monkeypatch.setattr(metadata_module, "local", _RaisingLocal())

    with pytest.raises(CargoExecutableNotFoundError):
        metadata_module._ensure_command()


def test_build_workspace_graph_constructs_models(tmp_path: Path) -> None:
    """Convert metadata payloads into strongly typed workspace models."""
    workspace_root = tmp_path
    crate_manifest = workspace_root / "crate" / "Cargo.toml"
    crate_manifest.parent.mkdir(parents=True)
    crate_manifest.write_text(
        textwrap.dedent(
            """
            [package]
            name = "crate"
            version = "0.1.0"
            readme.workspace = true

            [dependencies]
            helper = { path = "../helper", version = "0.1.0" }
            """
        ).strip()
    )
    helper_manifest = workspace_root / "helper" / "Cargo.toml"
    helper_manifest.parent.mkdir(parents=True)
    helper_manifest.write_text(
        textwrap.dedent(
            """
            [package]
            name = "helper"
            version = "0.1.0"
            readme = "README.md"
            """
        ).strip()
    )
    metadata = {
        "workspace_root": str(workspace_root),
        "packages": [
            {
                "name": "crate",
                "version": "0.1.0",
                "id": "crate-id",
                "manifest_path": str(crate_manifest),
                "dependencies": [
                    {"name": "helper", "package": "helper-id", "kind": "dev"},
                    {"name": "external", "package": "external-id"},
                ],
                "publish": [],
            },
            {
                "name": "helper",
                "version": "0.1.0",
                "id": "helper-id",
                "manifest_path": str(helper_manifest),
                "dependencies": [],
                "publish": None,
            },
        ],
        "workspace_members": ["crate-id", "helper-id"],
    }

    graph = build_workspace_graph(metadata)

    assert isinstance(graph, WorkspaceGraph)
    assert graph.workspace_root == workspace_root.resolve()
    names = [crate.name for crate in graph.crates]
    assert names == ["crate", "helper"]
    crate = graph.crates[0]
    assert crate.publish is False
    assert crate.readme_is_workspace is True
    assert crate.dependencies == (
        WorkspaceDependency(package_id="helper-id", name="helper", kind="dev"),
    )
    helper = graph.crates[1]
    assert helper.publish is True
    assert helper.readme_is_workspace is False


def test_build_workspace_graph_rejects_missing_members(tmp_path: Path) -> None:
    """Missing package entries should surface as ``WorkspaceModelError``."""
    metadata = {
        "workspace_root": str(tmp_path),
        "packages": [],
        "workspace_members": ["crate-id"],
    }

    with pytest.raises(WorkspaceModelError):
        build_workspace_graph(metadata)


def test_load_workspace_invokes_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure ``load_workspace`` converts metadata into a graph."""
    crate_manifest = tmp_path / "crate" / "Cargo.toml"
    crate_manifest.parent.mkdir(parents=True)
    crate_manifest.write_text(
        """
        [package]
        name = "crate"
        version = "0.1.0"
        readme.workspace = true
        """
    )
    metadata = {
        "workspace_root": str(tmp_path),
        "packages": [
            {
                "name": "crate",
                "version": "0.1.0",
                "id": "crate-id",
                "manifest_path": str(crate_manifest),
                "dependencies": [],
                "publish": None,
            }
        ],
        "workspace_members": ["crate-id"],
    }

    monkeypatch.setattr(metadata_module, "load_cargo_metadata", lambda *_: metadata)

    graph = load_workspace(tmp_path)

    assert isinstance(graph, WorkspaceGraph)
    assert graph.crates[0].name == "crate"
