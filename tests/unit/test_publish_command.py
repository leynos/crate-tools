"""Unit tests for the publish planning helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lading import config as config_module
from lading.commands import publish
from lading.workspace import (
    WorkspaceCrate,
    WorkspaceDependency,
    WorkspaceGraph,
    WorkspaceModelError,
)


def _make_config(**overrides: object) -> config_module.LadingConfig:
    """Return a configuration tailored for publish command tests."""
    publish_table = config_module.PublishConfig(strip_patches="all", **overrides)
    return config_module.LadingConfig(publish=publish_table)


def _make_crate(
    root: Path,
    name: str,
    *,
    publish_flag: bool = True,
    dependencies: tuple[WorkspaceDependency, ...] | None = None,
) -> WorkspaceCrate:
    """Construct a :class:`WorkspaceCrate` rooted under ``root``."""
    crate_root = root / name
    manifest = crate_root / "Cargo.toml"
    return WorkspaceCrate(
        id=f"{name}-id",
        name=name,
        version="0.1.0",
        manifest_path=manifest,
        root_path=crate_root,
        publish=publish_flag,
        readme_is_workspace=False,
        dependencies=() if dependencies is None else dependencies,
    )


def _make_workspace(root: Path, *crates: WorkspaceCrate) -> WorkspaceGraph:
    """Construct a :class:`WorkspaceGraph` for ``crates`` rooted at ``root``."""
    if not crates:
        crates = (_make_crate(root, "alpha"),)
    return WorkspaceGraph(workspace_root=root, crates=tuple(crates))


def _make_dependency(name: str) -> WorkspaceDependency:
    """Return a workspace dependency pointing at the crate named ``name``."""
    return WorkspaceDependency(
        package_id=f"{name}-id",
        name=name,
        manifest_name=name,
        kind=None,
    )


@pytest.mark.parametrize(
    (
        "crate_specs",
        "exclude",
        "expected",
    ),
    [
        pytest.param(
            [("alpha", True), ("beta", False), ("gamma", True)],
            ["gamma"],
            {
                "publishable": ("alpha",),
                "manifest": ("beta",),
                "configuration": ("gamma",),
            },
            id="filters_manifest_and_configuration",
        ),
        pytest.param(
            [("alpha", False), ("beta", False)],
            [],
            {
                "publishable": (),
                "manifest": ("alpha", "beta"),
                "configuration": (),
            },
            id="handles_no_publishable_crates",
        ),
    ],
)
def test_plan_publication_filtering(
    tmp_path: Path,
    crate_specs: list[tuple[str, bool]],
    exclude: list[str],
    expected: dict[str, tuple[str, ...]],
) -> None:
    """Planner splits crates into publishable and skipped groups."""
    root = tmp_path.resolve()
    crates = [
        _make_crate(root, name, publish_flag=publish_flag)
        for name, publish_flag in crate_specs
    ]
    workspace = _make_workspace(root, *crates)
    configuration = _make_config(exclude=tuple(exclude))

    plan = publish.plan_publication(workspace, configuration)

    actual_publishable_names = tuple(crate.name for crate in plan.publishable)
    actual_manifest_names = tuple(crate.name for crate in plan.skipped_manifest)
    actual_configuration_names = tuple(
        crate.name for crate in plan.skipped_configuration
    )

    assert actual_publishable_names == expected["publishable"]
    assert actual_manifest_names == expected["manifest"]
    assert actual_configuration_names == expected["configuration"]


def test_plan_publication_empty_workspace(tmp_path: Path) -> None:
    """Planner returns empty results when the workspace has no crates."""
    root = tmp_path.resolve()
    workspace = WorkspaceGraph(workspace_root=root, crates=())
    configuration = _make_config()

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == ()
    assert plan.skipped_manifest == ()
    assert plan.skipped_configuration == ()


def test_plan_publication_empty_exclude_list(tmp_path: Path) -> None:
    """Configuration exclusions default to publishing all eligible crates."""
    root = tmp_path.resolve()
    publishable = _make_crate(root, "alpha")
    manifest_skipped = _make_crate(root, "beta", publish_flag=False)
    workspace = _make_workspace(root, publishable, manifest_skipped)
    configuration = _make_config(exclude=())

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (publishable,)
    assert plan.skipped_manifest == (manifest_skipped,)
    assert plan.skipped_configuration == ()


def test_plan_publication_records_missing_exclusions(tmp_path: Path) -> None:
    """Unknown entries in publish.exclude are reported in the plan."""
    root = tmp_path.resolve()
    workspace = _make_workspace(root)
    configuration = _make_config(exclude=("missing",))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.missing_configuration_exclusions == ("missing",)


def test_plan_publication_records_multiple_missing_exclusions(
    tmp_path: Path,
) -> None:
    """Multiple unmatched exclusions are surfaced in configuration order."""
    root = tmp_path.resolve()
    workspace = _make_workspace(root)
    configuration = _make_config(exclude=("missing1", "missing2", "missing3"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.missing_configuration_exclusions == (
        "missing1",
        "missing2",
        "missing3",
    )


def test_plan_publication_sorts_crates_by_name(tmp_path: Path) -> None:
    """Publishable and skipped crates appear in deterministic alphabetical order."""
    root = tmp_path.resolve()
    publishable_second = _make_crate(root, "beta")
    publishable_first = _make_crate(root, "alpha")
    manifest_skipped_late = _make_crate(root, "epsilon", publish_flag=False)
    manifest_skipped_early = _make_crate(root, "delta", publish_flag=False)
    config_skipped_late = _make_crate(root, "theta")
    config_skipped_early = _make_crate(root, "gamma")
    workspace = _make_workspace(
        root,
        publishable_second,
        publishable_first,
        manifest_skipped_late,
        manifest_skipped_early,
        config_skipped_late,
        config_skipped_early,
    )
    configuration = _make_config(exclude=("gamma", "theta"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (publishable_first, publishable_second)
    assert plan.skipped_manifest == (manifest_skipped_early, manifest_skipped_late)
    assert plan.skipped_configuration == (config_skipped_early, config_skipped_late)


def test_plan_publication_multiple_configuration_skips(tmp_path: Path) -> None:
    """All configuration exclusions appear in the skipped configuration list."""
    root = tmp_path.resolve()
    gamma = _make_crate(root, "gamma")
    delta = _make_crate(root, "delta")
    workspace = _make_workspace(root, gamma, delta)
    configuration = _make_config(exclude=("delta", "gamma"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == ()
    assert plan.skipped_configuration == (delta, gamma)


def test_plan_publication_topologically_orders_dependencies(tmp_path: Path) -> None:
    """Crates are sorted so that dependencies publish before their dependents."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    beta = _make_crate(root, "beta", dependencies=(_make_dependency("alpha"),))
    gamma = _make_crate(root, "gamma", dependencies=(_make_dependency("beta"),))
    workspace = _make_workspace(root, gamma, beta, alpha)
    configuration = _make_config()

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (alpha, beta, gamma)


