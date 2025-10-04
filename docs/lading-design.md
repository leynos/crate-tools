# Design Document: Lading Crate Management Tool

Version: 1.0\
Status: Proposed\
Date: 05 October 2025

## 1. Introduction

### 1.1. Purpose

This document specifies the design for a generalised, configuration-driven Python utility named `lading`. This tool will streamline versioning and publication workflows for arbitrary Rust workspaces. It is intended to supersede and replace the existing, repository-specific `bump_version.py` and `run_publish_check.py` scripts, abstracting their core logic into a reusable and robust command-line application.

### 1.2. Scope

The project encompasses the following key deliverables:

1. A unified command-line interface (CLI) tool, `lading`, built with `cyclopts`, providing `bump` and `publish` subcommands.
2. A single, unified TOML configuration file, `lading.toml`, to define workspace-specific behaviours, minimising the need for command-line arguments.
3. A workspace discovery mechanism that infers the dependency graph, crate locations, and publication order by parsing the output of `cargo metadata`.
4. A `bump` command to propagate version changes across the workspace, including `Cargo.toml` files for both the workspace and individual crates, and to synchronise documentation files.
5. A `publish` command to execute pre-publish checks and publish crates to a registry in the correct topological order, with support for both dry-run and live modes.
6. Support for the `readme.workspace = true` manifest key, ensuring the workspace's `README.md` is copied to member crates before packaging.

### 1.3. Goals

- **Decoupling:** Eliminate hardcoded paths, crate names, and repository-specific assumptions from the tooling.
- **Generalisation:** Create a tool that can be applied to any Rust workspace with minimal configuration.
- **Automation:** Reduce manual effort and the risk of human error in release processes.
- **Configuration over Code:** Favour declarative configuration in `lading.toml` over imperative logic within the tool itself.
- **Clarity and Maintainability:** Establish a clean, well-tested Python codebase that is easy to understand and extend.

### 1.4. Current coupling

#### `run_publish_check.py`
- The workflow is driven by the statically defined
  `PUBLISHABLE_CRATES` tuple imported from `publish_workspace_members`, which
  hard-codes the crate list and release ordering for this repository.
- Crate directories are resolved under `<workspace>/crates/<name>`, which only
  matches the current workspace layout and fails for workspaces that colocate
  crates elsewhere.
- Live publish commands and the locked publish variant are keyed off concrete
  crate names, making the publish pipeline unusable when the workspace contains
  a different set of packages.
- The dry-run mode packages one crate and checks others based on crate names,
  which will not hold in a generic workspace.

#### `bump_version.py`
- Member version updates assume that `ortho_config` should bump
  `ortho_config_macros` together, coupling the script to rstest-bdd-specific
  crates.
- Documentation updates only rewrite TOML fences that reference the
  `ortho_config` dependency and only touch `README.md` and
  `docs/users-guide.md`, missing other files in a different workspace layout.
- The script derives the workspace root as two directories above the script,
  preventing reuse when the tools are vendored into another project or invoked
  against a different repository.

## 2. Core Components

### 2.1. The `lading` Command-Line Interface

The primary user interaction point will be the `lading` CLI. It will be implemented using the `cyclopts` library to provide a modern, type-annotated, and environment-aware interface.

The structure will be as follows:

```shell
lading [--workspace-root <path>] <subcommand> [options]
```

- `--workspace-root`: An optional global flag to specify the path to the Rust workspace root. If omitted, it defaults to the current working directory.
- **Subcommands:**

- `bump`: Manages version bumping.
- `publish`: Manages the publication process.

### 2.2. Configuration: `lading.toml`

A `lading.toml` file located at the workspace root will define the tool's behaviour. The design prioritises inference to keep this file as minimal as possible.

**Schema Definition:**

