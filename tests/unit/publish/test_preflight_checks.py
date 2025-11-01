"""Unit tests targeting publish pre-flight helper utilities."""

from __future__ import annotations

import typing as typ

import pytest

from lading.commands import publish
from lading.workspace import metadata as metadata_module

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_split_command_rejects_empty_sequence() -> None:
    """Splitting an empty command raises a descriptive error."""
    with pytest.raises(publish.PublishPreflightError) as excinfo:
        publish._split_command(())

    assert "Command sequence must contain" in str(excinfo.value)


@pytest.mark.parametrize(
    "command",
    [
        ("cargo", "check"),
        ("cargo", "test", "--workspace"),
        ("git", "status", "--porcelain"),
    ],
)
def test_normalise_cmd_mox_command_forwards_non_cargo_commands(
    command: tuple[str, ...],
) -> None:
    """cmd-mox normalisation preserves non-cargo commands and arguments."""
    program, args = command[0], tuple(command[1:])

    rewritten_program, rewritten_args = publish._normalise_cmd_mox_command(
        program, args
    )

    if program == "cargo" and args:
        expected_program = f"cargo::{args[0]}"
        expected_args = list(args[1:])
    else:
        expected_program = program
        expected_args = list(args)

    assert rewritten_program == expected_program
    assert rewritten_args == expected_args


def test_metadata_coerce_text_decodes_bytes() -> None:
    """Binary output is decoded using UTF-8 with replacement semantics."""
    alpha = "\N{GREEK SMALL LETTER ALPHA}"
    encoded = alpha.encode()
    assert metadata_module._coerce_text(encoded) == alpha

    binary = b"foo\xff"
    assert metadata_module._coerce_text(binary) == "foo\ufffd"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on"])
def test_should_use_cmd_mox_stub_honours_truthy_values(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment values recognised as truthy enable cmd-mox stubbing."""
    monkeypatch.setenv(publish.metadata_module.CMD_MOX_STUB_ENV_VAR, value)

    assert publish._should_use_cmd_mox_stub() is True


def test_should_use_cmd_mox_stub_returns_false_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing environment values disable cmd-mox stubbing."""
    monkeypatch.delenv(publish.metadata_module.CMD_MOX_STUB_ENV_VAR, raising=False)

    assert publish._should_use_cmd_mox_stub() is False


def test_run_cargo_preflight_raises_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-zero command results are converted into preflight errors."""

    def failing_runner(
        command: tuple[str, ...], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        assert cwd == tmp_path
        assert command[0] == "cargo"
        return 1, "", "boom"

    with pytest.raises(publish.PublishPreflightError) as excinfo:
        publish._run_cargo_preflight(tmp_path, "check", runner=failing_runner)

    message = str(excinfo.value)
    assert "cargo check" in message
    assert "boom" in message


def test_verify_clean_working_tree_detects_dirty_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Dirty workspaces cause preflight to abort unless allow-dirty is set."""
    root = tmp_path.resolve()

    def dirty_runner(
        command: tuple[str, ...], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        assert cwd == root
        return 0, " M file\n", ""

    with pytest.raises(publish.PublishPreflightError) as excinfo:
        publish._verify_clean_working_tree(root, allow_dirty=False, runner=dirty_runner)

    assert "uncommitted changes" in str(excinfo.value)

    # Allow dirty should bypass the runner entirely.
    publish._verify_clean_working_tree(root, allow_dirty=True, runner=dirty_runner)


def test_verify_clean_working_tree_reports_missing_repo(
    tmp_path: Path,
) -> None:
    """A missing git repository surfaces a descriptive error."""

    def missing_runner(
        command: tuple[str, ...], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        assert command == ("git", "status", "--porcelain")
        assert cwd == tmp_path
        return 128, "", "fatal: Not a git repository"

    with pytest.raises(publish.PublishPreflightError) as excinfo:
        publish._verify_clean_working_tree(
            tmp_path, allow_dirty=False, runner=missing_runner
        )

    message = str(excinfo.value)
    assert "git repository" in message
    assert "fatal" in message
