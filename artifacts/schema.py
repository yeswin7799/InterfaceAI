"""
The artifact schema: a typed, versioned, serializable description of a
reusable "capability" an AI agent can invoke -- the reusable output of a
successful discovery run (Section 3.2).

Design rationale, in one place since this is the focal point of the project:

- Steps reference elements by (role, name) -- exactly what our perception
  layer extracts from the accessibility tree and exactly what Playwright's
  page.get_by_role(role, name=name) can locate. No CSS selectors, no
  coordinates, no dependence on IDs/classes the legacy app doesn't have.
  This is *why* role+name was chosen back in the agent design (see
  agent/perception.py) -- it was chosen specifically because it would also
  make a good, stable replay locator.

- A step's value (what to type, what option to select) is either a literal
  (fixed every time the capability runs) or a reference to a named,
  typed parameter (varies per invocation). This is what makes the artifact
  a genuine *capability* an agent can call with different arguments, rather
  than a frozen recording of one specific run.

- The checkpoint is a simple text-containment assertion against the final
  page. This is intentionally the simplest thing that could work: our
  target app's confirmation page always contains a fixed, distinctive
  phrase ("Sub-Account Opened Successfully") when the goal is genuinely
  reached. A more sophisticated surface might need a richer checkpoint
  (specific element present, specific structured value matched) -- see
  REPORT.md's Heterogeneity section for how this would extend.

- Everything is a Pydantic model: validation on construction (a malformed
  artifact fails loudly, immediately, not at replay time), and free JSON
  (de)serialization for storage.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ElementLocator(BaseModel):
    """Identifies one element on the page by its accessibility role + name.

    Robustness note: role+name survives markup changes that would break a
    CSS-selector or XPath-based locator (no ids/classes required), and is
    the same abstraction available on native desktop apps -- see REPORT.md
    Heterogeneity & multi-tenant.
    """

    role: str = Field(description="Accessibility role, e.g. 'textbox', 'button', 'combobox', 'link'.")
    name: str = Field(description="Accessible name (visible label), exact match required.")


class ArtifactStep(BaseModel):
    """One action in the recorded flow."""

    step_number: int
    action: Literal["fill_field", "click_element", "select_option"]
    target: ElementLocator

    # Exactly one of these should be set for fill_field/select_option.
    # click_element needs neither -- it just clicks the target.
    value_param: Optional[str] = Field(
        default=None, description="Name of the input parameter whose value should be used here."
    )
    value_literal: Optional[str] = Field(
        default=None, description="A fixed value to use every time, if this step isn't parameterized."
    )


class ArtifactParameter(BaseModel):
    """A typed input the caller must (or may) supply per invocation."""

    name: str
    type: Literal["string", "number"]
    description: str
    required: bool = True


class ArtifactOutput(BaseModel):
    """A typed piece of data the capability extracts and returns to the caller.

    Extraction strategy: our confirmation pages are label/value tables (a
    cell containing a fixed label like "Sub-Account ID:", followed by a
    cell containing the actual value). extract_after_label names the exact
    label text; replay locates it on the final page and reads the
    adjacent cell. This is deliberately simple and tied to our target app's
    real layout -- see REPORT.md Heterogeneity for how a different surface
    (no consistent label/value structure) would need a different strategy.
    """

    name: str
    type: Literal["string", "number"]
    description: str
    extract_after_label: str = Field(
        description="The exact visible label text this value appears immediately after on the checkpoint page."
    )


class Checkpoint(BaseModel):
    """
    How replay verifies the goal was actually reached, not just that steps
    were executed without a Playwright error. Currently a simple
    text-containment check against the final page's visible content.
    """

    description: str
    expected_text_contains: str = Field(
        description="Text that must appear on the final page for the run to be considered successful."
    )

class KnownOutcome(BaseModel):
    """
    A named, expected business outcome replay should recognize and report
    distinctly from a hard failure -- e.g. "member not found" or "validation
    error". Detected by a distinctive substring of text that appears on the
    page when this outcome occurs.

    Deliberately authored by whoever records/reviews the artifact, not
    inferred from the discovery run itself: a *successful* discovery run,
    by definition, never encountered these outcomes, so they can't be
    mined from its trace. This mirrors the explicit-parameterization
    decision for value_param -- see artifacts/record.py.
    """

    name: str
    description: str
    detected_by_text: str = Field(
        description="A distinctive substring of text that appears on the page when this outcome occurs."
    )


class Capability(BaseModel):
    """
    The complete artifact: a versioned, reviewable, agent-invocable
    capability produced from one successful discovery run.
    """

    name: str
    version: str
    description: str = Field(description="Human-readable summary of what this capability does.")
    start_url: str

    parameters: list[ArtifactParameter]
    steps: list[ArtifactStep]
    outputs: list[ArtifactOutput]
    checkpoint: Checkpoint
    known_outcomes: list[KnownOutcome] = Field(
        default_factory=list,
        description="Named business outcomes replay should recognize and report distinctly from hard failures.",
    )
    risk_level: Literal["safe", "risky"] = Field(
        default="safe",
        description=(
            "'safe' for read-only/reversible capabilities. 'risky' for anything that writes or creates "
            "real records (e.g. opening an account) -- replay refuses to execute a 'risky' capability "
            "unless explicitly confirmed by the caller."
        ),
    )

    locator_strategy_notes: str = Field(
        description="Reasoning about why the chosen locator strategy (role+name) is expected to be robust for this app."
    )