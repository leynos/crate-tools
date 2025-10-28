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
    readme_flag: bool = False,
) -> WorkspaceCrate:
    """Construct a :class:`WorkspaceCrate` rooted under ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    crate_root = root / name
    crate_root.mkdir(parents=True, exist_ok=True)
    manifest = crate_root / "Cargo.toml"
    header_lines = [
        "[package]",
        f'name = "{name}"',
        'version = "0.1.0"',
    ]
    if readme_flag:
        header_lines.append("readme.workspace = true")
    manifest.write_text("\n".join(header_lines) + "\n", encoding="utf-8")
    return WorkspaceCrate(
        id=f"{name}-id",
        name=name,
        version="0.1.0",
        manifest_path=manifest,
        root_path=crate_root,
        publish=publish_flag,
        readme_is_workspace=readme_flag,
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


def _make_dependency_chain(
    root: Path,
) -> tuple[WorkspaceCrate, WorkspaceCrate, WorkspaceCrate]:
    """Return crates that form a simple alpha→beta→gamma dependency chain.

    ``alpha`` has no dependencies, ``beta`` depends on ``alpha``, and
    ``gamma`` depends on ``beta``. Tests reuse this helper to ensure they all
    operate on the same structure without duplicating setup code.
    """
    alpha = _make_crate(root, "alpha")
    beta = _make_crate(root, "beta", dependencies=(_make_dependency("alpha"),))
    gamma = _make_crate(root, "gamma", dependencies=(_make_dependency("beta"),))
    return alpha, beta, gamma


def _plan_with_crates(
    tmp_path: Path,
    crates: tuple[WorkspaceCrate, ...],
    **config_overrides: object,
) -> publish.PublishPlan:
    """Plan publication for ``crates`` using ``tmp_path`` as the workspace root.

    Parameters
    ----------
    tmp_path:
        Pytest-provided temporary directory that defines the workspace root.
    crates:
        The workspace crates to include when constructing the plan.
    **config_overrides:
        Keyword arguments forwarded to :func:`_make_config` to customise the
        planner configuration.

    Returns
    -------
    publish.PublishPlan
        The resulting plan from :func:`publish.plan_publication`.

    """
    root = tmp_path.resolve()
    workspace = _make_workspace(root, *crates)
    configuration = _make_config(**config_overrides)
    return publish.plan_publication(workspace, configuration)


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
    alpha, beta, gamma = _make_dependency_chain(tmp_path.resolve())

    plan = _plan_with_crates(tmp_path, (gamma, beta, alpha))

    assert plan.publishable == (alpha, beta, gamma)


def test_plan_publication_ignores_dev_dependency_cycles(tmp_path: Path) -> None:
    """Dev-only dependency edges do not create publish-order cycles."""
    root = tmp_path.resolve()
    alpha = _make_crate(
        root,
        "alpha",
        dependencies=(
            WorkspaceDependency(
                package_id="beta-id",
                name="beta",
                manifest_name="beta",
                kind="dev",
            ),
        ),
    )
    beta = _make_crate(
        root,
        "beta",
        dependencies=(_make_dependency("alpha"),),
    )
    workspace = _make_workspace(root, alpha, beta)
    configuration = _make_config()

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (alpha, beta)


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


def test_plan_publication_ignores_cycles_in_non_publishable_crates(
    tmp_path: Path,
) -> None:
    """Cycles among skipped crates do not block eligible publishable crates."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    cycle_a = _make_crate(
        root,
        "cycle-a",
        publish_flag=False,
        dependencies=(_make_dependency("cycle-b"),),
    )
    cycle_b = _make_crate(
        root,
        "cycle-b",
        publish_flag=False,
        dependencies=(_make_dependency("cycle-a"),),
    )

    plan = _plan_with_crates(tmp_path, (alpha, cycle_a, cycle_b))

    assert plan.publishable == (alpha,)


