Feature: Lading CLI scaffolding
  Scenario: Bumping workspace versions updates Cargo manifests
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    When I invoke lading bump 1.2.3 with that workspace
    Then the bump command reports manifest updates for "1.2.3"
    And the CLI output lists manifest paths "- Cargo.toml" and "- crates/alpha/Cargo.toml"
    And the workspace manifest version is "1.2.3"
    And the crate "alpha" manifest version is "1.2.3"

  Scenario: Dry running the bump command previews manifest updates
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    When I invoke lading bump 1.2.3 with that workspace using --dry-run
    Then the bump command reports a dry-run plan for "1.2.3"
    And the CLI output lists manifest paths "- Cargo.toml" and "- crates/alpha/Cargo.toml"
    And the workspace manifest version is "0.1.0"
    And the crate "alpha" manifest version is "0.1.0"

  Scenario: Bumping with an invalid version fails fast
    Given a workspace directory with configuration
    When I invoke lading bump 1.2 with that workspace
    Then the bump command reports an invalid version error for "1.2"

  Scenario: Bumping workspace versions skips excluded crates
    Given a workspace directory with configuration
    And cargo metadata describes a workspace with crates alpha and beta
    And bump.exclude contains "alpha"
    When I invoke lading bump 1.2.3 with that workspace
    Then the crate "alpha" manifest version is "0.1.0"
    And the crate "beta" manifest version is "1.2.3"

  Scenario: Bumping updates internal dependency requirements
    Given a workspace directory with configuration
    And cargo metadata describes a workspace with internal dependency requirements
    When I invoke lading bump 1.2.3 with that workspace
    Then the dependency "beta:alpha@dependencies" has requirement "^1.2.3"
    And the dependency "beta:alpha@dev-dependencies" has requirement "~1.2.3"
    And the dependency "beta:alpha@build-dependencies" has requirement "1.2.3"

  Scenario: Bumping updates documentation TOML fences
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    And the workspace README contains a TOML dependency snippet for "alpha"
    And bump.documentation.globs contains "README.md"
    When I invoke lading bump 1.2.3 with that workspace
    Then the documentation file "README.md" contains "alpha = \"1.2.3\""
    And the CLI output lists documentation path "- README.md (documentation)"

  Scenario: Bumping workspace versions when already up to date
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    And the workspace manifests record version "1.2.3"
    When I invoke lading bump 1.2.3 with that workspace
    Then the bump command reports no manifest changes for "1.2.3"

  Scenario: Running the publish command with a workspace root
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    When I invoke lading publish with that workspace
    Then the publish command prints the publish plan for "alpha"

  Scenario: Publish command reports skipped crates and missing exclusions
    Given a workspace directory with configuration
    And cargo metadata describes a workspace with publish filtering cases
    And publish.exclude contains "gamma"
    And publish.exclude contains "missing-delta"
    When I invoke lading publish with that workspace
    Then the publish command prints the publish plan for "alpha"
    And the publish command reports manifest-skipped crate "beta"
    And the publish command reports configuration-skipped crate "gamma"
    And the publish command reports missing exclusion "missing-delta"

  Scenario: Publish command lists multiple configuration skipped crates
    Given a workspace directory with configuration
    And cargo metadata describes a workspace with publish filtering cases
    And publish.exclude contains "gamma"
    And publish.exclude contains "delta"
    When I invoke lading publish with that workspace
    Then the publish command prints the publish plan for "alpha"
    And the publish command reports configuration-skipped crates "gamma, delta"

  Scenario: Publish command reports no publishable crates
    Given a workspace directory with configuration
    And cargo metadata describes a workspace with no publishable crates
    When I invoke lading publish with that workspace
    Then the publish command reports that no crates are publishable
    And the publish command reports manifest-skipped crate "alpha"
    And the publish command reports manifest-skipped crate "beta"

  Scenario: Running the bump command without configuration
    Given a workspace directory without configuration
    When I invoke lading bump 1.2.3 with that workspace
    Then the CLI reports a missing configuration error
