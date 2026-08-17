"""
Human-in-the-loop escalation & handoff (Section 3.6).

When the discovery agent calls the `stuck` tool, this module takes over:
it captures context (goal, step, reason, current page state), saves an
intervention-request record to evidence, then genuinely pauses -- the
Playwright browser window stays open and interactive, so a human operator
can act directly in the *same live session* the agent was using, not a
fresh one. When the human signals they're done (pressing Enter at the
terminal, our deliberately bare/mock operator surface per the assignment's
scope note), we capture the resulting page state and hand control back to
the agent, which resumes the loop from wherever the page now is.

Honest limitation, documented rather than hidden: because the human acts
directly in the browser window (not through our tool vocabulary), we don't
get a structured, action-by-action log of exactly what they clicked/typed --
only a before/after snapshot of the page. A production operator console
(explicitly out of scope per the brief) would capture this at the action
level; here, the before/after page state is the record of what the
intervention accomplished.
"""

import json
import os
import time

from playwright.sync_api import Page

from agent.perception import snapshot_page
from safety.redaction import redact_value


def request_intervention(
    page: Page,
    goal: str,
    step_number: int,
    reason: str,
    evidence_dir: str | None = None,
) -> dict:
    """
    Pause discovery, hand the live session to a human, and wait for them to
    signal completion. Returns a record of the escalation (context, before/
    after state, evidence paths) for the caller to log and feed back into
    the agent's history.
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    record = {
        "goal": goal,
        "step_number": step_number,
        "reason": reason,
        "snapshot_before": snapshot_page(page),
        "screenshot_before": None,
        "snapshot_after": None,
        "screenshot_after": None,
    }

    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        record["screenshot_before"] = os.path.join(evidence_dir, f"escalation-before-{timestamp}.png")
        page.screenshot(path=record["screenshot_before"])

    print("\n" + "=" * 70)
    print("HUMAN INTERVENTION REQUESTED")
    print(f"Goal:        {goal}")
    print(f"Stuck at:    step {step_number}")
    print(f"Reason:      {reason}")
    print("-" * 70)
    print("The browser window is still open -- you may interact with it directly.")
    print("When you're done (or want the agent to just retry as-is), press Enter here.")
    print("=" * 70)
    input(">>> ")

    record["snapshot_after"] = snapshot_page(page)
    if evidence_dir:
        record["screenshot_after"] = os.path.join(evidence_dir, f"escalation-after-{timestamp}.png")
        page.screenshot(path=record["screenshot_after"])

        log_path = os.path.join(evidence_dir, f"escalation-{timestamp}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(redact_value(record), f, indent=2)
        record["evidence_path"] = log_path

    print("Control returned to the agent. Resuming from the current page state.\n")
    return record