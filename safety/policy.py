"""
Safety allowlist policy (Section 3.4): an explicit, configurable allowlist
of hosts the agent/replay may navigate to, and action types they may
perform. Both the discovery agent and the replay engine check against this
before acting -- neither is trusted to self-limit.

This is deliberately a static, hand-authored policy rather than something
inferred from the target app or the artifact. In a real deployment this
would be per-tenant configuration (which hosts/routes THIS institution's
instance of the agent is permitted to touch), not something the automation
system decides for itself.
"""

from urllib.parse import urlparse


class SafetyViolation(Exception):
    """Raised when an action or navigation would violate the allowlist."""


# Hosts the agent/replay is permitted to navigate to. In production this
# would be per-tenant, loaded from config -- hardcoded here since we only
# have one target app.
ALLOWED_HOSTS = {"127.0.0.1:5000", "localhost:5000"}

# Action types the agent/replay is permitted to perform. Anything not in
# this set (e.g. a hypothetical future "delete_record" tool) is blocked
# by default rather than allowed by default -- deny-by-default is the
# safer posture for an allowlist.
ALLOWED_ACTIONS = {"fill_field", "click_element", "select_option"}


def check_host_allowed(url: str) -> None:
    """Raise SafetyViolation if url's host isn't on the allowlist."""
    host = urlparse(url).netloc
    if host not in ALLOWED_HOSTS:
        raise SafetyViolation(
            f"Navigation to host '{host}' is not permitted. Allowed hosts: {sorted(ALLOWED_HOSTS)}"
        )


def check_action_allowed(action: str) -> None:
    """Raise SafetyViolation if action isn't on the allowlist."""
    if action not in ALLOWED_ACTIONS:
        raise SafetyViolation(
            f"Action type '{action}' is not permitted. Allowed actions: {sorted(ALLOWED_ACTIONS)}"
        )