```toml
# lading.toml

# `bump` table: Configuration for the 'bump' command.
[bump]
# A list of glob patterns for documentation files to update with the new version.
# If unset, the tool will not attempt to modify any documentation files.
# Example: doc_files = ["README.md", "docs/**/*.md"]
doc_files = []

# A list of crate names to exclude from the version bump process.
# The tool will infer all publishable crates by default and apply
# version bump to these.
# exclude = []

# `publish` table: Configuration for the 'publish' command.
[publish]
# A list of crate names to exclude from the publishing process.
# Useful for examples, internal tools, or private crates within the workspace.
# The tool will infer all publishable crates by default.
# exclude = []

# Optional explicit ordering for publication. If not specified, the tool
# will determine the order topologically from the dependency graph.
# This should only be used to resolve ambiguity or enforce a specific sequence.
# Crate names listed here must be valid members of the workspace.
# order = ["crate-a", "crate-b"]

# Strategy for stripping [patch.crates-io] directives from Cargo.toml during
# publication. This is often necessary to ensure the registry uses published
# versions of workspace dependencies instead of local path overrides.
#
# Possible values:
# - "all": The entire [patch.crates-io] section is removed from the temporary
#   workspace manifest before any checks are run.
# - "per-crate": Before publishing each crate, its specific entry is removed
#   from the [patch.crates-io] section. This allows subsequent crates in the
#   publish order to still resolve local paths.
# - false: No patches are stripped.
#
# If unset, the tool defaults to "all" for dry runs and "per-crate" for live runs.
strip_patches = "per-crate"

```

### 2.3. Workspace Discovery and Model

The tool's internal representation of the workspace is critical for its operation. This model will be constructed at runtime by executing `cargo metadata --format-version 1` and parsing its JSON output. This approach is superior to manual TOML parsing as it correctly handles path dependencies, build scripts, and complex workspace configurations.

The discovery process will populate an internal data structure representing the workspace graph, containing:

- **Workspace Root:** The absolute path to the workspace directory.
- **Crate List:** A collection of all crates, each containing:

- `name`: The crate name (e.g., `my-crate`).
- `version`: The current version string.
- `path`: The absolute path to the crate's root directory.
- `manifest_path`: The absolute path to the crate's `Cargo.toml`.
- `publish`: A boolean indicating if the crate is intended for publication (derived from `package.publish` in `Cargo.toml`).
- `dependencies`: A list of its dependencies within the workspace.
- `readme_is_workspace`: A boolean flag derived from checking if `package.readme.workspace` is `true`.

This internal graph enables reliable dependency resolution and topological sorting for the `publish` command.

## 3. `bump` Subcommand Design

The `bump` command will synchronise versions across the workspace.

**Command Signature:**

```shell
lading bump <new_version> [--dry-run]
```

- `<new_version>`: The new semantic version string (e.g., `1.2.3`). This is a required argument.
- `--dry-run`: If present, the command will report all changes it would make without writing to any files.

**Execution Flow:**

1. **Discover Workspace:** Build the internal workspace model.
2. **Update Workspace **`Cargo.toml`**:** Set `workspace.package.version` to `<new_version>`.
3. **Update Member Crates:** For each crate in the workspace (not just publishable ones):

- Update `package.version` in its `Cargo.toml`.
- Iterate through its `[dependencies]`, `[dev-dependencies]`, and `[build-dependencies]`. If a dependency is a workspace member, update its version string to match `<new_version>`, preserving any existing version operators (e.g., `^`, `~`). This prevents version drift between internal crates.
4. **Handle Workspace READMEs:** For each crate where `readme_is_workspace` is `true`:

- Copy the `README.md` file from the workspace root to the crate's directory, overwriting any existing file. This action will be performed _before_ any packaging step in the `publish` command but is conceptually part of the versioning workflow. The `bump` command will validate that this is possible.
5. **Update Documentation Files:**

