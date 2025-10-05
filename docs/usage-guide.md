# Lading Usage Guide

The `lading` command-line tool orchestrates versioning and publication tasks
for Rust workspaces. This guide documents the CLI scaffolding introduced in
roadmap Step 1.1 and will expand as additional behaviour lands.

## Installation and invocation

The CLI ships with the repository. You can execute it directly with Python or
via `uv`:

```bash
uv run python -m lading.cli --help
```

The entry point lives in `lading/cli.py`; running `python -m lading.cli` is the
supported launch mechanism during the early development stages.

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

## Subcommands

### `bump`

The `bump` command currently emits a placeholder acknowledgement confirming the
selected workspace. Future roadmap items will replace this with the version
propagation workflow described in the design document.

```bash
python -m lading.cli --workspace-root /workspace/path bump
```

### `publish`

`publish` is scaffolded in the same fashion. It acknowledges the workspace and
returns successfully. Publication planning and execution will arrive in later
phases of the roadmap.

```bash
python -m lading.cli --workspace-root /workspace/path publish
```

## Testing hooks

Behavioural tests invoke the CLI as an external process and spy on the
`python` executable with [`cmd-mox`](./cmd-mox-usage-guide.md). This pattern
keeps the tests faithful to real user interactions while still providing strict
control over command invocations. Use the same approach when adding new
end-to-end scenarios.
