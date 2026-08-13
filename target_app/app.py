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

@app.route("/health")
def health():
    """Plain liveness check  not part of the automated flow, just useful
    for us to confirm the server is up before pointing an agent at it."""
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True, port=5000)