def test_plan_publication_configuration_skips_ignore_cycles(tmp_path: Path) -> None:
    """Configuration exclusions bypass cycles outside publishable crates."""
    root = tmp_path.resolve()
    alpha = _make_crate(root, "alpha")
    cycle_a = _make_crate(
        root,
        "cycle-a",
        dependencies=(_make_dependency("cycle-b"),),
    )
    cycle_b = _make_crate(
        root,
        "cycle-b",
        dependencies=(_make_dependency("cycle-a"),),
    )

    plan = _plan_with_crates(
        tmp_path,
        (alpha, cycle_a, cycle_b),
        exclude=("cycle-a", "cycle-b"),
    )

    assert plan.publishable == (alpha,)


def test_plan_publication_honours_configured_order(tmp_path: Path) -> None:
    """Explicit publish.order values override the automatic dependency sort."""
    alpha, beta, gamma = _make_dependency_chain(tmp_path.resolve())

    plan = _plan_with_crates(
        tmp_path,
        (alpha, beta, gamma),
        order=("gamma", "beta", "alpha"),
    )

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
    alpha, _, _ = _make_dependency_chain(tmp_path.resolve())

    with pytest.raises(publish.PublishPlanError) as excinfo:
        _plan_with_crates(tmp_path, (alpha,), order=("alpha", "alpha"))

    assert "Duplicate publish.order entries: alpha" in str(excinfo.value)


