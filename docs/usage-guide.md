# Lading Usage Guide

The `lading` command-line tool orchestrates versioning and publication tasks
for Rust workspaces. This guide documents the CLI scaffolding introduced in
roadmap Step 1.1 and the manifest version propagation delivered in Step 2.1.

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

[bump.documentation]
globs = ["README.md", "docs/**/*.md"]

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

`bump` synchronises manifest versions across the workspace. The command
requires the target version as a positional argument and rejects inputs that do
not match the `<major>.<minor>.<patch>` semantic version pattern, while
allowing optional pre-release and build metadata. All validation happens before
the command loads workspace metadata, so mistakes fail fast.

When the version string passes validation, `bump` updates the workspace
`Cargo.toml` and each member crate's manifest, unless the crate name appears in
`bump.exclude` within `lading.toml`.

```bash
python -m lading.cli --workspace-root /workspace/path bump 1.2.3
```

Running the command updates:

- `workspace.package.version` and any root `[package]` entry inside the main
  `Cargo.toml`.
- `package.version` for each workspace crate not listed in `bump.exclude`.
- Dependency requirements in `[dependencies]`, `[dev-dependencies]`, and
  `[build-dependencies]` sections when they point to workspace members whose
  versions were bumped. Existing requirement operators such as `^` or `~` are
  preserved, and other inline options (for example `path = "../crate"`) remain
  untouched.
- Markdown files matching any glob configured under `bump.documentation.globs`.
  Each TOML fence in those files is parsed with `tomlkit` so that `[package]`,
  `[workspace.package]`, and dependency entries that name workspace crates
  inherit the new version while preserving indentation and fence metadata.

`lading` prints a short summary that lists every file it touched. For example:

```text
Updated version to 1.2.3 in 3 manifest(s):
- Cargo.toml
- crates/alpha/Cargo.toml
- crates/beta/Cargo.toml
```

All paths are relative to the workspace root. Documentation files appear in the
same list with a `(documentation)` suffix, and the summary prefix reports both
manifest and documentation counts. When every manifest already records the
requested version, the CLI reports: `No manifest changes required; all versions
already 1.2.3.`

Pass `--dry-run` to preview the same summary without writing to disk.
Example:

```text
Dry run; would update version to 1.2.3 in 3 manifest(s):
- Cargo.toml
- crates/alpha/Cargo.toml
- crates/beta/Cargo.toml
```

### `publish`

`publish` now produces a publication plan for the workspace. The command reads
`publish.exclude` from `lading.toml`, honours any crate manifests that declare
`publish = false`, and prints a structured summary listing the crates that will
be published. Additional sections document crates skipped by manifest flags or
configuration, along with any exclusion entries that do not match a workspace
crate. This early feedback allows release engineers to validate the plan before
later roadmap steps begin executing pre-flight checks and cargo commands.

```bash
python -m lading.cli --workspace-root /workspace/path publish
```

Example output:

```text
Publish plan for /workspace/path
Strip patch strategy: all
Crates to publish (1):
- alpha @ 0.1.0
```

When the configuration excludes additional crates, or a manifest sets the
`publish = false` flag, the plan prints dedicated sections so the reasons for
skipping crates are visible to the operator.

## Testing hooks

Behavioural tests invoke the CLI as an external process and spy on the `python`
executable with [`cmd-mox`](./cmd-mox-usage-guide.md). This pattern keeps the
tests faithful to real user interactions while still providing strict control
over command invocations. Use the same approach when adding new end-to-end
scenarios.

## Workspace discovery helpers

Roadmap Step 1.2 introduces a thin wrapper around `cargo metadata` to expose
workspace information to both commands and library consumers. Import
`lading.workspace.load_cargo_metadata` to execute the command with the current
or explicitly provided workspace root:

```python
from pathlib import Path

from lading.workspace import load_cargo_metadata

metadata = load_cargo_metadata(Path("/path/to/workspace"))
print(metadata["workspace_root"])
```

The helper normalises the workspace path, invokes
`cargo metadata --format-version 1` using `plumbum`, and returns the parsed
JSON mapping. Any execution errors or invalid output raise `CargoMetadataError`
with a descriptive message so callers can present actionable feedback to users.

### Workspace graph model

`load_workspace` converts the raw metadata into a strongly typed
`WorkspaceGraph` model backed by `msgspec.Struct` definitions. The graph lists
each crate, its manifest path, publication status, and any dependencies on
other workspace members. The message returned by the CLI mirrors this
information so that users can confirm discovery succeeded before later roadmap
features begin mutating manifests.

```python
from pathlib import Path

from lading.workspace import load_workspace

workspace = load_workspace(Path("/path/to/workspace"))
print([crate.name for crate in workspace.crates])
```

The builder reads each crate manifest with `tomlkit` to detect
`readme.workspace = true` directives while preserving document structure for
future round-tripping.
