# Lading Tool Development Roadmap

## Phase 1: Foundation and Core Abstraction

**Objective:** Establish the foundational structure of the `lading` tool,
including the CLI, configuration management, and workspace discovery. This
phase decouples the logic from the old repository-specific scripts and creates
a solid base for the new, generalised functionality.

______________________________________________________________________

### **Step 1.1: Project Scaffolding and CLI Structure**

**Description:** Create the new Python project structure for `lading` and
implement the basic command-line interface using `cyclopts`.

**Tasks:**

- [x] **Initialise New Project:**

  - **Outcome:** A new Python package named `lading` is created with a
    `pyproject.toml` file.
  - **Completion Criteria:** The project is configured with `uv`, `ruff`, and
    `pytest`. The directory structure matches the one outlined in the design
    document.

- [x] **Implement `lading` CLI Shell:**

  - **Outcome:** A `cyclopts`-based CLI application is implemented with `bump`
    and `publish` subcommands.
  - **Completion Criteria:** The CLI runs and correctly dispatches to
    placeholder functions for each subcommand. It accepts the global
    `--workspace-root` option.

- [x] **Configuration Loading:**

  - **Outcome:** The tool can locate and parse a `lading.toml` file from the
    workspace root.
  - **Completion Criteria:** A Pydantic or dataclass model for `lading.toml` is
    defined. The CLI successfully loads and validates the configuration file,
    making its values accessible to the application.

______________________________________________________________________

### **Step 1.2: Workspace Discovery and Modelling**

**Description:** Implement the core logic for inspecting a Rust workspace using
`cargo metadata`.

**Tasks:**

- [x] **Implement `cargo metadata` Wrapper:**

  - **Outcome:** A Python function exists that executes
    `cargo metadata --format-version 1` as a subprocess and captures its JSON
    output.
  - **Completion Criteria:** The function correctly handles command execution
    errors and returns the parsed JSON data. It is covered by unit tests using
    a mocked subprocess.

- [x] **Develop Workspace Data Model:**

  - **Outcome:** A set of `msgspec.Struct` models represents the workspace
    graph, including crates, dependencies, and manifest paths.
  - **Completion Criteria:** The models can be successfully instantiated from
    the JSON output of `cargo metadata` for a representative test workspace.

- [x] **Integrate Discovery into CLI:**

  - **Outcome:** The `lading` CLI builds the workspace model upon invocation.
  - **Completion Criteria:** Both `bump` and `publish` commands have access to
    the complete, populated workspace model.

## Phase 2: `lading bump` Subcommand Implementation

**Objective:** Deliver a fully functional, configuration-driven `bump` command
that correctly propagates version changes across all relevant files in a
generic Rust workspace.

______________________________________________________________________

### **Step 2.1: Version Propagation in `Cargo.toml`**

**Description:** Implement the core logic for updating version numbers in the
workspace and member crate manifests.

**Tasks:**

- [x] **Update Workspace and Member Versions:**

  - **Outcome:** The `bump` command can modify the `version` field in the main
    `Cargo.toml` and all member `Cargo.toml` files.
  - **Completion Criteria:** An integration test confirms that running
    `lading bump 1.2.3` on a fixture workspace results in all `package.version`
    fields being updated to `1.2.3`.

- [x] **Update Internal Dependency Versions:**

  - **Outcome:** The command updates the version specifiers for all
    dependencies that are internal to the workspace.
  - **Completion Criteria:** An integration test verifies that
    `[dependencies]`, `[dev-dependencies]`, and `[build-dependencies]` sections
    are correctly updated to point to the new workspace version, preserving
    operators like `^` or `~`.

- [x] **Implement `--dry-run` Mode for Bumping:**

  - **Outcome:** The `--dry-run` flag prevents any file modifications and
    instead prints a summary of intended changes.
  - **Completion Criteria:** Running `lading bump 1.2.3 --dry-run` produces a
    report of all files that would be changed, and a subsequent check confirms
    no files were actually modified.

______________________________________________________________________

### **Step 2.2: Documentation and README Synchronisation**

**Description:** Implement the logic for updating documentation files and
handling workspace READMEs.

**Tasks:**

- [x] **Implement Configurable Documentation Updates:**

  - **Outcome:** The `bump` command updates version numbers within TOML code
    fences in documentation files, using new configuration introduced alongside
    this feature.
  - **Completion Criteria:** A test case with a fixture workspace containing a
    `README.md` with a TOML snippet confirms the version inside the snippet is
    correctly updated.

