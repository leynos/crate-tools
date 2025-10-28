"""Publication planning helpers for :mod:`lading.commands.publish`."""

from __future__ import annotations

import dataclasses as dc
import shutil
import tempfile
import typing as typ
from pathlib import Path

from lading import config as config_module
from lading.utils.path import normalise_workspace_root
from lading.workspace import WorkspaceDependencyCycleError

if typ.TYPE_CHECKING:
    from lading.config import LadingConfig
    from lading.workspace import WorkspaceCrate, WorkspaceGraph


class PublishPlanError(RuntimeError):
    """Raised when the publish plan cannot be constructed."""


class PublishPreparationError(RuntimeError):
    """Raised when publish preparation cannot stage required assets."""


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


@dc.dataclass(frozen=True, slots=True)
class PublishOptions:
    """Configuration for publish command execution."""

    build_directory: Path | None = None


@dc.dataclass(frozen=True, slots=True)
class PublishPreparation:
    """Details about the staged workspace copy."""

    staging_root: Path
    copied_readmes: tuple[Path, ...]


def _categorize_crates(
    workspace_crates: typ.Sequence[WorkspaceCrate],
    exclusion_set: set[str],
) -> tuple[list[WorkspaceCrate], list[WorkspaceCrate], list[WorkspaceCrate]]:
    """Split workspace crates into publishable and skipped categories."""
    publishable: list[WorkspaceCrate] = []
    skipped_manifest: list[WorkspaceCrate] = []
    skipped_configuration: list[WorkspaceCrate] = []

    for crate in workspace_crates:
        if not crate.publish:
            skipped_manifest.append(crate)
        elif crate.name in exclusion_set:
            skipped_configuration.append(crate)
        else:
            publishable.append(crate)

    return publishable, skipped_manifest, skipped_configuration


def _process_order_and_collect_errors(
    configured_order: typ.Sequence[str],
    publishable_by_name: dict[str, WorkspaceCrate],
) -> tuple[list[WorkspaceCrate], set[str], set[str], list[str]]:
    """Collect ordering results and validation state for ``configured_order``.

    The helper iterates the configured publish order once to gather the
    resolved publishable crates alongside the bookkeeping needed for later
    validation. Callers receive the ordered crates, all names that were seen,
    the set of duplicate entries, and any references to unknown crates.
    """
    ordered_crates: list[WorkspaceCrate] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    unknown_names: list[str] = []

    for crate_name in configured_order:
        crate = publishable_by_name.get(crate_name)
        if crate is None:
            unknown_names.append(crate_name)
            continue
        if crate_name in seen:
            duplicates.add(crate_name)
        else:
            ordered_crates.append(crate)
            seen.add(crate_name)

    return ordered_crates, seen, duplicates, unknown_names


def _build_order_validation_messages(
    duplicates: typ.AbstractSet[str],
    unknown: typ.Sequence[str],
    missing: typ.Sequence[str],
) -> list[str]:
    """Render validation failure messages for publish order problems.

    Parameters
    ----------
    duplicates : Collection[str]
        Configured crate names that appeared more than once.
    unknown : Sequence[str]
        Configured crate names not present in the publishable set.
    missing : Sequence[str]
        Publishable crate names omitted from the configuration.

    Returns
    -------
    list[str]
        Formatted error messages matching the existing publish planner output.

    """
    messages: list[str] = []
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        messages.append(f"Duplicate publish.order entries: {duplicate_list}")
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        messages.append(
            "publish.order references crates outside the publishable set: "
            f"{unknown_list}"
        )
    if missing:
        missing_list = ", ".join(missing)
        messages.append(f"publish.order omits publishable crate(s): {missing_list}")
    return messages


