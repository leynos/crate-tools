"""Unit tests for end-to-end publish command execution."""

from __future__ import annotations

import typing as typ

import pytest

from lading import config as config_module
from lading.commands import publish
from lading.workspace import WorkspaceCrate, WorkspaceGraph, WorkspaceModelError
from tests.unit.conftest import _CrateSpec, _ORIGINAL_PREFLIGHT

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_run_normalises_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
    publish_options: publish.PublishOptions,
) -> None:
    """The run helper resolves the workspace root before planning."""
    workspace = "workspace"
    monkeypatch.chdir(tmp_path)
    resolved = tmp_path / "workspace"
    plan_workspace = make_workspace(resolved)
    configuration = make_config()

    def fake_load(root: Path) -> WorkspaceGraph:
        assert root == resolved
        return plan_workspace

    monkeypatch.setattr("lading.workspace.load_workspace", fake_load)
    output = publish.run(workspace, configuration, options=publish_options)

    assert output.splitlines()[0] == f"Publish plan for {resolved}"


def test_run_uses_active_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
    publish_options: publish.PublishOptions,
) -> None:
    """``run`` falls back to :func:`current_configuration` when needed."""
    configuration = make_config(exclude=("skip-me",))
    monkeypatch.setattr(config_module, "current_configuration", lambda: configuration)
    root = tmp_path.resolve()
    workspace = make_workspace(root, make_crate(root, "alpha"))
    monkeypatch.setattr("lading.workspace.load_workspace", lambda _: workspace)

    output = publish.run(tmp_path, options=publish_options)

    assert "skip-me" in output


def test_run_loads_configuration_when_inactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
    publish_options: publish.PublishOptions,
) -> None:
    """``run`` loads configuration from disk if no active configuration exists."""
    root = tmp_path.resolve()
    workspace = make_workspace(root, make_crate(root, "alpha"))
    monkeypatch.setattr("lading.workspace.load_workspace", lambda _: workspace)
    loaded_configuration = make_config()
    load_calls: list[Path] = []

    def raise_not_loaded() -> config_module.LadingConfig:
        message = "Configuration unavailable"
        raise config_module.ConfigurationNotLoadedError(message)

    def capture_load(path: Path) -> config_module.LadingConfig:
        load_calls.append(path)
        return loaded_configuration

    monkeypatch.setattr(config_module, "current_configuration", raise_not_loaded)
    monkeypatch.setattr(config_module, "load_configuration", capture_load)

    output = publish.run(root, options=publish_options)

    assert "Crates to publish" in output
    assert load_calls == [root]


def test_run_formats_plan_summary(
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
    publish_options: publish.PublishOptions,
) -> None:
    """``run`` returns a structured summary of the publish plan."""
    root = tmp_path.resolve()
    publishable = make_crate(root, "alpha")
    manifest_skipped = make_crate(root, "beta", _CrateSpec(publish=False))
    config_skipped = make_crate(root, "gamma")
    workspace = make_workspace(root, publishable, manifest_skipped, config_skipped)
    configuration = make_config(exclude=("gamma", "missing"))

    message = publish.run(
        root,
        configuration,
        workspace,
        options=publish_options,
    )

    lines = message.splitlines()
    assert lines[0] == f"Publish plan for {root}"
    assert "Strip patch strategy: all" in lines[1]
    assert "- alpha @ 0.1.0" in lines
    assert "Skipped (publish = false):" in lines
    assert "- beta" in lines
    assert "Skipped via publish.exclude:" in lines
    assert "- gamma" in lines
    assert "Configured exclusions not found in workspace:" in lines
    assert "- missing" in lines
    assert any(line.startswith("Staged workspace at:") for line in lines)
    assert "Copied workspace README to: none required" in lines


def test_run_reports_no_publishable_crates(
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
    publish_options: publish.PublishOptions,
) -> None:
    """``run`` highlights when no crates are eligible for publication."""
    root = tmp_path.resolve()
    manifest_skipped = make_crate(root, "alpha", _CrateSpec(publish=False))
    config_skipped_first = make_crate(root, "beta")
    config_skipped_second = make_crate(root, "gamma")
    workspace = make_workspace(
        root, manifest_skipped, config_skipped_first, config_skipped_second
    )
    configuration = make_config(exclude=("beta", "gamma"))

    message = publish.run(
        root,
        configuration,
        workspace,
        options=publish_options,
    )

    lines = message.splitlines()
    assert "Crates to publish: none" in lines
    assert "Skipped (publish = false):" in lines
    assert "- alpha" in lines
    assert "Skipped via publish.exclude:" in lines
    assert "- beta" in lines
    assert "- gamma" in lines
    assert any(line.startswith("Staged workspace at:") for line in lines)
    assert "Copied workspace README to: none required" in lines


def test_run_surfaces_missing_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """``run`` converts missing workspace roots into workspace model errors."""
    configuration = make_config()

    def raise_missing(_: Path) -> WorkspaceGraph:
        message = "workspace missing"
        raise FileNotFoundError(message)

    monkeypatch.setattr("lading.workspace.load_workspace", raise_missing)

    with pytest.raises(WorkspaceModelError) as excinfo:
        publish.run(tmp_path, configuration)

    message = str(excinfo.value)
    assert "Workspace root not found" in message
    assert str(tmp_path.resolve()) in message


