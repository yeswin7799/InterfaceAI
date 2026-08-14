"""
Converts a saved discovery evidence log (agent.evidence.save_discovery_log
output) into a validated Capability artifact.

Deliberately works from the *saved* evidence JSON rather than requiring the
live DiscoveryResult object in memory. This matters for the "decoupled from
the raw model transcript" requirement (Section 3.2) -- recording an artifact
is a separate, later step from running discovery, potentially done by a
different process, a human reviewer, or a while after the run happened. The
evidence log is the durable interface between them.

Parameterization is explicit, not inferred: the caller supplies
value_to_param, a mapping from the concrete literal values seen during this
particular discovery run (e.g. "10001") to the named parameter they should
become in the reusable capability (e.g. "member_id"). See artifacts/schema.py
for the reasoning behind this being a deliberate choice rather than a cut.
"""

import glob
import json
import os

from artifacts.schema import (
    ArtifactOutput,
    ArtifactParameter,
    ArtifactStep,
    Capability,
    Checkpoint,
    ElementLocator,
)


def load_discovery_log(path: str) -> dict:
    """Load a saved evidence JSON file (see agent/evidence.py) as a plain dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def latest_discovery_log(evidence_dir: str = "evidence") -> str:
    """Convenience: find the most recently saved discovery-log-*.json in evidence_dir."""
    candidates = sorted(glob.glob(os.path.join(evidence_dir, "discovery-log-*.json")))
    if not candidates:
        raise FileNotFoundError(f"No discovery-log-*.json files found in {evidence_dir}/")
    return candidates[-1]


def record_capability(
    log: dict,
    name: str,
    version: str,
    description: str,
    parameters: list[ArtifactParameter],
    value_to_param: dict[str, str],
    outputs: list[ArtifactOutput],
    checkpoint: Checkpoint,
    locator_strategy_notes: str,
) -> Capability:
    """
    Build a Capability from a loaded discovery log dict.

    Only successful ("ok") fill_field/click_element/select_option steps are
    included -- goal_complete/stuck are terminal signals, not replayable
    actions, and any step that errored during discovery didn't actually
    contribute to reaching the goal (the model recovered and did something
    else instead), so replaying it would be wrong.
    """
    if log["status"] != "goal_complete":
        raise ValueError(
            f"Refusing to record an artifact from a discovery run that didn't complete "
            f"the goal (status was '{log['status']}'). Only successful runs become capabilities."
        )

    steps: list[ArtifactStep] = []
    step_number = 1

    for raw_step in log["steps"]:
        decision = raw_step["decision"]
        tool = decision["tool"]
        args = decision["input"]

        if tool not in ("fill_field", "click_element", "select_option"):
            continue
        if raw_step["result_status"] != "ok":
            continue

        target = ElementLocator(role=args["role"], name=args["name"])

        if tool == "fill_field":
            value = args["text"]
        elif tool == "select_option":
            value = args["option"]
        else:
            value = None

        if value is not None and value in value_to_param:
            step = ArtifactStep(
                step_number=step_number, action=tool, target=target, value_param=value_to_param[value]
            )
        elif value is not None:
            step = ArtifactStep(step_number=step_number, action=tool, target=target, value_literal=value)
        else:
            step = ArtifactStep(step_number=step_number, action=tool, target=target)

        steps.append(step)
        step_number += 1

    return Capability(
        name=name,
        version=version,
        description=description,
        start_url=log["start_url"],
        parameters=parameters,
        steps=steps,
        outputs=outputs,
        checkpoint=checkpoint,
        locator_strategy_notes=locator_strategy_notes,
    )


def save_capability(capability: Capability, output_dir: str = "artifacts") -> str:
    """Save a Capability as versioned JSON: artifacts/<name>.v<version>.json"""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{capability.name}.v{capability.version}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(capability.model_dump_json(indent=2))
    return path


if __name__ == "__main__":
    log_path = latest_discovery_log()
    print(f"Loading discovery log: {log_path}")
    log = load_discovery_log(log_path)

    capability = record_capability(
        log=log,
        name="open_sub_account",
        version="1.0.0",
        description="Search for a member by ID, then open a new sub-account for them and reach the confirmation screen.",
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
        # Maps the concrete literal values THIS discovery run happened to use
        # to the named parameters they represent.
        value_to_param={
            "10001": "member_id",
            "Checking": "account_type",
            "150": "initial_deposit",
        },
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

    print(f"\nRecorded capability with {len(capability.steps)} steps.")

    path = save_capability(capability)
    print(f"Saved to: {path}")