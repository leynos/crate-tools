"""BDD steps for the cargo metadata wrapper."""

from __future__ import annotations

import json
import typing as typ

from pytest_bdd import given, scenarios, then, when

from lading.workspace import load_cargo_metadata
from tests.helpers.workspace_helpers import install_cargo_stub

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from cmd_mox import CmdMox

scenarios("../features/workspace_metadata.feature")


@given("a workspace directory", target_fixture="workspace_directory")
def given_workspace_directory(tmp_path: Path) -> Path:
    """Provide a workspace root for discovery exercises."""
    return tmp_path


@given("cargo metadata returns workspace information")
def given_cargo_metadata_response(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    workspace_directory: Path,
) -> None:
    """Stub the ``cargo metadata`` command for discovery tests."""
    install_cargo_stub(cmd_mox, monkeypatch)
    payload = {"workspace_root": str(workspace_directory), "packages": []}
    cmd_mox.mock("cargo").with_args("metadata", "--format-version", "1").returns(
        exit_code=0,
        stdout=json.dumps(payload),
    )


@when("I inspect the workspace metadata", target_fixture="metadata_payload")
def when_inspect_metadata(workspace_directory: Path) -> typ.Mapping[str, typ.Any]:
    """Execute the discovery helper against the stubbed command."""
    return load_cargo_metadata(workspace_directory)


@then("the metadata payload contains the workspace root")
def then_metadata_contains_workspace(
    metadata_payload: typ.Mapping[str, typ.Any], workspace_directory: Path
) -> None:
    """Assert that the workspace root was parsed from the JSON payload."""
    assert metadata_payload["workspace_root"] == str(workspace_directory)
