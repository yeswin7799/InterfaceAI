"""
Perception layer for the discovery agent.

This module is responsible for turning "whatever the browser currently shows"
into a compact, text-only description the LLM can reason over — the
"observe" half of the observe -> decide -> act loop.

We use Playwright's ARIA snapshot rather than raw HTML or a screenshot. Why:
  - It exposes each element's *role* (button, textbox, link, combobox, ...)
    and *accessible name* (its visible label) regardless of whether the
    underlying markup has clean IDs/classes — exactly the "no test IDs"
    legacy-app problem this project is built around.
  - Playwright can later locate the *same* element by role+name via
    page.get_by_role(role, name=name) — so the thing we show the model is
    also directly usable as a stable locator, both for acting during
    discovery and for the artifact's replay locators.
  - It's the same abstraction native desktop apps expose too, which matters
    for the "how would this extend beyond a web app" design question.

Note: Playwright's older page.accessibility.snapshot() API has been removed
in current versions. locator.aria_snapshot() is the modern replacement — it
returns a compact YAML-style string of the accessibility tree, which is
arguably even better suited to feeding an LLM than a raw nested dict.
"""

from playwright.sync_api import Page


def snapshot_page(page: Page) -> str:
    """
    Return a YAML-style text snapshot of the page's accessibility tree,
    e.g.:

        - textbox "Member ID:"
        - button "Search"

    This is what we'll hand the LLM as its "observation" of the current
    screen at each step of the agent loop.
    """
    return page.locator("body").aria_snapshot()


if __name__ == "__main__":
    # Quick manual check: point this at any running target-app page and
    # print what the model would "see" there.
    #   python agent/perception.py                                  (defaults to /search)
    #   python agent/perception.py http://127.0.0.1:5000/member/10001/open-sub-account
    import sys
    from playwright.sync_api import sync_playwright

    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000/search"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        snapshot = snapshot_page(page)
        print(f"--- ARIA snapshot for {url} ---")
        print(snapshot)

        browser.close()