def test_plan_publication_rejects_unknown_configured_crates(tmp_path: Path) -> None:
    """Names outside the publishable set trigger an informative error."""
    alpha, _, _ = _make_dependency_chain(tmp_path.resolve())

    with pytest.raises(publish.PublishPlanError) as excinfo:
        _plan_with_crates(tmp_path, (alpha,), order=("alpha", "omega"))

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
    output = publish.run(
        workspace,
        configuration,
        options=publish.PublishOptions(build_directory=tmp_path / "staging"),
    )

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

    staging_root = tmp_path.parent / f"{tmp_path.name}-staging"
    output = publish.run(
        tmp_path, options=publish.PublishOptions(build_directory=staging_root)
    )

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

    staging_root = tmp_path.parent / f"{tmp_path.name}-staging"
    output = publish.run(
        root, options=publish.PublishOptions(build_directory=staging_root)
    )

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

    staging_root = tmp_path.parent / f"{tmp_path.name}-staging"
    message = publish.run(
        root,
        configuration,
        workspace,
        options=publish.PublishOptions(build_directory=staging_root),
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

    staging_root = tmp_path.parent / f"{tmp_path.name}-staging"
    message = publish.run(
        root,
        configuration,
        workspace,
        options=publish.PublishOptions(build_directory=staging_root),
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


def test_append_section_appends_formatted_items() -> None:
    """Generic section helper applies the provided formatter."""

    class Dummy:
        def __init__(self, value: str) -> None:
            self.value = value

    lines = []
    items = (Dummy("alpha"), Dummy("beta"))

    publish._append_section(
        lines,
        items,
        header="Header:",
        formatter=lambda item: item.value.upper(),
    )

    assert lines == ["Header:", "- ALPHA", "- BETA"]


def test_append_section_defaults_to_string_conversion() -> None:
    """Default formatter handles simple string values without boilerplate."""
    lines: list[str] = []

    publish._append_section(lines, ("alpha", "beta"), header="Header:")

    assert lines == ["Header:", "- alpha", "- beta"]


def test_append_section_omits_header_for_empty_sequences() -> None:
    """Helper leaves ``lines`` unchanged when there is nothing to report."""
    lines = ["prefix"]

    publish._append_section(lines, (), header="Header:")

    assert lines == ["prefix"]


def test_format_plan_formats_skipped_sections(tmp_path: Path) -> None:
    """``_format_plan`` renders skipped crates using their names only."""
    root = tmp_path.resolve()
    manifest_skipped = _make_crate(root, "beta", publish_flag=False)
    config_skipped = _make_crate(root, "gamma")
    plan = publish.PublishPlan(
        workspace_root=root,
        publishable=(),
        skipped_manifest=(manifest_skipped,),
        skipped_configuration=(config_skipped,),
        missing_configuration_exclusions=("missing",),
    )

    message = publish._format_plan(plan, strip_patches="all")

    lines = message.splitlines()
    manifest_index = lines.index("Skipped (publish = false):")
    configuration_index = lines.index("Skipped via publish.exclude:")
    missing_index = lines.index("Configured exclusions not found in workspace:")

    assert lines[manifest_index + 1] == "- beta"
    assert lines[configuration_index + 1] == "- gamma"
    assert lines[missing_index + 1] == "- missing"


def test_normalise_build_directory_defaults_to_tempdir(tmp_path: Path) -> None:
    """Normalisation creates a temporary directory when none is provided."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    build_directory = publish._normalise_build_directory(workspace_root, None)

    assert build_directory.exists()
    assert build_directory.is_absolute()
    assert not build_directory.is_relative_to(workspace_root)


def test_normalise_build_directory_resolves_relative_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Relative build directories are resolved against the current directory."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.chdir(tmp_path)

    build_directory = publish._normalise_build_directory(
        workspace_root, Path("staging")
    )

    expected = (tmp_path / "staging").resolve()
    assert build_directory == expected
    assert build_directory.exists()


def test_normalise_build_directory_rejects_workspace_descendants(
    tmp_path: Path,
) -> None:
    """Normalisation rejects build directories nested under the workspace."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    build_directory = workspace_root / "target"

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._normalise_build_directory(workspace_root, build_directory)

    assert "cannot reside within the workspace root" in str(excinfo.value)


def test_copy_workspace_tree_mirrors_workspace_contents(tmp_path: Path) -> None:
    """Workspace files are cloned into the staging directory."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    manifest = workspace_root / "Cargo.toml"
    manifest.write_text("[workspace]\n", encoding="utf-8")
    nested_dir = workspace_root / "crates" / "alpha"
    nested_dir.mkdir(parents=True)
    nested_file = nested_dir / "README.md"
    nested_file.write_text("# README\n", encoding="utf-8")

    build_directory = tmp_path / "staging"
    build_directory.mkdir()

    staging_root = publish._copy_workspace_tree(workspace_root, build_directory)

    assert staging_root == build_directory / workspace_root.name
    assert (staging_root / "Cargo.toml").read_text(encoding="utf-8") == "[workspace]\n"
    assert (staging_root / "crates" / "alpha" / "README.md").read_text(
        encoding="utf-8"
    ) == "# README\n"


def test_copy_workspace_tree_replaces_existing_clone(tmp_path: Path) -> None:
    """Existing staging directories are replaced with a fresh copy."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "marker.txt").write_text("fresh", encoding="utf-8")

    build_directory = tmp_path / "staging"
    existing_clone = build_directory / workspace_root.name
    existing_clone.mkdir(parents=True)
    stale_file = existing_clone / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    staging_root = publish._copy_workspace_tree(workspace_root, build_directory)

    assert staging_root == existing_clone
    assert not stale_file.exists()
    assert (staging_root / "marker.txt").read_text(encoding="utf-8") == "fresh"


def test_copy_workspace_tree_rejects_nested_clone(tmp_path: Path) -> None:
    """Copying into a directory under the workspace is prohibited."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._copy_workspace_tree(workspace_root, workspace_root)

    assert "cannot be nested inside the workspace root" in str(excinfo.value)


def test_stage_workspace_readmes_returns_empty_list_when_unused(
    tmp_path: Path,
) -> None:
    """No work is performed when no crates opt into the workspace README."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    copied = publish._stage_workspace_readmes(
        crates=(), workspace_root=workspace_root, staging_root=staging_root
    )

    assert copied == []


def test_stage_workspace_readmes_copies_and_sorts_targets(tmp_path: Path) -> None:
    """Workspace README is copied into each opted-in crate in sorted order."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    readme = workspace_root / "README.md"
    readme.write_text("workspace", encoding="utf-8")
    crate_alpha = _make_crate(workspace_root, "alpha", readme_flag=True)
    crate_beta = _make_crate(workspace_root, "beta", readme_flag=True)
    staging_root = tmp_path / "staging" / "workspace"
    staging_root.mkdir(parents=True)

    copied = publish._stage_workspace_readmes(
        crates=(crate_beta, crate_alpha),
        workspace_root=workspace_root,
        staging_root=staging_root,
    )

    relative = [path.relative_to(staging_root).as_posix() for path in copied]
    assert relative == ["alpha/README.md", "beta/README.md"]
    for path in copied:
        assert path.read_text(encoding="utf-8") == "workspace"


def test_stage_workspace_readmes_requires_workspace_readme(tmp_path: Path) -> None:
    """Crates requesting the workspace README require the source file."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    crate = _make_crate(workspace_root, "alpha", readme_flag=True)
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._stage_workspace_readmes(
            crates=(crate,), workspace_root=workspace_root, staging_root=staging_root
        )

    assert "Workspace README.md is required" in str(excinfo.value)


def test_stage_workspace_readmes_rejects_external_crates(tmp_path: Path) -> None:
    """Crates outside the workspace cannot receive the workspace README."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    readme = workspace_root / "README.md"
    readme.write_text("workspace", encoding="utf-8")

    external_root = tmp_path / "external"
    crate = _make_crate(external_root, "alpha", readme_flag=True)
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._stage_workspace_readmes(
            crates=(crate,), workspace_root=workspace_root, staging_root=staging_root
        )

    assert "outside the workspace root" in str(excinfo.value)


def test_format_preparation_summary_lists_copied_readmes(tmp_path: Path) -> None:
    """Summary includes relative README paths when copies exist."""
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    readme_alpha = staging_root / "crates" / "alpha" / "README.md"
    readme_beta = staging_root / "crates" / "beta" / "README.md"
    for path in (readme_alpha, readme_beta):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("workspace", encoding="utf-8")
    preparation = publish.PublishPreparation(
        staging_root=staging_root, copied_readmes=(readme_alpha, readme_beta)
    )

    lines = publish._format_preparation_summary(preparation)

    assert lines[0] == f"Staged workspace at: {staging_root}"
    assert "Copied workspace README to:" in lines[1]
    assert "- crates/alpha/README.md" in lines
    assert "- crates/beta/README.md" in lines


def test_format_preparation_summary_handles_external_paths(tmp_path: Path) -> None:
    """Summary falls back to absolute paths when not under the staging root."""
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    external_readme = tmp_path.parent / "external-readme.md"
    external_readme.write_text("workspace", encoding="utf-8")
    preparation = publish.PublishPreparation(
        staging_root=staging_root, copied_readmes=(external_readme,)
    )

    lines = publish._format_preparation_summary(preparation)

    assert lines[0] == f"Staged workspace at: {staging_root}"
    assert lines[1] == "Copied workspace README to:"
    assert f"- {external_readme}" in lines


def test_format_preparation_summary_reports_absence(tmp_path: Path) -> None:
    """Summary highlights when no README copies were required."""
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    preparation = publish.PublishPreparation(
        staging_root=staging_root, copied_readmes=()
    )

    lines = publish._format_preparation_summary(preparation)

    assert lines == (
        f"Staged workspace at: {staging_root}",
        "Copied workspace README to: none required",
    )


def test_prepare_workspace_copies_workspace_readme(tmp_path: Path) -> None:
    """Staging copies the workspace README into crates that opt in."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    readme = workspace_root / "README.md"
    readme.write_text("Workspace README", encoding="utf-8")
    crate = _make_crate(workspace_root, "alpha", readme_flag=True)
    workspace = _make_workspace(workspace_root, crate)
    configuration = _make_config()
    plan = publish.plan_publication(workspace, configuration)
    options = publish.PublishOptions(build_directory=tmp_path / "staging")

    preparation = publish.prepare_workspace(plan, workspace, options=options)

    staging_root = preparation.staging_root
    assert staging_root.exists()
    staged_readme = (
        staging_root / crate.root_path.relative_to(workspace_root) / "README.md"
    )
    assert staged_readme.exists()
    assert staged_readme.read_text(encoding="utf-8") == readme.read_text(
        encoding="utf-8"
    )
    assert staged_readme in preparation.copied_readmes


def test_prepare_workspace_requires_workspace_readme(tmp_path: Path) -> None:
    """Staging fails fast when crates expect the workspace README."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    crate = _make_crate(workspace_root, "alpha", readme_flag=True)
    workspace = _make_workspace(workspace_root, crate)
    configuration = _make_config()
    plan = publish.plan_publication(workspace, configuration)

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish.prepare_workspace(
            plan,
            workspace,
            options=publish.PublishOptions(build_directory=tmp_path / "staging"),
        )

    assert "README.md" in str(excinfo.value)
