"""Unit tests covering publish plan derivation."""

from __future__ import annotations

import typing as typ

import pytest

from lading.commands import publish
from tests.unit.conftest import PlanningFixtures, _CrateSpec

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading import config as config_module
    from lading.workspace import WorkspaceCrate, WorkspaceDependency, WorkspaceGraph


def _plan_with_crates(
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
    crates: tuple[WorkspaceCrate, ...],
    **config_overrides: object,
) -> publish.PublishPlan:
    """Plan publication for ``crates`` using ``tmp_path`` as the workspace root."""
    root = tmp_path.resolve()
    workspace = make_workspace(root, *crates)
    configuration = make_config(**config_overrides)
    return publish.plan_publication(workspace, configuration)


def _make_dependency_chain(
    root: Path,
    *,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> tuple[WorkspaceCrate, WorkspaceCrate, WorkspaceCrate]:
    """Return crates that form a simple alpha→beta→gamma dependency chain."""
    alpha = make_crate(root, "alpha")
    beta = make_crate(
        root,
        "beta",
        _CrateSpec(dependencies=(make_dependency("alpha"),)),
    )
    gamma = make_crate(
        root,
        "gamma",
        _CrateSpec(dependencies=(make_dependency("beta"),)),
    )
    return alpha, beta, gamma


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
    planning_fixtures: PlanningFixtures,
    crate_specs: list[tuple[str, bool]],
    exclude: list[str],
    expected: dict[str, tuple[str, ...]],
) -> None:
    """Planner splits crates into publishable and skipped groups."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    crates = [
        fx.make_crate(root, name, _CrateSpec(publish=publish_flag))
        for name, publish_flag in crate_specs
    ]
    workspace = fx.make_workspace(root, *crates)
    configuration = fx.make_config(exclude=tuple(exclude))

    plan = publish.plan_publication(workspace, configuration)

    actual_publishable_names = tuple(crate.name for crate in plan.publishable)
    actual_manifest_names = tuple(crate.name for crate in plan.skipped_manifest)
    actual_configuration_names = tuple(
        crate.name for crate in plan.skipped_configuration
    )

    assert actual_publishable_names == expected["publishable"]
    assert actual_manifest_names == expected["manifest"]
    assert actual_configuration_names == expected["configuration"]


def test_plan_publication_empty_workspace(
    tmp_path: Path,
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Planner returns empty results when the workspace has no crates."""
    from lading.workspace import WorkspaceGraph

    root = tmp_path.resolve()
    workspace = WorkspaceGraph(workspace_root=root, crates=())
    configuration = make_config()

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == ()
    assert plan.skipped_manifest == ()
    assert plan.skipped_configuration == ()


def test_plan_publication_empty_exclude_list(
    planning_fixtures: PlanningFixtures,
) -> None:
    """Configuration exclusions default to publishing all eligible crates."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    publishable = fx.make_crate(root, "alpha")
    manifest_skipped = fx.make_crate(root, "beta", _CrateSpec(publish=False))
    workspace = fx.make_workspace(root, publishable, manifest_skipped)
    configuration = fx.make_config(exclude=())

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (publishable,)
    assert plan.skipped_manifest == (manifest_skipped,)
    assert plan.skipped_configuration == ()


def test_plan_publication_records_missing_exclusions(
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Unknown entries in publish.exclude are reported in the plan."""
    root = tmp_path.resolve()
    workspace = make_workspace(root)
    configuration = make_config(exclude=("missing",))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.missing_configuration_exclusions == ("missing",)


