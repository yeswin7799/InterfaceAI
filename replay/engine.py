"""
The deterministic replay engine (Section 3.3): given a saved Capability and
a set of parameter values, executes the recorded flow against a live
surface WITHOUT the LLM in the decision loop, and returns one of three
clearly distinct result shapes:

  - success          -- checkpoint reached, declared outputs extracted
  - business_outcome  -- a known_outcome's text was detected (e.g. "no such
                         member") -- a legitimate result, not a crash
  - hard_failure      -- something genuinely unexpected: no known outcome
                         matched, checkpoint never reached, and/or a step
                         could not be executed at all

Locator strategy mirrors agent/act.py deliberately: steps target elements by
(role, name), the same abstraction discovery reasoned about, so a replay
failure and a discovery failure would look the same to a human debugging
either one.

Recoverable-condition handling: each step is attempted with a short
timeout first; a Playwright timeout (the natural signature of "the page is
being slow") triggers one retry with a longer timeout rather than an
immediate hard failure. Anything that still fails after the retry is a
genuine hard failure, not a transient one.
"""

from dataclasses import dataclass, field

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from artifacts.schema import ArtifactStep, Capability
from safety.policy import SafetyViolation, check_action_allowed, check_host_allowed

SHORT_TIMEOUT_MS = 3000
RETRY_TIMEOUT_MS = 10000


@dataclass
class ReplayResult:
    status: str  # "success" | "business_outcome" | "hard_failure"
    outputs: dict = field(default_factory=dict)

    # populated when status == "business_outcome"
    outcome_name: str = ""
    outcome_description: str = ""

    # populated when status == "hard_failure" -- structured enough to debug
    # without re-running anything (Section 3.3's "what step, what was
    # expected, what was observed").
    failure_step: int | None = None
    failure_expected: str = ""
    failure_observed: str = ""


def _resolve_value(step: ArtifactStep, params: dict) -> str | None:
    """Turn a step's value_param/value_literal into the concrete string to use."""
    if step.value_param is not None:
        if step.value_param not in params:
            raise ValueError(f"Missing required parameter: '{step.value_param}'")
        return str(params[step.value_param])
    if step.value_literal is not None:
        return step.value_literal
    return None


def _execute_step(page: Page, step: ArtifactStep, value: str | None) -> None:
    """
    Execute one step, with a short-timeout attempt followed by one
    longer-timeout retry -- this is the recoverable-condition handling for
    transient slowness. Lets a genuine Playwright error propagate after the
    retry also fails; the caller classifies that as a hard failure.
    """
    locator = page.get_by_role(step.target.role, name=step.target.name)

    for timeout_ms in (SHORT_TIMEOUT_MS, RETRY_TIMEOUT_MS):
        try:
            if step.action == "fill_field":
                locator.fill(value, timeout=timeout_ms)
            elif step.action == "click_element":
                locator.click(timeout=timeout_ms)
            elif step.action == "select_option":
                locator.select_option(label=value, timeout=timeout_ms)
            else:
                raise ValueError(f"Unknown step action: {step.action}")
            return  # succeeded
        except PlaywrightTimeoutError:
            if timeout_ms == RETRY_TIMEOUT_MS:
                raise  # both attempts failed -- let this become a hard failure
            continue  # try again with the longer timeout


def replay_capability(capability: Capability, params: dict, headless: bool = True, confirmed: bool = False) -> ReplayResult:
    """
    Replay capability against a live browser using params, with no LLM
    involved in any decision.

    Risky capabilities (risk_level == "risky") refuse to execute unless
    confirmed=True is explicitly passed -- this is the "require
    confirmation" handling for risky/irreversible actions (Section 3.4).
    The check happens before the browser even launches, same posture as
    the missing-parameter check below: fail fast, don't do partial work
    you then have to explain.
    """
    if capability.risk_level == "risky" and not confirmed:
        return ReplayResult(
            status="hard_failure",
            failure_step=0,
            failure_expected="Explicit confirmation (confirmed=True) for a 'risky' capability.",
            failure_observed=(
                f"Capability '{capability.name}' is marked risky (it creates/modifies real records) "
                "and was invoked without confirmation. Refusing to execute."
            ),
        )
    # Fail fast on missing required parameters, before touching the browser.
    for p in capability.parameters:
        if p.required and p.name not in params:
            return ReplayResult(
                status="hard_failure",
                failure_step=0,
                failure_expected=f"Required parameter '{p.name}' to be provided.",
                failure_observed="Parameter was missing from the replay call.",
            )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()

        try:
            check_host_allowed(capability.start_url)
        except SafetyViolation as e:
            browser.close()
            return ReplayResult(status="hard_failure", failure_step=0, failure_expected="Allowed start_url host.", failure_observed=str(e))

        page.goto(capability.start_url)

        for step in capability.steps:
            try:
                check_action_allowed(step.action)
                value = _resolve_value(step, params)
                _execute_step(page, step, value)
            except SafetyViolation as e:
                browser.close()
                return ReplayResult(
                    status="hard_failure",
                    failure_step=step.step_number,
                    failure_expected="Action to be within the safety allowlist.",
                    failure_observed=str(e),
                )
            except Exception as e:
                body_text = page.locator("body").inner_text()
                # Even on a hard failure to execute a step, check whether a
                # known business outcome explains why (e.g. the previous
                # step already landed us on an error page and this step's
                # target genuinely doesn't exist because of that).
                for outcome in capability.known_outcomes:
                    if outcome.detected_by_text in body_text:
                        browser.close()
                        return ReplayResult(
                            status="business_outcome",
                            outcome_name=outcome.name,
                            outcome_description=outcome.description,
                        )
                browser.close()
                return ReplayResult(
                    status="hard_failure",
                    failure_step=step.step_number,
                    failure_expected=f"{step.action} on {step.target.role} '{step.target.name}' to succeed.",
                    failure_observed=f"{type(e).__name__}: {e}",
                )

            # After a successful step, check whether we've landed on a known
            # business outcome before continuing blindly toward the checkpoint.
            body_text = page.locator("body").inner_text()
            for outcome in capability.known_outcomes:
                if outcome.detected_by_text in body_text:
                    browser.close()
                    return ReplayResult(
                        status="business_outcome",
                        outcome_name=outcome.name,
                        outcome_description=outcome.description,
                    )

        # All steps executed without error and no known outcome matched --
        # now verify the checkpoint actually holds.
        body_text = page.locator("body").inner_text()
        if capability.checkpoint.expected_text_contains not in body_text:
            browser.close()
            return ReplayResult(
                status="hard_failure",
                failure_step=len(capability.steps),
                failure_expected=f"Checkpoint text '{capability.checkpoint.expected_text_contains}' to be present.",
                failure_observed="Checkpoint text was not found on the final page.",
            )

        outputs = {}
        for output_def in capability.outputs:
            try:
                label_locator = page.get_by_text(
                    output_def.extract_after_label, exact=True
                ).first
                value_locator = label_locator.locator("xpath=following-sibling::td[1]")
                outputs[output_def.name] = value_locator.inner_text(
                    timeout=SHORT_TIMEOUT_MS
                ).strip()
            except Exception as e:
                browser.close()
                return ReplayResult(
                    status="hard_failure",
                    failure_step=len(capability.steps),
                    failure_expected=f"Output '{output_def.name}' to be readable after label '{output_def.extract_after_label}'.",
                    failure_observed=f"{type(e).__name__}: {e}",
                )

        browser.close()
        return ReplayResult(status="success", outputs=outputs)
