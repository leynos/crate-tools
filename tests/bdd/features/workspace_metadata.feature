Feature: Cargo metadata discovery
    Background:
        Given a workspace directory

    Scenario: Inspecting cargo metadata succeeds
        Given cargo metadata returns workspace information
        When I inspect the workspace metadata
        Then the metadata payload contains the workspace root

    Scenario: Building a workspace model from metadata
        Given a workspace crate manifest with a workspace readme
        And cargo metadata returns that workspace crate
        When I build the workspace model
        Then the workspace model reflects the crate metadata
