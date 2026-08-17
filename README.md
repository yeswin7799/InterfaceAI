# InterfaceAI -- Computer-Use Automation System

A small end-to-end system that lets an LLM discover how to automate a legacy,
no-test-ID banking UI, records what it learned as a typed, reusable
**capability** artifact, and replays that capability deterministically --
without the LLM -- to power production-style invocations.

See `REPORT.md` for the full design write-up (architecture, artifact schema,
error handling, safety model, and known cuts).

## What's here
target_app/ -- mock legacy bank servicing app (Flask, table-based, no test IDs)
agent/ -- LLM-driven discovery loop (observe -> decide -> act) + escalation
artifacts/ -- capability schema + recorder (discovery trace -> reusable artifact)
replay/ -- deterministic replay engine (no LLM) + CLI
safety/ -- allowlist, risk confirmation, redaction
evidence/ -- saved logs/screenshots/artifacts from real runs
tests/ -- (see Cuts in REPORT.md)

## Setup

Requires Python 3.11+.

```bash
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash; use `source venv/bin/activate` on macOS/Linux

pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file in the repo root (never committed -- see `.gitignore`)
with your own Anthropic API key:
ANTHROPIC_API_KEY=sk-ant-your-key-here

You'll need your own key to run **discovery** (Section 4 of the assignment
requires the discovery run to be genuine). **Replay does not call the LLM at
all** and works with no API key and no cost.

## Running it

**1. Start the target app** (in its own terminal, leave it running):

```bash
cd target_app
python app.py
```

Visit `http://127.0.0.1:5000/search` to confirm it's up. Seeded members:
`10001`, `10002` (active), `10003` (restricted, for testing permission-denied).

**2. Run discovery on a goal** (in a second terminal, from the repo root):

```bash
python -m agent.run_discovery 'Open a new checking sub-account for member 10001 with an initial deposit of $150, and reach the confirmation screen.' --start-url http://127.0.0.1:5000/search
```

> **Note (Windows/Git Bash):** use single quotes around the goal text if it
> contains a `$` -- double quotes trigger bash variable expansion and will
> silently mangle the text (e.g. `$150` becomes `50`).

A real Chromium window opens and the agent drives it live. This writes a
structured JSON log and a screenshot to `evidence/`.

**3. Record the successful run as a reusable artifact:**

```bash
python -m artifacts.record
```

This loads the most recent successful discovery log and saves
`artifacts/open_sub_account.v1.0.0.json`.

**4. Replay the artifact -- no LLM involved:**

```bash
python -m replay.run_replay artifacts/open_sub_account.v1.0.0.json \
    --param member_id=10002 --param account_type=Savings --param initial_deposit=300 \
    --confirm
```

Note the parameters differ from the discovery run (`10002`/Savings/$300 vs.
`10001`/Checking/$150) -- this is deliberately proving genuine reuse, not
replaying a frozen recording. `--confirm` is required because this
capability is marked `risk_level: "risky"` (it creates a real record); see
`REPORT.md` Safety.

**Try a business-outcome case** (no crash, a clean structured result):

```bash
python -m replay.run_replay artifacts/open_sub_account.v1.0.0.json \
    --param member_id=99999 --param account_type=Savings --param initial_deposit=100 \
    --confirm
```

**Try the escalation path** (agent gets stuck, hands off to a human, resumes):

```bash
python -m agent.run_discovery "Update member 10001's phone number to 555-1234." --start-url http://127.0.0.1:5000/search
```

This goal is intentionally impossible in our target app (no such field
exists). The agent will call `stuck`, print an intervention banner, and
pause -- the live browser window stays open and interactive. Press Enter at
the prompt to hand control back and let the agent resume/retry.

## Running without live services

The target app is local and free to run indefinitely. Discovery needs a live
Anthropic API key (small real cost per run -- a handful of LLM calls).
Replay needs **no** API key and **no** LLM calls at all; it only needs the
target app and a saved artifact.

## Windows / Git Bash + conda environment notes

If `python` resolves to the wrong interpreter, or you hit SSL/certificate
errors calling the Anthropic API, it's very likely a conda-related shell
issue, not this project. See the "Environment gotchas" note in `REPORT.md`
for the specific fixes we hit during development (`conda config --set
auto_activate_base false`, removing a stray `alias python=` from
`~/.bashrc`, and an inherited `SSL_CERT_FILE` pointing at a nonexistent
path).

