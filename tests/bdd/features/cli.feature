Feature: Lading CLI scaffolding
  Scenario: Bumping workspace versions updates Cargo manifests
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    When I invoke lading bump 1.2.3 with that workspace
    Then the bump command reports manifest updates for "1.2.3"
    And the workspace manifest version is "1.2.3"
    And the crate "alpha" manifest version is "1.2.3"

  Scenario: Bumping with an invalid version fails fast
    Given a workspace directory with configuration
    When I invoke lading bump 1.2 with that workspace
    Then the CLI exits with code 1
    And the stderr contains "Invalid version argument '1.2'"

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
    Then the crate "beta" dependency "alpha" in "dependencies" has requirement "^1.2.3"
    And the crate "beta" dependency "alpha" in "dev-dependencies" has requirement "~1.2.3"
    And the crate "beta" dependency "alpha" in "build-dependencies" has requirement "1.2.3"

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
    Then the publish command reports the workspace path, crate count, and strip patches

  Scenario: Running the bump command without configuration
    Given a workspace directory without configuration
    When I invoke lading bump 1.2.3 with that workspace
    Then the CLI reports a missing configuration error
