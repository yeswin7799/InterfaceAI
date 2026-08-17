# Design Report

## 1. Architecture

Two independent paths share one artifact:

**Discovery** (uses the LLM):
1. Goal + start URL in
2. **Observe** -- capture an ARIA snapshot of the current page
3. **Decide** -- Claude picks one tool call (`fill_field`, `click_element`, `select_option`, `goal_complete`, or `stuck`)
4. **Act** -- Playwright executes it via a `(role, name)` locator
5. Repeat 2-4 until `goal_complete`, `stuck` (→ escalation, then resume), or `max_steps`
6. Produces a `DiscoveryResult` → `artifacts.record.record_capability()` → a saved `Capability` (JSON)

**Replay** (no LLM, reads the artifact from step 6):
1. Artifact + parameter values in
2. For each recorded step: resolve the value, execute it via the same `(role, name)` locator, with a timeout+retry for transient slowness
3. After every step, check the page against the artifact's `known_outcomes`
4. If all steps finish: check the checkpoint text, extract declared outputs
5. Returns a `ReplayResult`: `success`, `business_outcome`, or `hard_failure`

**Perception is role+accessible-name, not screenshots.** Every observation
is Playwright's ARIA snapshot; every action targets `(role, name)` via
`page.get_by_role()`. This survives our target app having zero
`id`/`class`/`data-testid` attributes, costs text tokens not image tokens,
and -- most importantly -- is the *same* format the artifact records and
replay re-executes. No translation step between what the model reasoned
about and what replay looks for.

**Tool-calling, not free-text parsing.** The agent's "decide" step forces
Claude to call one of five defined tools (`fill_field`, `click_element`,
`select_option`, `goal_complete`, `stuck`) via `tool_choice={"type": "any"}`.
Guarantees a structurally valid action every turn; the action vocabulary is
one explicit, reviewable list (`agent/tools.py`).

**Discovery and replay are fully separate code paths** that agree only on
the `Capability` data format. Replay has zero dependency on the `anthropic`
SDK or an API key -- it's meant to run cheaply, at volume, in production.

**Single-process, synchronous, no queue.** Given the brief discourages
premature scaling infrastructure and we implement against one target app,
a queue/worker design would be complexity with no present payoff (see
Section 4 for how this would extend without rebuilding the core model).

**Environment note:** notable build time went into a Windows/Git Bash +
conda interaction (a stray `alias python=`, and an inherited `SSL_CERT_FILE`
pointing at a nonexistent path, both silently breaking the Anthropic SDK's
HTTP client) and a sandboxed dev environment unable to download the
Playwright browser binary. Worth naming since "the environment is part of
the system" is a real theme of this assignment.

## 2. Artifact schema

A `Capability` (`artifacts/schema.py`, Pydantic) has: `parameters` (typed
inputs), `steps` (each targeting an `ElementLocator(role, name)`, with a
value that's either `value_param` or `value_literal` -- never an
unexplained hardcoded value), `outputs` (each declaring
`extract_after_label`, the visible label text a value sits next to),
`checkpoint` (a required text substring on the final page), `known_outcomes`
(named business outcomes with a `detected_by_text` signature),
`risk_level`, and `locator_strategy_notes` (required justification, not
taken on faith).

**Parameterization is an explicit, human-authored mapping, not inferred.**
`record_capability()` takes a `value_to_param` dict (e.g.
`{"10001": "member_id"}`) supplied by whoever records the artifact.
Automatic parameter-boundary inference is a genuinely hard problem, and
getting it wrong silently would produce a falsely-generalized capability --
worse than one deliberate human step. Same reasoning applies to
`known_outcomes`: a *successful* discovery run never encounters "member not
found" by definition, so those outcomes can't be mined from its trace; they
have to be declared by a reviewer with knowledge of the app's real failure
modes.

**The checkpoint is a plain text-containment check** because our
confirmation page always renders one fixed, distinctive phrase on real
success, and nowhere else. Sufficient for this target; a more heterogeneous
surface would need a richer checkpoint concept (Section 4).

Everything round-trips through JSON cleanly (Pydantic validates on load, so
a malformed artifact fails immediately, not mid-replay) -- see
`artifacts/open_sub_account.v1.0.0.json` for the real generated example.

## 3. Determinism & error handling

Determinism comes from role+name locators (stable regardless of exact
layout), zero LLM involvement in replay, and an explicit checkpoint
assertion rather than "didn't crash" being good enough.

**The three-way `ReplayResult`** is the central decision here:
- **`success`** -- checkpoint found, outputs extracted.
- **`business_outcome`** -- page text matched a `known_outcome` after *any*
  step, not just the last one. This matters concretely: a too-low deposit
  only produces its error text after step 6 (form submission); checking
  only at the end would have misreported it as a generic hard failure
  instead of the specific, actionable outcome.
- **`hard_failure`** -- neither of the above. Carries `failure_step`,
  `failure_expected`, `failure_observed` for debugging without re-running
  anything.

**Recoverable conditions:** each step attempts a short timeout (3s) first;
a `TimeoutError` triggers one retry at a longer timeout (10s) before
propagating as a hard failure -- targets the target app's `?simulate=slow`
condition directly.

