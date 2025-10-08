# Lading Usage Guide

The `lading` command-line tool orchestrates versioning and publication tasks
for Rust workspaces. This guide documents the CLI scaffolding introduced in
roadmap Step 1.1 and will expand as additional behaviour lands.

## Installation and invocation

The CLI ships with the repository and can be executed via the `lading` console
script or directly with Python:

```bash
uv run lading --help
```

The console script resolves to :func:`lading.cli.main`. Invoking the
implementation module remains supported for development workflows:

```bash
uv run python -m lading.cli --help
```

## Global options

### `--workspace-root <path>`

Specify the root of the Rust workspace that `lading` should operate on. The
flag can appear before or after the subcommand:

```bash
python -m lading.cli --workspace-root /path/to/workspace bump
python -m lading.cli bump --workspace-root /path/to/workspace
```

If the flag is omitted, the CLI defaults to the current working directory. The
resolved path is also exported as the `LADING_WORKSPACE_ROOT` environment
variable so that downstream helpers and configuration loading can share the
location without re-parsing CLI arguments.

## Configuration file: `lading.toml`

`lading` expects a `lading.toml` file at the workspace root. The CLI resolves
the workspace directory, uses `cyclopts`' TOML loader to read the file, and
exposes the resulting configuration to the active command. The configuration is
validated with a dataclass-backed model to ensure that string lists and boolean
flags conform to the schema described in the design document.

An example minimal configuration looks like:

```toml
[bump]
doc_files = ["README.md"]

[publish]
strip_patches = "all"
```

If the file is missing or contains invalid values the CLI prints a descriptive
error and exits with a non-zero status. Commands invoked programmatically via
`python -m lading.cli` load the configuration on demand, so helper scripts and
tests can continue to exercise the commands directly as long as the file is
present.

## Subcommands

### `bump`

The `bump` command currently emits a placeholder acknowledgement confirming the
selected workspace and summarising the documentation files listed in the
configuration. Future roadmap items will replace this with the version
propagation workflow described in the design document.

```bash
python -m lading.cli --workspace-root /workspace/path bump
```

### `publish`

`publish` is scaffolded in the same fashion. It acknowledges the workspace,
reports the configured `strip_patches` strategy, and returns successfully.
Publication planning and execution will arrive in later phases of the roadmap.

```bash
python -m lading.cli --workspace-root /workspace/path publish
```

## Testing hooks

Behavioural tests invoke the CLI as an external process and spy on the
`python` executable with [`cmd-mox`](./cmd-mox-usage-guide.md). This pattern
keeps the tests faithful to real user interactions while still providing strict
control over command invocations. Use the same approach when adding new
end-to-end scenarios.

## Workspace discovery helpers
Roadmap Step 1.2 introduces a thin wrapper around `cargo metadata` to
expose workspace information to both commands and library consumers.
Import `lading.workspace.load_cargo_metadata` to execute the command
with the current or explicitly provided workspace root:

```python
from pathlib import Path

from lading.workspace import load_cargo_metadata

metadata = load_cargo_metadata(Path("/path/to/workspace"))
print(metadata["workspace_root"])
```

The helper normalises the workspace path, invokes `cargo metadata --
format-version 1` using `plumbum`, and returns the parsed JSON mapping.
Any execution errors or invalid output raise `CargoMetadataError` with a
descriptive message so callers can present actionable feedback to users.
