"""Command-line interface for the :mod:`lading` toolkit."""

from __future__ import annotations

import os
import sys
import typing as typ
from contextlib import contextmanager
from pathlib import Path

from cyclopts import App, Parameter

from . import commands, config
from .utils import normalise_workspace_root

WORKSPACE_ROOT_ENV_VAR = "LADING_WORKSPACE_ROOT"
WORKSPACE_ROOT_REQUIRED_MESSAGE = "--workspace-root requires a value"
_WORKSPACE_PARAMETER = Parameter(
    name="workspace-root",
    env_var=WORKSPACE_ROOT_ENV_VAR,
    help="Path to the Rust workspace root.",
)
WorkspaceRootOption = typ.Annotated[Path, _WORKSPACE_PARAMETER]

app = App(help="Manage Rust workspaces with the lading toolkit.")


def _validate_workspace_value(value: str) -> str:
    """Ensure ``value`` is usable as a workspace path."""
    if not value or value.startswith("-"):
        raise SystemExit(WORKSPACE_ROOT_REQUIRED_MESSAGE)
    return value


def _parse_workspace_flag(tokens: typ.Sequence[str], index: int) -> tuple[str, int]:
    """Parse ``--workspace-root <path>`` form starting at ``index``."""
    try:
        candidate = tokens[index + 1]
    except IndexError as err:
        raise SystemExit(WORKSPACE_ROOT_REQUIRED_MESSAGE) from err
    workspace = _validate_workspace_value(candidate)
    return workspace, index + 2


def _parse_workspace_equals(argument: str, index: int) -> tuple[str, int]:
    """Parse ``--workspace-root=<path>`` form for ``argument``."""
    candidate = argument.partition("=")[2]
    workspace = _validate_workspace_value(candidate)
    return workspace, index + 1


def _extract_workspace_override(
    tokens: typ.Sequence[str],
) -> tuple[str | None, list[str]]:
    """Split ``--workspace-root`` from CLI tokens.

    The flag can appear in either ``--workspace-root <path>`` or
    ``--workspace-root=<path>`` form. The last occurrence wins, matching
    common CLI conventions. The returned token list can be passed directly
    to :func:`cyclopts.App.__call__`.
    """
    workspace: str | None = None
    remainder: list[str] = []
    index = 0
    while index < len(tokens):
        current_argument = tokens[index]
        if current_argument == "--workspace-root":
            workspace, index = _parse_workspace_flag(tokens, index)
            continue
        if current_argument.startswith("--workspace-root="):
            workspace, index = _parse_workspace_equals(current_argument, index)
            continue
        remainder.append(current_argument)
        index += 1
    return workspace, remainder


@contextmanager
def _workspace_env(value: Path) -> typ.Iterator[None]:
    """Temporarily set :data:`WORKSPACE_ROOT_ENV_VAR` to ``value``."""
    previous = os.environ.get(WORKSPACE_ROOT_ENV_VAR)
    os.environ[WORKSPACE_ROOT_ENV_VAR] = str(value)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(WORKSPACE_ROOT_ENV_VAR, None)
        else:
            os.environ[WORKSPACE_ROOT_ENV_VAR] = previous


def _dispatch_and_print(tokens: typ.Sequence[str]) -> int:
    """Execute the Cyclopts app and print command results."""
    try:
        result = app(tokens)
    except SystemExit as err:
        code = err.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    if isinstance(result, int):
        return result
    if result is not None:
        print(result)
    return 0


def main(argv: typ.Sequence[str] | None = None) -> int:
    """Entry point for ``python -m lading.cli``."""
    try:
        if argv is None:
            argv = sys.argv[1:]
        workspace_override, remaining = _extract_workspace_override(list(argv))
        workspace_root = normalise_workspace_root(workspace_override)
        if not remaining:
            _dispatch_and_print(remaining)  # Print usage message
            return 2  # Standard exit code for missing subcommand
        previous_config = app.config
        config_loader = config.build_loader(workspace_root)
        try:
            configuration = config.load_from_loader(config_loader)
        except config.ConfigurationError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 1
        app.config = (config_loader,)
        try:
            with (
                _workspace_env(workspace_root),
                config.use_configuration(configuration),
            ):
                return _dispatch_and_print(remaining)
        finally:
            app.config = previous_config
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - fallback guard for CLI entry point
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


def _run_with_configuration(
    workspace_root: Path,
    runner: typ.Callable[[Path, config.LadingConfig], str],
) -> str:
    """Execute ``runner`` with a configuration, loading it on demand."""
    try:
        configuration = config.current_configuration()
    except config.ConfigurationNotLoadedError:
        configuration = config.load_configuration(workspace_root)
        with config.use_configuration(configuration):
            return runner(workspace_root, configuration)
    return runner(workspace_root, configuration)


@app.command
def bump(
    workspace_root: WorkspaceRootOption | None = None,
) -> str:
    """Return placeholder acknowledgement for the ``bump`` subcommand."""
    resolved = normalise_workspace_root(workspace_root)
    return _run_with_configuration(resolved, commands.bump.run)


@app.command
def publish(
    workspace_root: WorkspaceRootOption | None = None,
) -> str:
    """Return placeholder acknowledgement for the ``publish`` subcommand."""
    resolved = normalise_workspace_root(workspace_root)
    return _run_with_configuration(resolved, commands.publish.run)


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    raise SystemExit(main())
