Feature: Lading CLI scaffolding
  Scenario: Bumping workspace versions updates Cargo manifests
    Given a workspace directory with configuration
    And cargo metadata describes a sample workspace
    When I invoke lading bump 1.2.3 with that workspace
    Then the bump command reports manifest updates for "1.2.3"
    And the workspace manifest version is "1.2.3"
    And the crate "alpha" manifest version is "1.2.3"

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