def test_run_surfaces_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """``run`` propagates configuration errors encountered while loading."""

    def raise_not_loaded() -> config_module.LadingConfig:
        message = "Configuration inactive"
        raise config_module.ConfigurationNotLoadedError(message)

    def raise_config_error(_: Path) -> config_module.LadingConfig:
        message = "invalid configuration"
        raise config_module.ConfigurationError(message)

    monkeypatch.setattr(config_module, "current_configuration", raise_not_loaded)
    monkeypatch.setattr(config_module, "load_configuration", raise_config_error)

    with pytest.raises(config_module.ConfigurationError) as excinfo:
        publish.run(tmp_path)

    assert str(excinfo.value) == "invalid configuration"


def test_run_executes_preflight_checks_in_clone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Pre-flight commands run inside an isolated workspace clone."""

    monkeypatch.setattr(publish, "_run_preflight_checks", _ORIGINAL_PREFLIGHT)
    root = tmp_path.resolve()
    workspace = make_workspace(root, make_crate(root, "alpha"))
    configuration = make_config()

    clone_paths: list[Path] = []

    def fake_clone(source: Path, destination: Path) -> None:
        assert source == root
        destination.mkdir()
        clone_paths.append(destination)

    monkeypatch.setattr(publish, "_clone_workspace_for_checks", fake_clone)

    calls: list[tuple[tuple[str, ...], Path | None]] = []

    def fake_invoke(
        command: typ.Sequence[str], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        calls.append((tuple(command), cwd))
        return 0, "", ""

    monkeypatch.setattr(publish, "_invoke", fake_invoke)

    message = publish.run(root, configuration, workspace)

    assert message.startswith(f"Publish plan for {root}")
    assert clone_paths, "clone helper should have been invoked"
    clone_root = clone_paths[0]
    assert ("git", "status", "--porcelain") in {
        command for command, _cwd in calls
    }
    assert (
        ("cargo", "check", "--workspace", "--all-targets"),
        clone_root,
    ) in calls
    assert (
        ("cargo", "test", "--workspace", "--all-targets"),
        clone_root,
    ) in calls


def test_run_raises_when_preflight_command_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Non-zero cargo check aborts the publish command."""

    monkeypatch.setattr(publish, "_run_preflight_checks", _ORIGINAL_PREFLIGHT)
    root = tmp_path.resolve()
    workspace = make_workspace(root, make_crate(root, "alpha"))
    configuration = make_config()

    monkeypatch.setattr(
        publish,
        "_clone_workspace_for_checks",
        lambda _source, destination: destination.mkdir(),
    )

    def failing_invoke(
        command: typ.Sequence[str], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        if command[0] == "git":
            return 0, "", ""
        if command[1] == "check":
            return 1, "", "check failed"
        return 0, "", ""

    monkeypatch.setattr(publish, "_invoke", failing_invoke)

    with pytest.raises(publish.PublishPreflightError) as excinfo:
        publish.run(root, configuration, workspace)

    message = str(excinfo.value)
    assert "cargo check" in message
    assert "exit code 1" in message


def test_allow_dirty_flag_skips_clean_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """``allow_dirty`` bypasses the git status cleanliness guard."""

    monkeypatch.setattr(publish, "_run_preflight_checks", _ORIGINAL_PREFLIGHT)
    root = tmp_path.resolve()
    workspace = make_workspace(root, make_crate(root, "alpha"))
    configuration = make_config()

    clone_destinations: list[Path] = []

    def fake_clone(source: Path, destination: Path) -> None:
        destination.mkdir()
        clone_destinations.append(destination)

    monkeypatch.setattr(publish, "_clone_workspace_for_checks", fake_clone)

    def dirty_invoke(
        command: typ.Sequence[str], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        if command[0] == "git":
            return 0, " M Cargo.toml\n", ""
        return 0, "", ""

    monkeypatch.setattr(publish, "_invoke", dirty_invoke)

    with pytest.raises(publish.PublishPreflightError):
        publish.run(root, configuration, workspace)

    calls: list[tuple[tuple[str, ...], Path | None]] = []

    def allow_dirty_invoke(
        command: typ.Sequence[str], *, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        if command[0] == "git":
            message = "git status should be skipped when allow-dirty is set"
            raise AssertionError(message)
        calls.append((tuple(command), cwd))
        return 0, "", ""

    monkeypatch.setattr(publish, "_invoke", allow_dirty_invoke)

    message = publish.run(
        root,
        configuration,
        workspace,
        options=publish.PublishOptions(allow_dirty=True),
    )

    assert message.startswith(f"Publish plan for {root}")
    assert clone_destinations, "clone helper should still run with allow-dirty"
    clone_root = clone_destinations[-1]
    assert (
        ("cargo", "check", "--workspace", "--all-targets"),
        clone_root,
    ) in calls
    assert (
        ("cargo", "test", "--workspace", "--all-targets"),
        clone_root,
    ) in calls