All four of the target app's real business outcomes (`member_not_found`,
`permission_denied`, `deposit_too_low`, and a missing-parameter/unconfirmed-
risk hard failure) were verified against the live running engine, not just
designed on paper.

## 4. Heterogeneity & multi-tenant

**Surface abstraction:** the seam is `(role, name)` in `ElementLocator` --
nothing in the schema or replay engine assumes a browser or DOM. A desktop
app's UI Automation/Accessibility API exposes the same role/name
abstraction, so a `DesktopPerception`/`DesktopAct` pair implementing the
same interface would let the same schema, recorder, and replay engine work
unchanged. `artifacts/schema.py` imports only `pydantic` -- no
Playwright-specific types leak into the artifact itself.

**Multi-tenant reuse (designed, not built):** a capability recorded against
one tenant becomes a **base** artifact; per-tenant differences become a
small **override** artifact referencing the base by name + `tenant_id`,
replacing only the specific steps that differ. Replay resolves "base +
override for this tenant" before executing -- additive to the schema, not
a redesign.

**Drift detection (designed, not built):** a `hard_failure` where
`failure_expected` names a missing element is itself a drift signal;
accumulating these per-tenant surfaces "this tenant's app moved this
control" without bespoke tooling. The same signal could gate an artifact
out of unattended replay for that tenant automatically.

Not built because the brief is explicit this is a design question, and
building it against one target app would validate nothing real.

## 5. Escalation & handoff

Discovery runs with a real, visible Chromium window. When the model calls
`stuck`, `agent/escalation.py` captures context (goal, step, reason,
snapshot, screenshot) to `evidence/`, prints a banner, and blocks on
`input()`. The browser window stays open and interactive during that
block -- **the same live session**, not a fresh one. Pressing Enter (our
deliberately bare operator surface, per the assignment's scope note) hands
control back; a fresh snapshot/screenshot is captured as the "after" state.

**The loop resumes, not stops:** after escalation, discovery loops back
into observe/decide/act with a history note that a human intervened. We
validated this for real: given an intentionally impossible goal ("update
member 10001's phone number" -- no such field exists), the agent correctly
called `stuck`, escalated, was handed back control, and gave an honest,
increasingly specific report each time rather than hallucinating success --
six real escalations, all in `evidence/`, ending in `max_steps_exceeded`.
Arguably better evidence than a clean success: the system never claimed to
do something it couldn't.

**Honest limitation:** because the human acts directly in the browser, not
through our tool vocabulary, we get a before/after page snapshot, not an
action-by-action log of what they clicked. A full operator console
(explicitly out of scope) would capture at the action level.

**Replay's escalation path** would call the same `request_intervention()`
on a `hard_failure`; not wired in (see Section 7) since discovery's version
is what's directly demoable without extra infrastructure.

## 6. Safety

**Allowlist (`safety/policy.py`):** deny-by-default `ALLOWED_HOSTS` and
`ALLOWED_ACTIONS`, checked *before* acting -- host before `page.goto()`,
action type before each step. Violations become a structured refusal, not
an uncaught exception.

**Risky actions -- confirmation, chosen and justified.** Outright blocking
would make "risky" capabilities unusable in production; a passive flag
doesn't gate anything. `Capability.risk_level` is declared explicitly at
recording time; `replay_capability()` checks it *before launching a
browser* and refuses a `risky` capability without `confirmed=True`. Our
`open_sub_account` capability (creates a real financial record) is marked
risky; both paths -- refusal without `--confirm`, success with it -- were
verified directly.

**Redaction (`safety/redaction.py`):** our target app has no
credentials/tokens (no login system), so the concrete sensitive category is
financial data. `redact_value()` recursively masks dollar-amount-shaped
substrings before any evidence log is written to disk -- verified against a
real saved log, where `$150.00` appears as `$[REDACTED]` in the snapshot,
reasoning text, and structured outputs alike, while non-sensitive fields
stay readable.

**Honest limitation:** only *formatted* dollar amounts are caught; a raw
unformatted number typed into a form isn't, since it's indistinguishable
from a member ID without field-level context. A production system would
need field-aware redaction and broader PII coverage. This is one correctly-
scoped example of the pattern, not a comprehensive solution.

## 7. Cuts

- **Automated tests.** `tests/` is empty -- time went into manually
  validating every core requirement against the real, live system instead.
  Highest-value next tests: schema validation edge cases, redaction regex
  coverage, and replay's outcome/checkpoint logic against a mocked page.
- **Replay-side escalation.** Designed (Section 5), not wired in.
- **A second recorded capability**, to prove the schema/recorder/replay
  path is genuinely generic rather than implicitly shaped around
  `open_sub_account`.
- **Multi-tenant and desktop support.** Designed (Section 4), not built,
  per the brief's own instruction.
- **UI drift detection**, **confidence scoring/approval gating**, and
  **field-aware redaction** -- all designed conceptually above, none built.
- **Agent-facing capability catalog (stretch goal).** Capabilities are
  invoked via CLI, not exposed as a discoverable tool surface -- with only
  one capability recorded, a catalog wasn't yet a real problem to solve.

**Priority if continuing:** replay-side escalation (the actual production
path) → a second capability (pressure-test genericity) → the test suite →
field-aware redaction (given this handles regulated financial data).