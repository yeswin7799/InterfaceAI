"""
The "act" step of the discovery agent's observe -> decide -> act loop.

Takes a decision dict from agent.decide.decide_next_action() and executes it
against a live Playwright page. This is deliberately a thin, literal
translation: {"tool": "fill_field", "input": {"role": "textbox", "name": "Member ID:", "text": "10001"}}
becomes page.get_by_role("textbox", name="Member ID:").fill("10001").

Using get_by_role(role, name=...) here is the payoff of our perception/tools
design: the exact (role, name) pair the model reasoned about is the exact
locator Playwright uses to find the element for real. No re-interpretation
step in between.

goal_complete and stuck don't touch the browser at all -- they're terminal
signals the loop (built next) will handle.
"""

from playwright.sync_api import Page


class ActionResult:
    """Simple result wrapper so the loop can tell what happened without
    inspecting exception types directly."""

    def __init__(self, status: str, detail: str = ""):
        self.status = status  # "ok" | "error" | "goal_complete" | "stuck"
        self.detail = detail

    def __repr__(self):
        return f"ActionResult(status={self.status!r}, detail={self.detail!r})"


def execute_action(page: Page, decision: dict) -> ActionResult:
    """
    Execute one decided action against the page.

    decision is {"tool": <name>, "input": <dict>}, matching what
    agent.decide.decide_next_action() returns.
    """
    tool = decision["tool"]
    args = decision["input"]

    try:
        if tool == "fill_field":
            page.get_by_role(args["role"], name=args["name"]).fill(args["text"])
            return ActionResult("ok", f"Filled {args['role']} '{args['name']}' with '{args['text']}'")

        elif tool == "click_element":
            page.get_by_role(args["role"], name=args["name"]).click()
            return ActionResult("ok", f"Clicked {args['role']} '{args['name']}'")

        elif tool == "select_option":
            page.get_by_role(args["role"], name=args["name"]).select_option(label=args["option"])
            return ActionResult("ok", f"Selected '{args['option']}' in {args['role']} '{args['name']}'")

        elif tool == "goal_complete":
            return ActionResult("goal_complete", args.get("reasoning", ""))

        elif tool == "stuck":
            return ActionResult("stuck", args.get("reason", ""))

        else:
            return ActionResult("error", f"Unknown tool: {tool}")

    except Exception as e:
        # Any Playwright failure (element not found, not visible, timeout, ...)
        # becomes a structured error rather than an uncaught crash -- the
        # loop needs to be able to react to this (e.g. tell the model what
        # went wrong, or eventually escalate) rather than the whole process dying.
        return ActionResult("error", f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    # Quick manual check: fill the search box for real and confirm it landed.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("http://127.0.0.1:5000/search")

        result = execute_action(
            page,
            {"tool": "fill_field", "input": {"role": "textbox", "name": "Member ID:", "text": "10001"}},
        )
        print("Result:", result)

        input("Check the browser -- is '10001' in the field? Press Enter to close...")
        browser.close()