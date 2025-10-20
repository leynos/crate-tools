"""Publication planning helpers for :mod:`lading.publish`."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

from lading import config as config_module
from lading.utils import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading.config import LadingConfig
    from lading.workspace import WorkspaceCrate, WorkspaceGraph


@dc.dataclass(frozen=True, slots=True)
class PublishPlan:
    """Describe which crates should be published from a workspace."""

    workspace_root: Path
    publishable: tuple[WorkspaceCrate, ...]
    skipped_manifest: tuple[WorkspaceCrate, ...]
    skipped_configuration: tuple[WorkspaceCrate, ...]
    missing_configuration_exclusions: tuple[str, ...] = ()

    @property
    def publishable_names(self) -> tuple[str, ...]:
        """Return the names of crates scheduled for publication."""
        return tuple(crate.name for crate in self.publishable)


def plan_publication(
    workspace: WorkspaceGraph,
    configuration: LadingConfig,
    *,
    workspace_root: Path | None = None,
) -> PublishPlan:
    """Return the :class:`PublishPlan` for ``workspace`` and ``configuration``."""
    root_path = workspace.workspace_root if workspace_root is None else workspace_root
    configured_exclusions = tuple(configuration.publish.exclude)
    exclusion_set = set(configured_exclusions)
    publishable: list[WorkspaceCrate] = []
    skipped_manifest: list[WorkspaceCrate] = []
    skipped_configuration: list[WorkspaceCrate] = []

    workspace_crates = tuple(workspace.crates)
    crate_names = {crate.name for crate in workspace_crates}

    for crate in workspace_crates:
        if not crate.publish:
            skipped_manifest.append(crate)
            continue
        if crate.name in exclusion_set:
            skipped_configuration.append(crate)
            continue
        publishable.append(crate)

    missing_exclusions = tuple(
        name for name in configured_exclusions if name not in crate_names
    )

    return PublishPlan(
        workspace_root=root_path,
        publishable=tuple(publishable),
        skipped_manifest=tuple(skipped_manifest),
        skipped_configuration=tuple(skipped_configuration),
        missing_configuration_exclusions=missing_exclusions,
    )


def _format_plan(
    plan: PublishPlan, *, strip_patches: config_module.StripPatchesSetting
) -> str:
    """Render ``plan`` to a human-readable summary for CLI output."""
    lines = [
        f"Publish plan for {plan.workspace_root}",
        f"Strip patch strategy: {strip_patches}",
    ]

    if plan.publishable:
        lines.append(f"Crates to publish ({len(plan.publishable)}):")
        lines.extend(f"- {crate.name} @ {crate.version}" for crate in plan.publishable)
    else:
        lines.append("Crates to publish: none")

    if plan.skipped_manifest:
        lines.append("Skipped (publish = false):")
        lines.extend(f"- {crate.name}" for crate in plan.skipped_manifest)

    if plan.skipped_configuration:
        lines.append("Skipped via publish.exclude:")
        lines.extend(f"- {crate.name}" for crate in plan.skipped_configuration)

    if plan.missing_configuration_exclusions:
        lines.append("Configured exclusions not found in workspace:")
        lines.extend(f"- {name}" for name in plan.missing_configuration_exclusions)

    return "\n".join(lines)


def run(
    workspace_root: Path,
    configuration: LadingConfig | None = None,
    workspace: WorkspaceGraph | None = None,
) -> str:
    """Plan crate publication for ``workspace_root``."""
    root_path = normalise_workspace_root(workspace_root)
    if configuration is None:
        configuration = config_module.current_configuration()
    if workspace is None:
        from lading.workspace import load_workspace

        workspace = load_workspace(root_path)

    plan = plan_publication(workspace, configuration, workspace_root=root_path)
    return _format_plan(plan, strip_patches=configuration.publish.strip_patches)