def _resolve_configured_order(
    publishable_by_name: dict[str, WorkspaceCrate],
    configured_order: typ.Sequence[str],
) -> tuple[WorkspaceCrate, ...]:
    """Validate and return crates ordered according to configuration."""
    publishable_names = set(publishable_by_name)
    (
        ordered_publishable_list,
        seen_names,
        duplicates,
        unknown,
    ) = _process_order_and_collect_errors(
        configured_order,
        publishable_by_name,
    )
    missing = sorted(name for name in publishable_names if name not in seen_names)
    messages = _build_order_validation_messages(duplicates, unknown, missing)
    if messages:
        raise PublishPlanError("; ".join(messages))
    return tuple(ordered_publishable_list)


def _resolve_topological_order(
    workspace: WorkspaceGraph, publishable_names: set[str]
) -> tuple[WorkspaceCrate, ...]:
    """Return publishable crates ordered by workspace dependencies."""
    try:
        publishable_crates = tuple(
            crate for crate in workspace.crates if crate.name in publishable_names
        )
        subgraph = workspace.__class__(
            workspace_root=workspace.workspace_root,
            crates=publishable_crates,
        )
        return subgraph.topologically_sorted_crates()
    except WorkspaceDependencyCycleError as exc:
        cycle_list = ", ".join(exc.cycle_nodes)
        message = "Cannot determine publish order due to dependency cycle"
        if cycle_list:
            message = f"{message} involving: {cycle_list}"
        raise PublishPlanError(message) from exc


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

    workspace_crates = workspace.crates
    publishable, skipped_manifest, skipped_configuration = _categorize_crates(
        workspace_crates,
        exclusion_set,
    )
    crate_names = {crate.name for crate in workspace_crates}

    missing_exclusions = tuple(
        sorted(name for name in configured_exclusions if name not in crate_names)
    )

    publishable_by_name = {crate.name: crate for crate in publishable}
    publishable_names = set(publishable_by_name)

    if configured_order := configuration.publish.order:
        ordered_publishable = _resolve_configured_order(
            publishable_by_name,
            configured_order,
        )
    else:
        ordered_publishable = _resolve_topological_order(
            workspace,
            publishable_names,
        )

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


def _append_section[T](
    lines: list[str],
    items: typ.Sequence[T],
    *,
    header: str,
    formatter: typ.Callable[[T], str] = str,
) -> None:
    """Append formatted ``items`` to ``lines`` when a section has content.

    Parameters
    ----------
    lines : list[str]
        Mutable buffer that collects the formatted plan output lines.
    items : Sequence[T]
        Items that should be included in the formatted section.
    header : str
        Section header to prepend when ``items`` are present.
    formatter : Callable[[T], str], optional
        Callable that formats each item into a string for display. Defaults to
        :class:`str` to make simple string sequences ergonomic.

    """
    if items:
        lines.append(header)
        lines.extend(f"- {formatter(item)}" for item in items)


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
    _append_section(
        lines,
        plan.skipped_manifest,
        header="Skipped (publish = false):",
        formatter=lambda crate: crate.name,
    )
    _append_section(
        lines,
        plan.skipped_configuration,
        header="Skipped via publish.exclude:",
        formatter=lambda crate: crate.name,
    )
    _append_section(
        lines,
        plan.missing_configuration_exclusions,
        header="Configured exclusions not found in workspace:",
    )

    return "\n".join(lines)


def _normalise_build_directory(
    workspace_root: Path, build_directory: Path | None
) -> Path:
    """Return a directory suitable for staging workspace artifacts."""
    if build_directory is None:
        return Path(tempfile.mkdtemp(prefix="lading-publish-"))

    candidate = Path(build_directory).expanduser()
    candidate = candidate.resolve(strict=False)

    workspace_root = workspace_root.resolve(strict=True)
    candidate_resolved = candidate
    if candidate_resolved.is_relative_to(workspace_root):
        message = "Publish build directory cannot reside within the workspace root"
        raise PublishPreparationError(message)

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate_resolved


