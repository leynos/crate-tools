"""Publication planning helpers for :mod:`lading.commands.publish`."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

from lading import config as config_module
from lading.utils.path import normalise_workspace_root

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading.config import LadingConfig
    from lading.workspace import WorkspaceCrate, WorkspaceGraph

T = typ.TypeVar("T")


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
    """Return the :class:`PublishPlan` for ``workspace`` and ``configuration``.

    Parameters
    ----------
    workspace : WorkspaceGraph
        Workspace graph describing the crates that may be published.
    configuration : LadingConfig
        Publish configuration specifying which crates should be skipped.
    workspace_root : Path | None, optional
        Override for the workspace root path. When ``None`` (the default),
        ``workspace.workspace_root`` is used instead.

    Returns
    -------
    PublishPlan
        The computed publication plan for the workspace and configuration.
    """
    root_path = workspace.workspace_root if workspace_root is None else workspace_root
    configured_exclusions = tuple(configuration.publish.exclude)
    exclusion_set = set(configured_exclusions)
    publishable: list[WorkspaceCrate] = []
    skipped_manifest: list[WorkspaceCrate] = []
    skipped_configuration: list[WorkspaceCrate] = []

    workspace_crates = workspace.crates
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
        sorted(name for name in configured_exclusions if name not in crate_names)
    )

    ordered_publishable = tuple(sorted(publishable, key=lambda crate: crate.name))
    ordered_skipped_manifest = tuple(
        sorted(skipped_manifest, key=lambda crate: crate.name)
    )
    ordered_skipped_configuration = tuple(
        sorted(skipped_configuration, key=lambda crate: crate.name)
    )

    return PublishPlan(
        workspace_root=root_path,
        publishable=ordered_publishable,
        skipped_manifest=ordered_skipped_manifest,
        skipped_configuration=ordered_skipped_configuration,
        missing_configuration_exclusions=missing_exclusions,
    )


def _format_section(
    items: tuple[T, ...],
    *,
    header: str,
    item_formatter: typ.Callable[[T], str],
    empty_lines: tuple[str, ...] = (),
) -> list[str]:
    """Return ``header`` and formatted ``items`` when any are present."""
    if not items:
        return list(empty_lines)

    formatted_items = [item_formatter(item) for item in items]
    return [header, *formatted_items]


def _format_plan(
    plan: PublishPlan, *, strip_patches: config_module.StripPatchesSetting
) -> str:
    """Render ``plan`` to a human-readable summary for CLI output."""
    lines = [
        f"Publish plan for {plan.workspace_root}",
        f"Strip patch strategy: {strip_patches}",
    ]

    lines.extend(
        _format_section(
            plan.publishable,
            header=f"Crates to publish ({len(plan.publishable)}):",
            item_formatter=lambda crate: f"- {crate.name} @ {crate.version}",
            empty_lines=("Crates to publish: none",),
        )
    )
    lines.extend(
        _format_section(
            plan.skipped_manifest,
            header="Skipped (publish = false):",
            item_formatter=lambda crate: f"- {crate.name}",
        )
    )
    lines.extend(
        _format_section(
            plan.skipped_configuration,
            header="Skipped via publish.exclude:",
            item_formatter=lambda crate: f"- {crate.name}",
        )
    )
    lines.extend(
        _format_section(
            plan.missing_configuration_exclusions,
            header="Configured exclusions not found in workspace:",
            item_formatter=lambda name: f"- {name}",
        )
    )

    return "\n".join(lines)


def _ensure_configuration(
    configuration: LadingConfig | None, workspace_root: Path
) -> LadingConfig:
    """Return active configuration, loading it if necessary."""
    if configuration is not None:
        return configuration

    try:
        return config_module.current_configuration()
    except config_module.ConfigurationNotLoadedError:
        return config_module.load_configuration(workspace_root)


def _ensure_workspace(
    workspace: WorkspaceGraph | None, workspace_root: Path
) -> WorkspaceGraph:
    """Return workspace graph, loading it if necessary."""
    if workspace is not None:
        return workspace

    from lading.workspace import WorkspaceModelError, load_workspace

    try:
        return load_workspace(workspace_root)
    except FileNotFoundError as exc:
        message = f"Workspace root not found: {workspace_root}"
        raise WorkspaceModelError(message) from exc


def run(
    workspace_root: Path,
    configuration: LadingConfig | None = None,
    workspace: WorkspaceGraph | None = None,
) -> str:
    """Plan crate publication for ``workspace_root``."""
    root_path = normalise_workspace_root(workspace_root)
    active_configuration = _ensure_configuration(configuration, root_path)
    active_workspace = _ensure_workspace(workspace, root_path)

    plan = plan_publication(
        active_workspace, active_configuration, workspace_root=root_path
    )
    return _format_plan(plan, strip_patches=active_configuration.publish.strip_patches)
