"""Tests for the ``cargo metadata`` wrapper."""

from __future__ import annotations

import json
import os
import typing as typ

import pytest
from cmd_mox.ipc import Invocation

from lading.workspace import CargoMetadataError, load_cargo_metadata
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


def test_load_cargo_metadata_raises_on_failure(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-zero exit codes should raise :class:`CargoMetadataError`."""
    _install_cargo_stub(cmd_mox, monkeypatch)
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=101,
        stderr="could not read manifest",
    )

    with pytest.raises(CargoMetadataError) as excinfo:
        load_cargo_metadata(tmp_path)

    assert "could not read manifest" in str(excinfo.value)


def test_load_cargo_metadata_validates_json(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Invalid JSON payloads should raise :class:`CargoMetadataError`."""
    _install_cargo_stub(cmd_mox, monkeypatch)
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout="[]",
    )

    with pytest.raises(CargoMetadataError) as excinfo:
        load_cargo_metadata(tmp_path)

    assert "non-object" in str(excinfo.value)
