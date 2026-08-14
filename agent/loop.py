"""
The discovery agent's full observe -> decide -> act loop.

This is the "goal + target -> LLM-driven run against a live surface" piece
required by Section 3.1 of the brief. It repeatedly:
  1. observes the current page (agent.perception.snapshot_page)
  2. decides the next action (agent.decide.decide_next_action)
  3. acts on it (agent.act.execute_action)
until the model calls goal_complete, calls stuck, or we hit a max-step
safety limit (our third stopping condition alongside those two).

We keep a full structured trace of every step -- this is both what lets us
give the model a running history each turn, and, unmodified, becomes the
evidence log required by Section 3.5. It's also the raw material the
artifact-recording step (built next, after this) will condense into a
reusable capability.
"""

from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright

from agent.perception import snapshot_page
from agent.decide import decide_next_action
from agent.act import execute_action


@dataclass
class Step:
    step_number: int
    snapshot: str
    decision: dict
    result_status: str
    result_detail: str


@dataclass
class DiscoveryResult:
    status: str  # "goal_complete" | "stuck" | "max_steps_exceeded"
    steps: list = field(default_factory=list)
    outputs: dict = field(default_factory=dict)
    reasoning: str = ""
    screenshot_path: str = ""


def run_discovery(
    goal: str,
    start_url: str,
    max_steps: int = 15,
    headless: bool = True,
    evidence_dir: str | None = None,
) -> DiscoveryResult:
    """
    Run the full discovery loop against a live browser, starting at start_url,
    trying to accomplish goal within max_steps turns.

    If evidence_dir is given, a screenshot of the final page state is saved
    there when the loop reaches a terminal condition (goal_complete, stuck,
    or max_steps_exceeded) -- this is the "richer signal" evidence required
    alongside the structured step log (Section 3.5).
    """
    import os
    import time

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(start_url)

        history: list[str] = []
        steps: list[Step] = []

        def save_screenshot(status: str) -> str:
            if not evidence_dir:
                return ""
            os.makedirs(evidence_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = os.path.join(evidence_dir, f"discovery-{status}-{timestamp}.png")
            page.screenshot(path=path)
            return path

        for step_number in range(1, max_steps + 1):
            snapshot = snapshot_page(page)
            decision = decide_next_action(goal, snapshot, history)
            result = execute_action(page, decision)

            steps.append(Step(step_number, snapshot, decision, result.status, result.detail))

            if result.status == "goal_complete":
                screenshot_path = save_screenshot("success")
                browser.close()
                return DiscoveryResult(
                    status="goal_complete",
                    steps=steps,
                    outputs=decision["input"].get("outputs", {}),
                    reasoning=decision["input"].get("reasoning", ""),
                    screenshot_path=screenshot_path,
                )

            if result.status == "stuck":
                screenshot_path = save_screenshot("stuck")
                browser.close()
                return DiscoveryResult(
                    status="stuck", steps=steps, reasoning=result.detail, screenshot_path=screenshot_path
                )

            # "ok" or "error" -- either way, record what happened and let the
            # model see it next turn. A tool error is not a crash: we feed it
            # back as history so the model can course-correct (e.g. retry
            # with a different name it now sees in the refreshed snapshot).
            action_desc = f"{decision['tool']}({decision['input']})"
            history.append(f"Step {step_number}: {action_desc} -> {result.status}: {result.detail}")

        screenshot_path = save_screenshot("max-steps-exceeded")
        browser.close()
        return DiscoveryResult(
            status="max_steps_exceeded",
            steps=steps,
            reasoning=f"Exceeded {max_steps} steps without reaching goal_complete or stuck.",
            screenshot_path=screenshot_path,
        )

if __name__ == "__main__":
    # Harder test: the real multi-step flow with a form and a confirmation
    # checkpoint -- this is the goal we intend to turn into a saved artifact.
    from agent.evidence import save_discovery_log

    goal = (
        "Open a new checking sub-account for member 10001 with an "
        "initial deposit of $150, and reach the confirmation screen."
    )
    start_url = "http://127.0.0.1:5000/search"

    result = run_discovery(
        goal=goal,
        start_url=start_url,
        max_steps=10,
        headless=False,
        evidence_dir="evidence",
    )

    print(f"\n=== Discovery finished: {result.status} ===")
    print(f"Outputs: {result.outputs}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Screenshot: {result.screenshot_path}")
    print(f"\nSteps taken ({len(result.steps)}):")
    for s in result.steps:
        print(f"  {s.step_number}. {s.decision['tool']}({s.decision['input']}) -> {s.result_status}: {s.result_detail}")

    log_path = save_discovery_log(result, goal, start_url, "evidence")
    print(f"\nEvidence log saved to: {log_path}")