def _copy_workspace_tree(workspace_root: Path, build_directory: Path) -> Path:
    """Copy ``workspace_root`` into ``build_directory`` and return the clone."""
    workspace_root = workspace_root.resolve(strict=True)
    staging_root = build_directory / workspace_root.name
    if staging_root.resolve(strict=False).is_relative_to(workspace_root):
        message = "Publish staging directory cannot be nested inside the workspace root"
        raise PublishPreparationError(message)
    if staging_root.exists():
        shutil.rmtree(staging_root)
    shutil.copytree(workspace_root, staging_root)
    return staging_root


def _collect_workspace_readme_targets(
    workspace: WorkspaceGraph,
) -> tuple[WorkspaceCrate, ...]:
    """Return crates that opt into using the workspace README."""
    return tuple(crate for crate in workspace.crates if crate.readme_is_workspace)


def _stage_workspace_readmes(
    *,
    crates: tuple[WorkspaceCrate, ...],
    workspace_root: Path,
    staging_root: Path,
) -> list[Path]:
    """Copy the workspace README into ``crates`` located at ``staging_root``."""
    if not crates:
        return []

    workspace_readme = workspace_root / "README.md"
    if not workspace_readme.exists():
        message = (
            "Workspace README.md is required by crates that set readme.workspace = true"
        )
        raise PublishPreparationError(message)

    copied: list[Path] = []
    for crate in crates:
        try:
            relative_crate_root = crate.root_path.relative_to(workspace_root)
        except ValueError as exc:
            message = (
                "Crate "
                f"{crate.name!r} is outside the workspace root; "
                "cannot stage README"
            )
            raise PublishPreparationError(message) from exc
        staged_crate_root = staging_root / relative_crate_root
        staged_crate_root.mkdir(parents=True, exist_ok=True)
        staged_readme = staged_crate_root / "README.md"
        shutil.copyfile(workspace_readme, staged_readme)
        copied.append(staged_readme)

    copied.sort(key=lambda path: path.relative_to(staging_root).as_posix())
    return copied


def prepare_workspace(
    plan: PublishPlan,
    workspace: WorkspaceGraph,
    *,
    options: PublishOptions | None = None,
) -> PublishPreparation:
    """Stage a workspace copy and propagate workspace READMEs."""
    active_options = PublishOptions() if options is None else options
    build_directory = _normalise_build_directory(
        plan.workspace_root, active_options.build_directory
    )
    staging_root = _copy_workspace_tree(plan.workspace_root, build_directory)
    readme_crates = _collect_workspace_readme_targets(workspace)
    copied_readmes = tuple(
        _stage_workspace_readmes(
            crates=readme_crates,
            workspace_root=plan.workspace_root,
            staging_root=staging_root,
        )
    )
    return PublishPreparation(staging_root=staging_root, copied_readmes=copied_readmes)


def _format_preparation_summary(preparation: PublishPreparation) -> tuple[str, ...]:
    """Return formatted summary lines for staging results."""
    lines = [f"Staged workspace at: {preparation.staging_root}"]
    if preparation.copied_readmes:
        lines.append("Copied workspace README to:")
        for path in preparation.copied_readmes:
            try:
                relative_path = path.relative_to(preparation.staging_root)
            except ValueError:
                relative_path = path
            lines.append(f"- {relative_path}")
    else:
        lines.append("Copied workspace README to: none required")
    return tuple(lines)


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
    *,
    options: PublishOptions | None = None,
) -> str:
    """Plan crate publication for ``workspace_root``."""
    root_path = normalise_workspace_root(workspace_root)

    active_configuration = _ensure_configuration(configuration, root_path)
    active_workspace = _ensure_workspace(workspace, root_path)

    plan = plan_publication(
        active_workspace, active_configuration, workspace_root=root_path
    )
    preparation = prepare_workspace(plan, active_workspace, options=options)
    plan_message = _format_plan(
        plan, strip_patches=active_configuration.publish.strip_patches
    )
    summary_lines = _format_preparation_summary(preparation)
    return f"{plan_message}\n\n" + "\n".join(summary_lines)
