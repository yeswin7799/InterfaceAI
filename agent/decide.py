"""
The "decide" step of the discovery agent's observe -> decide -> act loop.

Given a goal, the current page's accessibility snapshot, and a short history
of what's happened so far, ask Claude to pick exactly one next action from
the tool vocabulary defined in agent/tools.py.

We force tool use (tool_choice={"type": "any"}) rather than letting the
model reply with plain text — for an automation agent, a free-text
non-action response is useless to us, so we don't want to leave that door
open.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

from agent.tools import TOOLS

load_dotenv()

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an automation agent operating a legacy bank servicing web application on behalf of a human operator. You are shown the current page as an accessibility tree (role + accessible name for each interactive element) rather than a screenshot or raw HTML.

Your job: accomplish the stated goal by choosing exactly one tool call per turn based on the current page state.

Rules:
- Only interact with elements that actually appear in the current page snapshot. Use the role and name exactly as shown.
- Take one action at a time. You will be shown the resulting new page snapshot after each action, and asked to decide again.
- Call goal_complete only when the current page snapshot clearly shows the goal has been reached (e.g. a confirmation page with the expected details visible). Do not call it prematurely.
- Call stuck if the page doesn't match what you expect, if you've tried the same thing multiple times without progress, or if continuing would require guessing rather than acting on what's actually visible.
- Never invent data (like a specific record ID) that wasn't given to you in the goal."""


def decide_next_action(goal: str, snapshot: str, history: list[str]) -> dict:
    """
    Ask Claude to decide the next action.

    Returns a dict: {"tool": <tool name>, "input": <tool input dict>}
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    history_text = (
        "\n".join(f"{i+1}. {h}" for i, h in enumerate(history))
        if history
        else "(no actions taken yet)"
    )

    user_message = f"""Goal: {goal}

Actions taken so far:
{history_text}

Current page snapshot:
{snapshot}

Decide the next action."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if block.type == "tool_use":
            return {"tool": block.name, "input": block.input}

    raise RuntimeError(f"Model did not return a tool call. Response: {response.content}")


if __name__ == "__main__":
    # Quick manual check: decide one action for the search page, no loop yet.
    from playwright.sync_api import sync_playwright
    from agent.perception import snapshot_page

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://127.0.0.1:5000/search")
        snapshot = snapshot_page(page)
        browser.close()

    print("--- Snapshot shown to model ---")
    print(snapshot)

    decision = decide_next_action(
        goal="Look up member 10001 and read their savings balance.",
        snapshot=snapshot,
        history=[],
    )

    print("\n--- Model decision ---")
    print(decision)