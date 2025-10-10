"""Shared test helpers for workspace metadata tests."""

from __future__ import annotations

import os
import typing as typ

from cmd_mox.ipc import Invocation

if typ.TYPE_CHECKING:
    import pytest
    from cmd_mox import CmdMox


def install_cargo_stub(cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch) -> None:
    """Activate cmd-mox shims for both in-process and subprocess tests."""
    from lading.workspace import metadata as metadata_module

    class _StubCommand:
        """Use cmd-mox expectations without invoking an external process."""

        def run(
            self,
            *,
            retcode: int | tuple[int, ...] | None = None,
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
    monkeypatch.setenv(metadata_module.CMD_MOX_STUB_ENV_VAR, "1")