- [ ] **Implement Workspace README Handling:**

  - **Outcome:** The `publish` command's preparation step correctly copies the
    workspace `README.md` to member crates that have
    `package.readme.workspace = true` set.
  - **Completion Criteria:** An end-to-end dry-run test of the `publish`
    command verifies that the README file is correctly staged for a designated
    crate in the temporary build directory.

## Phase 3: `lading publish` Subcommand Implementation

**Objective:** Deliver a robust `publish` command that safely and correctly
publishes workspace crates in the right order, with comprehensive pre-flight
checks.

______________________________________________________________________

### **Step 3.1: Publication Planning and Pre-flight Checks**

**Description:** Implement the logic to determine which crates to publish, in
what order, and to validate the workspace state before any publication actions
occur.

**Tasks:**

- [ ] **Determine Publishable Crates:**

  - **Outcome:** The `publish` command can identify all publishable crates from
    the workspace model.
  - **Completion Criteria:** The logic correctly filters out crates with
    `publish = false` and those listed in the `publish.exclude` configuration.

- [ ] **Implement Topological Sort for Publish Order:**

  - **Outcome:** The command can generate a valid publication order based on
    the workspace dependency graph.
  - **Completion Criteria:** The implementation correctly sorts a test case
    with a multi-level dependency chain and correctly reports an error for a
    workspace with a dependency cycle. The explicit `publish.order`
    configuration is also honoured when present.

- [ ] **Implement Pre-Publish Checks:**

  - **Outcome:** The command executes `cargo check` and `cargo test` in a
    clean, temporary clone of the workspace before proceeding.
  - **Completion Criteria:** A test confirms that the publish command fails if
    either of the pre-flight checks fails. The `--allow-dirty` flag is
    correctly handled.

______________________________________________________________________

### **Step 3.2: Crate Packaging and Publication**

**Description:** Implement the final steps of packaging each crate and
interacting with the `cargo publish` command.

**Tasks:**

- [ ] **Implement Configurable Patch Stripping:**

  - **Outcome:** The command correctly modifies the workspace `Cargo.toml` in
    the temporary clone according to the `publish.strip_patches` strategy
    (`all`, `per-crate`, or `false`).
  - **Completion Criteria:** Unit tests verify that the manifest is correctly
    manipulated for each of the three strategies.

- [ ] **Implement Crate Packaging Loop:**

  - **Outcome:** The command iterates through the publish list, executing
    `cargo package` for each crate.
  - **Completion Criteria:** A dry-run test confirms that `cargo package` is
    called for each publishable crate in the correct order.

- [ ] **Implement `cargo publish` Execution:**

  - **Outcome:** The command executes `cargo publish` for each crate,
    supporting both dry-run and live modes.
  - **Completion Criteria:** A dry-run test verifies that
    `cargo publish --dry-run` is called correctly. The logic gracefully handles
    and logs when a crate version is already published, then continues to the
    next crate.

## Phase 4: Stabilisation and Documentation

**Objective:** Ensure the `lading` tool is robust, well-tested, and has clear
documentation for end-users.

______________________________________________________________________

### **Step 4.1: Testing and Quality Assurance**

**Description:** Finalise the test suite, focusing on edge cases and end-to-end
behaviours.

**Tasks:**

- [ ] **Achieve High Test Coverage:**

  - **Outcome:** The entire `lading` codebase has a high level of unit and
    integration test coverage.
  - **Completion Criteria:** Code coverage reports show over 90% line coverage
    for all new modules.

- [ ] **Create End-to-End Test Suite:**

  - **Outcome:** A suite of tests exists that covers the full user workflow in
    a temporary Git repository.
  - **Completion Criteria:** At least one end-to-end test exists for `bump` and
    one for `publish --dry-run` that validates the full sequence of operations
    on a non-trivial fixture workspace.

______________________________________________________________________

### **Step 4.2: User Documentation and Release**

**Description:** Prepare user-facing documentation and package the tool for
distribution.

**Tasks:**

- [ ] **Write User Guide:**

  - **Outcome:** A comprehensive `README.md` or set of documentation files
    exists for the `lading` project.
  - **Completion Criteria:** The documentation includes an installation guide,
    a tutorial, and a complete reference for the `lading.toml` configuration
    file.

- [ ] **Package for PyPI:**

  - **Outcome:** The `lading` tool is packaged as a standard Python wheel.
  - **Completion Criteria:** The `pyproject.toml` is fully configured for
    building a distributable package, and a successful build can be triggered.
