# Roadmap: Generalising publish tooling

This document outlines the work required to adapt `run_publish_check.py` and
`bump_version.py` so they can operate on arbitrary Rust workspaces rather than
the current rstest-bdd specific layout.

## Current coupling

### `run_publish_check.py`
- The workflow is driven by the statically defined
  `PUBLISHABLE_CRATES` tuple imported from `publish_workspace_members`, which
  hard-codes the crate list and release ordering for this repository.【F:crate_tools/run_publish_check.py†L49-L97】
- Crate directories are resolved under `<workspace>/crates/<name>`, which only
  matches the current workspace layout and fails for workspaces that colocate
  crates elsewhere.【F:crate_tools/run_publish_check.py†L160-L187】
- Live publish commands and the locked publish variant are keyed off concrete
  crate names, making the publish pipeline unusable when the workspace contains
  a different set of packages.【F:crate_tools/run_publish_check.py†L74-L97】
- The dry-run mode packages one crate and checks others based on crate names,
  which will not hold in a generic workspace.【F:crate_tools/run_publish_check.py†L626-L637】

### `bump_version.py`
- Member version updates assume that `ortho_config` should bump
  `ortho_config_macros` together, coupling the script to rstest-bdd-specific
  crates.【F:crate_tools/bump_version.py†L422-L440】
- Documentation updates only rewrite TOML fences that reference the
  `ortho_config` dependency and only touch `README.md` and
  `docs/users-guide.md`, missing other files in a different workspace layout.【F:crate_tools/bump_version.py†L504-L614】
- The script derives the workspace root as two directories above the script,
  preventing reuse when the tools are vendored into another project or invoked
  against a different repository.【F:crate_tools/bump_version.py†L340-L360】

## Roadmap

### 1. Introduce workspace metadata discovery
1. Parse the workspace manifest (or invoke `cargo metadata`) to build the crate
   list, release order, and per-crate paths at runtime, replacing the
   `PUBLISHABLE_CRATES` constant and hard-coded `crates/<name>` resolution in the
   publish workflow.【F:crate_tools/run_publish_check.py†L72-L187】
2. Extend `publish_workspace_members` (or an adjacent helper) to expose the
   discovered data so both scripts can consume a shared representation.
3. Provide a compatibility shim that honours an explicit crate ordering when a
   workspace supplies one (for example via a config file) so existing release
   sequences remain controllable.

### 2. Make crate-specific behaviour configurable
1. Replace the static live publish command map with configuration derived from
   metadata or an external config file (YAML/TOML), allowing workspaces to mark
   crates that require locked publishes or custom command sequences.【F:crate_tools/run_publish_check.py†L74-L485】
2. Generalise the dry-run action selection so that each crate declares whether
   it should run `cargo check`, `cargo test`, or `cargo package`, instead of the
   current name-based branching.【F:crate_tools/run_publish_check.py†L626-L637】
3. Document and implement CLI flags (or config schema) for optional behaviours
   such as stripping `[patch]` sections, applying per-crate replacements, and
   keeping the temporary workspace, so other projects can opt in without code
   changes.【F:crate_tools/run_publish_check.py†L511-L667】

### 3. Support flexible workspace layouts
1. Let callers pass the workspace root explicitly (CLI option or environment
   variable) and resolve crate locations via metadata, enabling vendored use of
   the scripts.【F:crate_tools/bump_version.py†L340-L360】【F:crate_tools/run_publish_check.py†L160-L187】
2. Ensure member discovery handles path, glob, and package rename cases from the
   manifest rather than assuming directory names match package names.
3. Update temporary export and pruning helpers to operate on the discovered set
   of members so they no longer depend on rstest-bdd specific helper modules.

### 4. Generalise version propagation
1. Allow configuring which workspace crates should share the workspace version
   (for example via manifest metadata or an external map) instead of the
   `ortho_config` special-case in `_update_member_version`.【F:crate_tools/bump_version.py†L422-L440】
2. Replace the `replace_version_in_toml`/`_update_markdown_versions` coupling to
   `ortho_config` with a rule-based system (e.g. scan for dependencies whose
   names match the workspace crates) and support an extensible list of
   documentation paths supplied on the command line or via config.【F:crate_tools/bump_version.py†L504-L614】
3. Add unit tests that cover multiple workspace layouts and documentation file
   selections to guarantee the new configuration behaves as expected.

### 5. Validation and ergonomics
1. Update the CLI help text to describe the new configuration options and
   document the expected metadata/configuration schema in `docs/`.
2. Provide example config files and usage snippets for adopting the scripts in a
   new workspace, ensuring the roadmap deliverables translate into actionable
   migration steps.
3. Wire the repository Makefile (or equivalent) to run integration tests across
   representative workspaces to prevent regressions once the scripts become
   generic.