- Read the `bump.doc_files` glob patterns from `lading.toml`.
- For each matching file, scan for TOML code fences (```toml).
- Within each fence, parse the content and update the version of any dependency that is also a workspace member to `<new_version>`. This replaces the previous hardcoded logic.
6. **Report Changes:** Output a summary of all files that were (or would be) modified.

## 4. `publish` Subcommand Design

The `publish` command orchestrates the publication of crates to the designated registry.

**Command Signature:**

```shell
lading publish [--dry-run] [--allow-dirty]
```

- `--live`: By default, the command simulates the entire process, including `cargo package` and `cargo publish --dry-run`, without uploading to the registry. Specifying `--live` takes the process to completion.
- `--allow-dirty`: Allows the command to proceed even if the Git working tree is dirty.

**Execution Flow:**

1. **Discover Workspace:** Build the internal workspace model.
2. **Determine Publishable Crates:**

  - Filter the crate list to include only those where `publish` is not `false`.
  - Remove any crates listed in `publish.exclude` from `lading.toml`.

3. **Determine Publish Order:**

  - If `publish.order` is defined in `lading.toml`, validate that it contains all publishable crates and use this order.
  - If `publish.order` is not defined, perform a topological sort on the dependency graph of publishable crates to generate the correct publication sequence. If the graph contains cycles, the command will abort with an error.

4. **Prepare Workspace Manifest**: Within the temporary clone of the repository, determine the patch stripping strategy based on the publish.strip_patches configuration and the execution mode (--dry-run flag).

  - If strip_patches is "all" (or is unset and this is a dry run), remove the entire [patch.crates-io] section from the Cargo.toml.

5. **Execute Pre-Publish Checks:** Before publishing, run a series of checks in a clean, temporary clone of the repository to ensure integrity:

  - Run `cargo check --all-targets` for the entire workspace.
  - Run `cargo test --all-targets` for the entire workspace.

6. **Iterate and Publish:** For each crate in the determined order:

- **Patch Handling (per-crate)**: If strip_patches is "per-crate" (or is unset and this is a live run), remove the specific patch entry for the current crate from the Cargo.toml in the temporary clone.
- **README Handling:** If the crate has `readme.workspace = true`, copy the workspace `README.md` into the crate's directory within the temporary clone.
- **Package:** Run `cargo package` to create the `.crate` file and verify its contents.
- **Publish:** Run `cargo publish`. If `--dry-run` is active (default behaviour), the `--dry-run` flag will be passed to `cargo publish`. The tool will check the command's output for confirmation. It will also gracefully handle cases where a specific version has already been published, logging a warning and proceeding to the next crate.

## 5. Refactoring and Project Structure

The existing code from `crate_tools` will be refactored into a new Python package structure for `lading`.

**Proposed Directory Structure:**

```plaintext
lading/
├── __init__.py
├── cli.py          # Cyclopts app definition and command wiring
├── commands/
│   ├── __init__.py
│   ├── bump.py     # Logic for the 'bump' subcommand
│   └── publish.py  # Logic for the 'publish' subcommand
├── config.py       # Pydantic models for lading.toml
├── workspace.py    # Workspace discovery and graph model
└── toml_utils.py   # Helpers for manipulating TOML files
tests/
├── conftest.py
├── fixtures/
│   └── simple_workspace/
│       ├── Cargo.toml
│       └── lading.toml
│       └── ...
└── test_*.py
pyproject.toml
```

This structure separates concerns, improves testability, and establishes a clear architecture for future development.

## 6. Testing Strategy

A robust testing strategy is essential for a tool that modifies source files and performs releases.

- **Unit Tests:** Each module (`config.py`, `workspace.py`, `toml_utils.py`) will have comprehensive unit tests. Logic within the `bump` and `publish` commands will be unit-tested with mocked filesystem and subprocess calls.
- **Integration Tests:** The CLI itself (`cli.py`) will be tested using `cyclopts.testing.invoke`. These tests will run against mock workspaces defined in `tests/fixtures/` to verify command-line parsing, configuration loading, and the orchestration of different modules.
- **End-to-End Tests:** A small suite of end-to-end tests will operate on temporary Git repositories. These tests will initialise a Rust workspace, commit a `lading.toml`, and then execute `lading bump` and `lading publish --dry-run`, asserting that the files are correctly modified and the `cargo` commands are executed in the right sequence.

This multi-layered approach will ensure correctness from the lowest-level utilities to the highest-level user-facing commands.

