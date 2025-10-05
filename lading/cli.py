"""Command-line interface for the :mod:`lading` toolkit."""

from __future__ import annotations

import os
import sys
import typing as typ
from contextlib import contextmanager
from pathlib import Path

from cyclopts import App, Parameter
from plumbum import local

from . import commands

WORKSPACE_ROOT_ENV_VAR = "LADING_WORKSPACE_ROOT"
WORKSPACE_ROOT_REQUIRED_MESSAGE = "--workspace-root requires a value"
_WORKSPACE_PARAMETER = Parameter(
    name="workspace-root",
    env_var=WORKSPACE_ROOT_ENV_VAR,
    help="Path to the Rust workspace root.",
)
WorkspaceRootOption = typ.Annotated[Path, _WORKSPACE_PARAMETER]

app = App(help="Manage Rust workspaces with the lading toolkit.")


def _normalise_workspace_root(value: Path | str | None) -> Path:
    """Return an absolute workspace path with ``~`` expanded."""
    if value is None:
        return Path.cwd().resolve()
    candidate = local.path(str(value))
    expanded = Path(str(candidate)).expanduser()
    return expanded.resolve(strict=False)


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
            try:
                workspace = tokens[index + 1]
            except IndexError as err:
                raise SystemExit(WORKSPACE_ROOT_REQUIRED_MESSAGE) from err
            if workspace.startswith("-"):
                raise SystemExit(WORKSPACE_ROOT_REQUIRED_MESSAGE)
            index += 2
            continue
        if current_argument.startswith("--workspace-root="):
            workspace = current_argument.partition("=")[2]
            if not workspace:
                raise SystemExit(WORKSPACE_ROOT_REQUIRED_MESSAGE)
            index += 1
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
    result = app(tokens)
    if isinstance(result, int):
        return result
    if result is not None:
        print(result)
    return 0


def main(argv: typ.Sequence[str] | None = None) -> int:
    """Entry point for ``python -m lading.cli``."""
    if argv is None:
        argv = sys.argv[1:]
    workspace_override, remaining = _extract_workspace_override(list(argv))
    workspace_root = _normalise_workspace_root(workspace_override)
    with _workspace_env(workspace_root):
        return _dispatch_and_print(remaining)


@app.command
def bump(
    workspace_root: WorkspaceRootOption | None = None,
) -> str:
    """Return placeholder acknowledgement for the ``bump`` subcommand."""
    resolved = _normalise_workspace_root(workspace_root)
    return commands.bump.run(resolved)


@app.command
def publish(
    workspace_root: WorkspaceRootOption | None = None,
) -> str:
    """Return placeholder acknowledgement for the ``publish`` subcommand."""
    resolved = _normalise_workspace_root(workspace_root)
    return commands.publish.run(resolved)


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    raise SystemExit(main())
