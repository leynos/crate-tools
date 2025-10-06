Feature: Lading CLI scaffolding
  Scenario: Running the bump command with a workspace root
    Given a workspace directory with configuration
    When I invoke lading bump with that workspace
    Then the command reports the workspace path and doc files

  Scenario: Running the publish command with a workspace root
    Given a workspace directory with configuration
    When I invoke lading publish with that workspace
    Then the publish command reports the workspace path and strip patches
