"""
Manual sanity check: hand-build a Capability matching the real discovery run
we already did (open a checking sub-account for member 10001, $150 deposit),
but parameterized so it could run for *any* member/account type/deposit.

This isn't the automated recorder yet -- that's next. This is just to prove
the schema can actually represent our real flow before we automate producing
it.
"""

from artifacts.schema import (
    ArtifactOutput,
    ArtifactParameter,
    ArtifactStep,
    Capability,
    Checkpoint,
    ElementLocator,
)

open_sub_account_capability = Capability(
    name="open_sub_account",
    version="1.0.0",
    description="Search for a member by ID, then open a new sub-account for them and reach the confirmation screen.",
    start_url="http://127.0.0.1:5000/search",
    parameters=[
        ArtifactParameter(name="member_id", type="string", description="The member ID to search for.", required=True),
        ArtifactParameter(
            name="account_type",
            type="string",
            description="Type of sub-account to open: 'Savings', 'Checking', or 'Certificate'.",
            required=True,
        ),
        ArtifactParameter(
            name="initial_deposit", type="number", description="Initial deposit amount in dollars.", required=True
        ),
    ],
    steps=[
        ArtifactStep(
            step_number=1,
            action="fill_field",
            target=ElementLocator(role="textbox", name="Member ID:"),
            value_param="member_id",
        ),
        ArtifactStep(
            step_number=2,
            action="click_element",
            target=ElementLocator(role="button", name="Search"),
        ),
        ArtifactStep(
            step_number=3,
            action="click_element",
            target=ElementLocator(role="link", name="Open Sub-Account for this Member"),
        ),
        ArtifactStep(
            step_number=4,
            action="select_option",
            target=ElementLocator(role="combobox", name="Account Type:"),
            value_param="account_type",
        ),
        ArtifactStep(
            step_number=5,
            action="fill_field",
            target=ElementLocator(role="textbox", name="Initial Deposit ($):"),
            value_param="initial_deposit",
        ),
        ArtifactStep(
            step_number=6,
            action="click_element",
            target=ElementLocator(role="button", name="Open Sub-Account"),
        ),
    ],
    outputs=[
        ArtifactOutput(
            name="sub_account_id",
            type="string",
            description="The newly created sub-account's ID.",
            extract_after_label="Sub-Account ID:",
        ),
    ],
    checkpoint=Checkpoint(
        description="The confirmation page is shown, containing the success banner text.",
        expected_text_contains="Sub-Account Opened Successfully",
    ),
    locator_strategy_notes=(
        "All targets use accessibility role + accessible name, sourced from the page's ARIA tree. "
        "The target app has no ids/classes/test-ids (legacy-style markup), so role+name is the only "
        "stable option; form fields were explicitly labeled during target-app development to ensure "
        "each has a real accessible name rather than relying on adjacent, unassociated text."
    ),
)


if __name__ == "__main__":
    # Prove it validates and round-trips through JSON cleanly.
    json_str = open_sub_account_capability.model_dump_json(indent=2)
    print(json_str)

    # Round-trip check.
    reloaded = Capability.model_validate_json(json_str)
    assert reloaded == open_sub_account_capability
    print("\nRound-trip validation OK.")