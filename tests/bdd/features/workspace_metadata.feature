Feature: Cargo metadata discovery
    Background:
        Given a workspace directory

    Scenario: Inspecting cargo metadata succeeds
        Given cargo metadata returns workspace information
        When I inspect the workspace metadata
        Then the metadata payload contains the workspace root
