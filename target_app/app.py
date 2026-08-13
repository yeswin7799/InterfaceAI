"""
Mock "legacy bank" servicing tool.

This is our stand-in for a real core-banking / servicing app: server-rendered
HTML, no JS framework, no test IDs, table-based layout. It exists purely so
we have a realistic, controllable surface for the computer-use agent to
operate  see /REPORT.md section 1 for why we built our own instead of using
a public site.

Nothing here talks to a real database. Member data lives in memory and
resets every time the process restarts  that's intentional: this app is a
throwaway target, not a product.
"""
import time
import uuid

from flask import Flask, render_template, request, redirect

app = Flask(__name__)
app.secret_key = "dev-only-secret-not-for-production"  # fine for a local mock; a real app would load this from env/secret store

# In-memory "database" of members.
# Keying by member_id (string) so lookups mimic what a real search form would take.
MEMBERS = {
    "10001": {
        "member_id": "10001",
        "name": "Alice Johnson",
        "status": "active",
        "savings_balance": 4520.75,
    },
    "10002": {
        "member_id": "10002",
        "name": "Brian Osei",
        "status": "active",
        "savings_balance": 1289.10,
    },
    "10003": {
        "member_id": "10003",
        "name": "Carla Nguyen",
        "status": "restricted",  # used later to demo a "permission denied" business outcome
        "savings_balance": 730.00,
    },
}

# Sub-accounts opened during a session live here too  in-memory, reset on restart.
SUB_ACCOUNTS = {}

@app.route("/search", methods=["GET"])
def search_form():
    """The search screen. GET just shows the empty form."""
    return render_template("search.html")


@app.route("/search", methods=["POST"])
def search_submit():
    """
    Handle the search form submission.

    On a valid, known member ID -> redirect to their detail page (built next step).
    On an unknown ID -> re-render the search form with an inline error. This is
    a *business outcome* ("no such member"), not a crash — an important
    distinction the replay engine will need to make later (see REPORT.md,
    Determinism & error handling).
    """
    member_id = request.form.get("member_id", "").strip()

    if member_id in MEMBERS:
        return redirect(f"/member/{member_id}")

    return render_template(
        "search.html",
        error=f"No member found with ID '{member_id}'.",
        submitted_id=member_id,
    )

@app.route("/member/<member_id>", methods=["GET"])
def member_detail(member_id):
    """
    Show a member's detail page.

    Three business outcomes, all of which the agent/replay must distinguish
    from crashes:
      - unknown member_id -> back to search with an error (shouldn't normally
        happen via the UI since search already filters this, but guards
        against a bad/stale link or direct navigation).
      - status == "restricted" -> permission-denied view, no balance shown.
      - otherwise -> full detail view with the "open sub-account" action.

    Also supports ?simulate=slow, which adds an artificial delay before
    responding — a *recoverable condition* (transient slowness), not a
    business outcome. The page still loads correctly; something waiting on
    it just needs to be patient rather than giving up. This is here so the
    replay engine has a real condition to demonstrate wait/retry logic
    against (see REPORT.md, Determinism & error handling).
    """
    if request.args.get("simulate") == "slow":
        time.sleep(4)

    member = MEMBERS.get(member_id)

    if member is None:
        return redirect(f"/search")

    if member["status"] == "restricted":
        return render_template("member_detail.html", denied=True, member=member)

    return render_template("member_detail.html", denied=False, member=member)

def _get_accessible_member(member_id):
    """
    Shared guard used by both the form and submit routes: resolves a member
    for this flow, or returns None if it's not accessible (unknown or
    restricted). Defense-in-depth — the detail page already hides the link
    for restricted/unknown members, but a direct URL shouldn't bypass that.
    """
    member = MEMBERS.get(member_id)
    if member is None or member["status"] == "restricted":
        return None
    return member


@app.route("/member/<member_id>/open-sub-account", methods=["GET"])
def open_sub_account_form(member_id):
    member = _get_accessible_member(member_id)
    if member is None:
        return redirect("/search")
    return render_template("open_sub_account.html", member=member)


@app.route("/member/<member_id>/open-sub-account", methods=["POST"])
def open_sub_account_submit(member_id):
    """
    Validate and process the sub-account form.

    Validation error (bad deposit amount) -> re-render the form with an
    inline error and the submitted values preserved. This is a *business
    outcome* (validation error), one of the three categories the replay
    engine must distinguish per REPORT.md.

    On success -> create the sub-account and redirect to the confirmation
    checkpoint page.
    """
    member = _get_accessible_member(member_id)
    if member is None:
        return redirect("/search")

    account_type = request.form.get("account_type", "")
    initial_deposit_raw = request.form.get("initial_deposit", "").strip()

    error = None
    initial_deposit = None

    if account_type not in ("savings", "checking", "certificate"):
        error = "Please select a valid account type."
    else:
        try:
            initial_deposit = float(initial_deposit_raw)
            if initial_deposit < 25:
                error = "Initial deposit must be at least $25.00."
        except ValueError:
            error = f"'{initial_deposit_raw}' is not a valid dollar amount."

    if error:
        return render_template(
            "open_sub_account.html",
            member=member,
            error=error,
            account_type=account_type,
            initial_deposit=initial_deposit_raw,
        )

    sub_account_id = f"SA-{uuid.uuid4().hex[:8].upper()}"
    SUB_ACCOUNTS[sub_account_id] = {
        "sub_account_id": sub_account_id,
        "member_id": member_id,
        "account_type": account_type,
        "initial_deposit": initial_deposit,
    }

    return redirect(f"/sub-account/{sub_account_id}/confirmation")


@app.route("/sub-account/<sub_account_id>/confirmation", methods=["GET"])
def sub_account_confirmation(sub_account_id):
    sub_account = SUB_ACCOUNTS.get(sub_account_id)
    if sub_account is None:
        return redirect("/search")
    return render_template("confirmation.html", sub_account=sub_account)

@app.route("/health")
def health():
    """Plain liveness check  not part of the automated flow, just useful
    for us to confirm the server is up before pointing an agent at it."""
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True, port=5000)