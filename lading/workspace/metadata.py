"""Interfaces for invoking ``cargo metadata``."""

from __future__ import annotations

import json
import typing as typ

from plumbum import local
from plumbum.commands.processes import CommandNotFound

from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path

    from plumbum.commands.base import BoundCommand


class CargoMetadataError(RuntimeError):
    """Raised when ``cargo metadata`` cannot be executed successfully."""


class CargoExecutableNotFoundError(CargoMetadataError):
    """Raised when the ``cargo`` executable is missing from ``PATH``."""

    def __init__(self) -> None:
        """Initialise the error with a descriptive message."""
        super().__init__("The 'cargo' executable could not be located.")


class CargoMetadataInvocationError(CargoMetadataError):
    """Raised when ``cargo metadata`` exits with a failure code."""

    def __init__(self, exit_code: int, stdout: str, stderr: str) -> None:
        """Summarise the failing invocation for the caller."""
        message = (
            stderr.strip()
            or stdout.strip()
            or f"cargo metadata exited with status {exit_code}"
        )
        super().__init__(message)


class CargoMetadataParseError(CargoMetadataError):
    """Raised when the command output cannot be parsed."""

    def __init__(self, detail: str) -> None:
        """Store the underlying parse failure description."""
        super().__init__(detail)

    @classmethod
    def invalid_json(cls) -> CargoMetadataParseError:
        """Return an error indicating malformed JSON output."""
        return cls("cargo metadata produced invalid JSON output")

    @classmethod
    def non_object_payload(cls) -> CargoMetadataParseError:
        """Return an error indicating the payload was not a JSON object."""
        return cls("cargo metadata returned a non-object JSON payload")


def _ensure_command() -> BoundCommand:
    """Return the ``cargo metadata`` command object."""
    try:
        cargo = local["cargo"]
    except CommandNotFound as exc:  # pragma: no cover - defensive guard
        raise CargoExecutableNotFoundError from exc
    return cargo["metadata", "--format-version", "1"]


def _coerce_text(value: str | bytes) -> str:
    """Normalise process output to text."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def load_cargo_metadata(
    workspace_root: Path | str | None = None,
) -> typ.Mapping[str, typ.Any]:
    """Execute ``cargo metadata`` and parse the resulting JSON payload."""
    command = _ensure_command()
    root_path = normalise_workspace_root(workspace_root)
    exit_code, stdout, stderr = command.run(retcode=None, cwd=str(root_path))
    stdout_text = _coerce_text(stdout)
    stderr_text = _coerce_text(stderr)
    if exit_code != 0:
        raise CargoMetadataInvocationError(exit_code, stdout_text, stderr_text)
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise CargoMetadataParseError.invalid_json() from exc
    if not isinstance(payload, dict):
        raise CargoMetadataParseError.non_object_payload()
    return payload
