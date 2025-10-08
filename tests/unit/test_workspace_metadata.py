"""Tests for the ``cargo metadata`` wrapper."""

from __future__ import annotations

import json
import os
import typing as typ

import pytest
from cmd_mox.ipc import Invocation

from lading.workspace import (
    CargoExecutableNotFoundError,
    CargoMetadataError,
    load_cargo_metadata,
)
from lading.workspace import metadata as metadata_module

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


def _install_cargo_stub(cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``_ensure_command`` with a shim using :mod:`cmd_mox`."""

    class _StubCommand:
        def run(
            self,
            *,
            retcode: int | None = None,
            cwd: str | os.PathLike[str] | None = None,
        ) -> tuple[int, str, str]:
            invocation = Invocation(
                command="cargo",
                args=["metadata", "--format-version", "1"],
                stdin="",
                env=dict(os.environ),
            )
            response = cmd_mox._handle_invocation(invocation)
            return response.exit_code, response.stdout, response.stderr

    monkeypatch.setattr(metadata_module, "_ensure_command", lambda: _StubCommand())


def test_load_cargo_metadata_parses_output(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Successful invocations should return parsed JSON payloads."""
    _install_cargo_stub(cmd_mox, monkeypatch)
    payload = {"workspace_root": "./", "packages": []}
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
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


@pytest.mark.parametrize(
    ("exit_code", "stdout", "stderr", "expected_message"),
    [
        pytest.param(
            101,
            "",
            "could not read manifest",
            "could not read manifest",
            id="non_zero_exit_with_stderr",
        ),
        pytest.param(
            101,
            "",
            "",
            "cargo metadata exited with status 101",
            id="non_zero_exit_empty_output",
        ),
        pytest.param(
            0,
            "[]",
            "",
            "non-object",
            id="non_object_json",
        ),
        pytest.param(
            0,
            "{]",
            "",
            "invalid JSON",
            id="malformed_json",
        ),
    ],
)
def test_load_cargo_metadata_error_scenarios(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    exit_code: int,
    stdout: str,
    stderr: str,
    expected_message: str,
) -> None:
    """Error cases should raise :class:`CargoMetadataError` with detail."""
    _install_cargo_stub(cmd_mox, monkeypatch)
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )

    with pytest.raises(CargoMetadataError) as excinfo:
        load_cargo_metadata(tmp_path)

    assert expected_message in str(excinfo.value)
