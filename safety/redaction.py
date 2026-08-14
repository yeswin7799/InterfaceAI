"""
Redaction utilities (Section 3.4): strip sensitive data before it's
persisted to evidence logs or artifacts.

Our target app has no credentials/tokens (no login system), so the main
sensitive category we actually handle is financial data -- dollar amounts
(balances, deposits). This redacts those specifically.

Scope note (see REPORT.md, Safety): this is intentionally narrow -- a real
deployment handling regulated financial data would need broader PII
redaction (full account numbers, SSNs, names). Implemented here as one
concrete, working example of the pattern rather than a comprehensive
solution.
"""

import re

DOLLAR_AMOUNT_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?")


def redact_dollar_amounts(text: str) -> str:
    """Replace any dollar-amount-looking substring with a redaction marker."""
    return DOLLAR_AMOUNT_PATTERN.sub("$[REDACTED]", text)


def redact_value(obj):
    """
    Recursively redact dollar amounts from a nested structure of
    str/dict/list (e.g. a full evidence log record before json.dump).
    Non-string leaf values (numbers, booleans, None) pass through unchanged.
    """
    if isinstance(obj, str):
        return redact_dollar_amounts(obj)
    if isinstance(obj, dict):
        return {k: redact_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_value(v) for v in obj]
    return obj