def test_plan_publication_detects_dependency_cycles(tmp_path: Path) -> None:
    """A dependency cycle raises an explicit planning error."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha", dependencies=(_make_dependency("beta"),))
    beta = _make_crate(root, "beta", dependencies=(_make_dependency("alpha"),))
    workspace = _make_workspace(root, alpha, beta)
    configuration = _make_config()

    with pytest.raises(publish.PublishPlanError) as excinfo:
        publish.plan_publication(workspace, configuration)

    assert "dependency cycle" in str(excinfo.value)


def test_plan_publication_honours_configured_order(tmp_path: Path) -> None:
    """Explicit publish.order values override the automatic dependency sort."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    beta = _make_crate(root, "beta", dependencies=(_make_dependency("alpha"),))
    gamma = _make_crate(root, "gamma", dependencies=(_make_dependency("beta"),))
    workspace = _make_workspace(root, alpha, beta, gamma)
    configuration = _make_config(order=("gamma", "beta", "alpha"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (gamma, beta, alpha)


def test_plan_publication_rejects_incomplete_configured_order(tmp_path: Path) -> None:
    """Missing crates in publish.order surface a descriptive validation error."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    beta = _make_crate(root, "beta")
    workspace = _make_workspace(root, alpha, beta)
    configuration = _make_config(order=("alpha",))

    with pytest.raises(publish.PublishPlanError) as excinfo:
        publish.plan_publication(workspace, configuration)

    message = str(excinfo.value)
    assert "publish.order omits" in message
    assert "beta" in message


def test_plan_publication_rejects_duplicate_configured_crates(tmp_path: Path) -> None:
    """Repeated publish.order entries raise a duplicate configuration error."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    workspace = _make_workspace(root, alpha)
    configuration = _make_config(order=("alpha", "alpha"))

    with pytest.raises(publish.PublishPlanError) as excinfo:
        publish.plan_publication(workspace, configuration)

    assert "Duplicate publish.order entries: alpha" in str(excinfo.value)


def test_plan_publication_rejects_unknown_configured_crates(tmp_path: Path) -> None:
    """Names outside the publishable set trigger an informative error."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    workspace = _make_workspace(root, alpha)
    configuration = _make_config(order=("alpha", "omega"))

    with pytest.raises(publish.PublishPlanError) as excinfo:
        publish.plan_publication(workspace, configuration)

    assert "publish.order references crates outside the publishable set" in str(
        excinfo.value
    )


def test_run_normalises_workspace_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The run helper resolves the workspace root before planning."""
    workspace = Path("workspace")
    monkeypatch.chdir(tmp_path)
    resolved = tmp_path / "workspace"
    plan_workspace = _make_workspace(resolved)
    configuration = _make_config()

    def fake_load(root: Path) -> WorkspaceGraph:
        assert root == resolved
        return plan_workspace

    monkeypatch.setattr("lading.workspace.load_workspace", fake_load)
    output = publish.run(workspace, configuration)

    assert output.splitlines()[0] == f"Publish plan for {resolved}"


def test_run_uses_active_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run`` falls back to :func:`current_configuration` when needed."""
    configuration = _make_config(exclude=("skip-me",))
    monkeypatch.setattr(config_module, "current_configuration", lambda: configuration)
    root = tmp_path.resolve()
    workspace = _make_workspace(root, _make_crate(root, "alpha"))
    monkeypatch.setattr("lading.workspace.load_workspace", lambda _: workspace)

    output = publish.run(tmp_path)

    assert "skip-me" in output


def test_run_loads_configuration_when_inactive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run`` loads configuration from disk if no active configuration exists."""
    root = tmp_path.resolve()
    workspace = _make_workspace(root, _make_crate(root, "alpha"))
    monkeypatch.setattr("lading.workspace.load_workspace", lambda _: workspace)
    loaded_configuration = _make_config()
    load_calls: list[Path] = []

    def raise_not_loaded() -> config_module.LadingConfig:
        message = "Configuration unavailable"
        raise config_module.ConfigurationNotLoadedError(message)

    def capture_load(path: Path) -> config_module.LadingConfig:
        load_calls.append(path)
        return loaded_configuration

    monkeypatch.setattr(config_module, "current_configuration", raise_not_loaded)
    monkeypatch.setattr(config_module, "load_configuration", capture_load)

    output = publish.run(root)

    assert "Crates to publish" in output
    assert load_calls == [root]


def test_run_formats_plan_summary(tmp_path: Path) -> None:
    """``run`` returns a structured summary of the publish plan."""
    root = tmp_path.resolve()
    publishable = _make_crate(root, "alpha")
    manifest_skipped = _make_crate(root, "beta", publish_flag=False)
    config_skipped = _make_crate(root, "gamma")
    workspace = _make_workspace(root, publishable, manifest_skipped, config_skipped)
    configuration = _make_config(exclude=("gamma", "missing"))

    message = publish.run(root, configuration, workspace)

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


def test_run_reports_no_publishable_crates(tmp_path: Path) -> None:
    """``run`` highlights when no crates are eligible for publication."""
    root = tmp_path.resolve()
    manifest_skipped = _make_crate(root, "alpha", publish_flag=False)
    config_skipped_first = _make_crate(root, "beta")
    config_skipped_second = _make_crate(root, "gamma")
    workspace = _make_workspace(
        root, manifest_skipped, config_skipped_first, config_skipped_second
    )
    configuration = _make_config(exclude=("beta", "gamma"))

    message = publish.run(root, configuration, workspace)

    lines = message.splitlines()
    assert "Crates to publish: none" in lines
    assert "Skipped (publish = false):" in lines
    assert "- alpha" in lines
    assert "Skipped via publish.exclude:" in lines
    assert "- beta" in lines
    assert "- gamma" in lines


def test_run_surfaces_missing_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run`` converts missing workspace roots into workspace model errors."""
    configuration = _make_config()

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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
