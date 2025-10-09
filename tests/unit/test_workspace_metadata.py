"""Tests for the ``cargo metadata`` wrapper."""

from __future__ import annotations

import json
from dataclasses import dataclass
import typing as typ

import pytest

from lading.workspace import (
    CargoExecutableNotFoundError,
    CargoMetadataError,
    load_cargo_metadata,
)
from lading.workspace import metadata as metadata_module
from tests.helpers.workspace_helpers import install_cargo_stub

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


def test_load_cargo_metadata_parses_output(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Successful invocations should return parsed JSON payloads."""
    install_cargo_stub(cmd_mox, monkeypatch)
    payload = {"workspace_root": "./", "packages": []}
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )

    result = load_cargo_metadata(tmp_path)

    assert result == payload


def test_load_cargo_metadata_decodes_byte_output(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The wrapper should transparently decode byte streams."""
    install_cargo_stub(cmd_mox, monkeypatch)
    payload = {"workspace_root": "./", "packages": []}
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload).encode("utf-8"),
        stderr=b"",
    )

    result = load_cargo_metadata(tmp_path)

    assert result == payload


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


@dataclass(frozen=True)
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

    class _MissingCargo:
        def __getitem__(self, name: str) -> typ.NoReturn:
            raise metadata_module.CommandNotFound(name, ["/usr/bin"])

    monkeypatch.setattr(metadata_module, "local", _MissingCargo())

    with pytest.raises(CargoExecutableNotFoundError):
        metadata_module._ensure_command()
