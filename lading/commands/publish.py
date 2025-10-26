"""Publication planning helpers for :mod:`lading.commands.publish`."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

from lading import config as config_module
from lading.utils.path import normalise_workspace_root
from lading.workspace import WorkspaceDependencyCycleError

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading.config import LadingConfig
    from lading.workspace import WorkspaceCrate, WorkspaceGraph


class PublishPlanError(RuntimeError):
    """Raised when the publish plan cannot be constructed."""


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

    publishable_by_name = {crate.name: crate for crate in publishable}
    publishable_names = set(publishable_by_name)

    if configured_order := configuration.publish.order:
        seen: set[str] = set()
        encountered: set[str] = set()
        duplicates: set[str] = set()
        unknown: list[str] = []
        ordered_publishable_list: list[WorkspaceCrate] = []

        for crate_name in configured_order:
            crate = publishable_by_name.get(crate_name)
            if crate is None:
                unknown.append(crate_name)
                continue
            if crate_name in encountered:
                duplicates.add(crate_name)
            else:
                encountered.add(crate_name)
            if crate_name not in seen:
                ordered_publishable_list.append(crate)
            seen.add(crate_name)

        missing = sorted(name for name in publishable_names if name not in seen)
        messages: list[str] = []
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            messages.append(f"Duplicate publish.order entries: {duplicate_list}")
        if unknown:
            unknown_list = ", ".join(unknown)
            messages.append(
                "publish.order references crates outside the publishable set: "
                f"{unknown_list}"
            )
        if missing:
            missing_list = ", ".join(missing)
            messages.append(f"publish.order omits publishable crate(s): {missing_list}")
        if messages:
            raise PublishPlanError("; ".join(messages))
        ordered_publishable = tuple(ordered_publishable_list)
    else:
        try:
            ordered_publishable = tuple(
                crate
                for crate in workspace.topologically_sorted_crates()
                if crate.name in publishable_names
            )
        except WorkspaceDependencyCycleError as exc:
            cycle_list = ", ".join(exc.cycle_nodes)
            message = "Cannot determine publish order due to dependency cycle"
            if cycle_list:
                message = f"{message} involving: {cycle_list}"
            raise PublishPlanError(message) from exc

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


def _format_crates_section(
    lines: list[str],
    crates: tuple[WorkspaceCrate, ...],
    *,
    header: str,
    empty_message: str | None = None,
) -> None:
    """Append publishable crate details to ``lines``.

    Parameters
    ----------
    lines : list[str]
        Mutable buffer that collects the formatted plan output lines.
    crates : tuple[WorkspaceCrate, ...]
        Publishable crates that should be listed with name and version.
    header : str
        Section header to prepend when publishable crates are present.
    empty_message : str | None, optional
        Message appended when ``crates`` is empty. When ``None`` (the
        default), the section contributes no lines.

    """
    if crates:
        lines.append(header)
        lines.extend(f"- {crate.name} @ {crate.version}" for crate in crates)
    elif empty_message is not None:
        lines.append(empty_message)


def _format_skipped_section(
    lines: list[str],
    crates: tuple[WorkspaceCrate, ...],
    *,
    header: str,
) -> None:
    """Append skipped crate names to ``lines``.

    Parameters
    ----------
    lines : list[str]
        Mutable buffer that collects the formatted plan output lines.
    crates : tuple[WorkspaceCrate, ...]
        Crates that were skipped from publication.
    header : str
        Section header to prepend when skipped crates are present.

    """
    if crates:
        lines.append(header)
        lines.extend(f"- {crate.name}" for crate in crates)


def _format_names_section(
    lines: list[str],
    names: tuple[str, ...],
    *,
    header: str,
) -> None:
    """Append generic name entries to ``lines``.

    Parameters
    ----------
    lines : list[str]
        Mutable buffer that collects the formatted plan output lines.
    names : tuple[str, ...]
        Arbitrary string names to list under the section.
    header : str
        Section header to prepend when names are present.

    """
    if names:
        lines.append(header)
        lines.extend(f"- {name}" for name in names)


def _format_plan(
    plan: PublishPlan, *, strip_patches: config_module.StripPatchesSetting
) -> str:
    """Render ``plan`` to a human-readable summary for CLI output."""
    lines = [
        f"Publish plan for {plan.workspace_root}",
        f"Strip patch strategy: {strip_patches}",
    ]

    _format_crates_section(
        lines,
        plan.publishable,
        header=f"Crates to publish ({len(plan.publishable)}):",
        empty_message="Crates to publish: none",
    )
    _format_skipped_section(
        lines,
        plan.skipped_manifest,
        header="Skipped (publish = false):",
    )
    _format_skipped_section(
        lines,
        plan.skipped_configuration,
        header="Skipped via publish.exclude:",
    )
    _format_names_section(
        lines,
        plan.missing_configuration_exclusions,
        header="Configured exclusions not found in workspace:",
    )

    return "\n".join(lines)


def _ensure_configuration(
    configuration: LadingConfig | None, workspace_root: Path
) -> LadingConfig:
    """Return the active configuration, loading it from disk when required."""
    if configuration is not None:
        return configuration

    try:
        return config_module.current_configuration()
    except config_module.ConfigurationNotLoadedError:
        return config_module.load_configuration(workspace_root)


def _ensure_workspace(
    workspace: WorkspaceGraph | None, workspace_root: Path
) -> WorkspaceGraph:
    """Return the workspace graph rooted at ``workspace_root``."""
    if workspace is not None:
        return workspace

    from lading.workspace import WorkspaceModelError, load_workspace

    try:
        return load_workspace(workspace_root)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
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