def test_plan_publication_records_multiple_missing_exclusions(
    tmp_path: Path,
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Multiple unmatched exclusions are surfaced in configuration order."""
    root = tmp_path.resolve()
    workspace = make_workspace(root)
    configuration = make_config(exclude=("missing1", "missing2", "missing3"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.missing_configuration_exclusions == (
        "missing1",
        "missing2",
        "missing3",
    )


def test_plan_publication_sorts_crates_by_name(
    planning_fixtures: PlanningFixtures,
) -> None:
    """Publishable and skipped crates appear in deterministic alphabetical order."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    publishable_second = fx.make_crate(root, "beta")
    publishable_first = fx.make_crate(root, "alpha")
    manifest_skipped_late = fx.make_crate(root, "epsilon", _CrateSpec(publish=False))
    manifest_skipped_early = fx.make_crate(root, "delta", _CrateSpec(publish=False))
    config_skipped_late = fx.make_crate(root, "theta")
    config_skipped_early = fx.make_crate(root, "gamma")
    workspace = fx.make_workspace(
        root,
        publishable_second,
        publishable_first,
        manifest_skipped_late,
        manifest_skipped_early,
        config_skipped_late,
        config_skipped_early,
    )
    configuration = fx.make_config(exclude=("gamma", "theta"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (publishable_first, publishable_second)
    assert plan.skipped_manifest == (manifest_skipped_early, manifest_skipped_late)
    assert plan.skipped_configuration == (config_skipped_early, config_skipped_late)


def test_plan_publication_multiple_configuration_skips(
    planning_fixtures: PlanningFixtures,
) -> None:
    """All configuration exclusions appear in the skipped configuration list."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    gamma = fx.make_crate(root, "gamma")
    delta = fx.make_crate(root, "delta")
    workspace = fx.make_workspace(root, gamma, delta)
    configuration = fx.make_config(exclude=("delta", "gamma"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == ()
    assert plan.skipped_configuration == (delta, gamma)


def test_plan_publication_topologically_orders_dependencies(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Crates are sorted so that dependencies publish before their dependents."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    alpha, beta, gamma = _make_dependency_chain(
        root, make_crate=fx.make_crate, make_dependency=make_dependency
    )

    plan = _plan_with_crates(
        fx.tmp_path,
        fx.make_workspace,
        fx.make_config,
        (gamma, beta, alpha),
    )

    assert plan.publishable == (alpha, beta, gamma)


def test_plan_publication_ignores_dev_dependency_cycles(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Dev-only dependency edges do not create publish-order cycles."""
    from lading.workspace import WorkspaceDependency

    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    alpha = fx.make_crate(
        root,
        "alpha",
        _CrateSpec(
            dependencies=(
                WorkspaceDependency(
                    package_id="beta-id",
                    name="beta",
                    manifest_name="beta",
                    kind="dev",
                ),
            )
        ),
    )
    beta = fx.make_crate(
        root,
        "beta",
        _CrateSpec(dependencies=(make_dependency("alpha"),)),
    )
    workspace = fx.make_workspace(root, alpha, beta)
    configuration = fx.make_config()

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (alpha, beta)


def test_plan_publication_detects_dependency_cycles(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """A dependency cycle raises an explicit planning error."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    alpha = fx.make_crate(
        root, "alpha", _CrateSpec(dependencies=(make_dependency("beta"),))
    )
    beta = fx.make_crate(
        root, "beta", _CrateSpec(dependencies=(make_dependency("alpha"),))
    )
    workspace = fx.make_workspace(root, alpha, beta)
    configuration = fx.make_config()

    with pytest.raises(publish.PublishPlanError) as excinfo:
        publish.plan_publication(workspace, configuration)

    assert "dependency cycle" in str(excinfo.value)


def test_plan_publication_ignores_cycles_in_non_publishable_crates(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Cycles among skipped crates do not block eligible publishable crates."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    alpha = fx.make_crate(root, "alpha")
    cycle_a = fx.make_crate(
        root,
        "cycle-a",
        _CrateSpec(publish=False, dependencies=(make_dependency("cycle-b"),)),
    )
    cycle_b = fx.make_crate(
        root,
        "cycle-b",
        _CrateSpec(publish=False, dependencies=(make_dependency("cycle-a"),)),
    )

    plan = _plan_with_crates(
        fx.tmp_path,
        fx.make_workspace,
        fx.make_config,
        (alpha, cycle_a, cycle_b),
    )

    assert plan.publishable == (alpha,)


def test_plan_publication_configuration_skips_ignore_cycles(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Configuration exclusions bypass cycles outside publishable crates."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    alpha = fx.make_crate(root, "alpha")
    cycle_a = fx.make_crate(
        root,
        "cycle-a",
        _CrateSpec(dependencies=(make_dependency("cycle-b"),)),
    )
    cycle_b = fx.make_crate(
        root,
        "cycle-b",
        _CrateSpec(dependencies=(make_dependency("cycle-a"),)),
    )

    plan = _plan_with_crates(
        fx.tmp_path,
        fx.make_workspace,
        fx.make_config,
        (alpha, cycle_a, cycle_b),
        exclude=("cycle-a", "cycle-b"),
    )

    assert plan.publishable == (alpha,)


def test_plan_publication_honours_configured_order(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Explicit publish.order values override the automatic dependency sort."""
    fx = planning_fixtures
    alpha, beta, gamma = _make_dependency_chain(
        fx.tmp_path.resolve(),
        make_crate=fx.make_crate,
        make_dependency=make_dependency,
    )

    plan = _plan_with_crates(
        fx.tmp_path,
        fx.make_workspace,
        fx.make_config,
        (alpha, beta, gamma),
        order=("gamma", "beta", "alpha"),
    )

    assert plan.publishable == (gamma, beta, alpha)


def test_plan_publication_rejects_incomplete_configured_order(
    planning_fixtures: PlanningFixtures,
) -> None:
    """Missing crates in publish.order surface a descriptive validation error."""
    fx = planning_fixtures
    root = fx.tmp_path.resolve()
    alpha = fx.make_crate(root, "alpha")
    beta = fx.make_crate(root, "beta")
    workspace = fx.make_workspace(root, alpha, beta)
    configuration = fx.make_config(order=("alpha",))

    with pytest.raises(publish.PublishPlanError) as excinfo:
        publish.plan_publication(workspace, configuration)

    message = str(excinfo.value)
    assert "publish.order omits" in message
    assert "beta" in message


def test_plan_publication_rejects_duplicate_configured_crates(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Repeated publish.order entries raise a duplicate configuration error."""
    fx = planning_fixtures
    alpha, _, _ = _make_dependency_chain(
        fx.tmp_path.resolve(),
        make_crate=fx.make_crate,
        make_dependency=make_dependency,
    )

    with pytest.raises(publish.PublishPlanError) as excinfo:
        _plan_with_crates(
            fx.tmp_path,
            fx.make_workspace,
            fx.make_config,
            (alpha,),
            order=("alpha", "alpha"),
        )

    assert "Duplicate publish.order entries: alpha" in str(excinfo.value)


def test_plan_publication_rejects_unknown_configured_crates(
    planning_fixtures: PlanningFixtures,
    make_dependency: typ.Callable[[str], WorkspaceDependency],
) -> None:
    """Names outside the publishable set trigger an informative error."""
    fx = planning_fixtures
    alpha, _, _ = _make_dependency_chain(
        fx.tmp_path.resolve(),
        make_crate=fx.make_crate,
        make_dependency=make_dependency,
    )

    with pytest.raises(publish.PublishPlanError) as excinfo:
        _plan_with_crates(
            fx.tmp_path,
            fx.make_workspace,
            fx.make_config,
            (alpha,),
            order=("alpha", "omega"),
        )

    assert "publish.order references crates outside the publishable set" in str(
        excinfo.value
    )
