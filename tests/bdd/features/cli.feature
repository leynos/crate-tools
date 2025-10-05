Feature: Lading CLI scaffolding
  Scenario: Running the bump command with a workspace root
    Given a workspace directory
    When I invoke lading bump with that workspace
    Then the command reports the workspace path
