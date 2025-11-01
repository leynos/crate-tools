"""Publish plan filtering behaviour tests."""

from __future__ import annotations

import typing as typ

import pytest

from lading.commands import publish
from lading.workspace import WorkspaceGraph

from .conftest import make_config, make_crate, make_workspace

if typ.TYPE_CHECKING:
    from pathlib import Path


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
        make_crate(root, name, publish_flag=publish_flag)
        for name, publish_flag in crate_specs
    ]
    workspace = make_workspace(root, *crates)
    configuration = make_config(exclude=tuple(exclude))

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
    configuration = make_config()

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == ()
    assert plan.skipped_manifest == ()
    assert plan.skipped_configuration == ()


def test_plan_publication_empty_exclude_list(tmp_path: Path) -> None:
    """Configuration exclusions default to publishing all eligible crates."""
    root = tmp_path.resolve()
    publishable = make_crate(root, "alpha")
    manifest_skipped = make_crate(root, "beta", publish_flag=False)
    workspace = make_workspace(root, publishable, manifest_skipped)
    configuration = make_config(exclude=())

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (publishable,)
    assert plan.skipped_manifest == (manifest_skipped,)
    assert plan.skipped_configuration == ()


def test_plan_publication_records_missing_exclusions(tmp_path: Path) -> None:
    """Configuration exclusions referencing missing crates are captured."""
    root = tmp_path.resolve()
    workspace = make_workspace(root)
    configuration = make_config(exclude=("missing",))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.missing_configuration_exclusions == ("missing",)


def test_plan_publication_records_multiple_missing_exclusions(
    tmp_path: Path,
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


def test_plan_publication_sorts_crates_by_name(tmp_path: Path) -> None:
    """Publishable and skipped crates appear in deterministic alphabetical order."""
    root = tmp_path.resolve()
    publishable_second = make_crate(root, "beta")
    publishable_first = make_crate(root, "alpha")
    manifest_skipped_late = make_crate(root, "epsilon", publish_flag=False)
    manifest_skipped_early = make_crate(root, "delta", publish_flag=False)
    config_skipped_late = make_crate(root, "theta")
    config_skipped_early = make_crate(root, "gamma")
    workspace = make_workspace(
        root,
        publishable_second,
        publishable_first,
        manifest_skipped_late,
        manifest_skipped_early,
        config_skipped_late,
        config_skipped_early,
    )
    configuration = make_config(exclude=("gamma", "theta"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == (publishable_first, publishable_second)
    assert plan.skipped_manifest == (manifest_skipped_early, manifest_skipped_late)
    assert plan.skipped_configuration == (config_skipped_early, config_skipped_late)


def test_plan_publication_multiple_configuration_skips(tmp_path: Path) -> None:
    """All configuration exclusions appear in the skipped configuration list."""
    root = tmp_path.resolve()
    gamma = make_crate(root, "gamma")
    delta = make_crate(root, "delta")
    workspace = make_workspace(root, gamma, delta)
    configuration = make_config(exclude=("delta", "gamma"))

    plan = publish.plan_publication(workspace, configuration)

    assert plan.publishable == ()
    assert plan.skipped_configuration == (delta, gamma)
