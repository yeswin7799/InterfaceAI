"""
CLI entry point for replaying a saved capability artifact.

Generic across any Capability -- parameters are supplied as --param name=value
pairs rather than hardcoded flags, since different capabilities will have
different parameter names. Values are coerced to the type declared in the
artifact's parameters list (string/number) before being passed to the
replay engine.

Usage:
    python -m replay.run_replay artifacts/open_sub_account.v1.0.0.json \\
        --param member_id=10002 --param account_type=Savings --param initial_deposit=300
"""

import argparse

from artifacts.schema import Capability
from replay.engine import replay_capability


def load_capability(path: str) -> Capability:
    with open(path, "r", encoding="utf-8") as f:
        return Capability.model_validate_json(f.read())


def coerce_params(capability: Capability, raw_params: dict[str, str]) -> dict:
    """Convert CLI string values to the types declared in the capability's parameters."""
    param_types = {p.name: p.type for p in capability.parameters}
    coerced = {}
    for name, raw_value in raw_params.items():
        declared_type = param_types.get(name, "string")
        if declared_type == "number":
            coerced[name] = float(raw_value)
        else:
            coerced[name] = raw_value
    return coerced


def parse_param_arg(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"--param must be name=value, got: {s!r}")
    name, _, value = s.partition("=")
    return name, value


def main():
    parser = argparse.ArgumentParser(description="Replay a saved capability artifact, no LLM involved.")
    parser.add_argument("artifact_path", help="Path to the saved capability JSON.")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        dest="params",
        type=parse_param_arg,
        help="A parameter as name=value. Repeat for multiple parameters.",
    )
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser window.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to execute a 'risky' capability (one that writes/creates real records).",
    )
    args = parser.parse_args()

    capability = load_capability(args.artifact_path)
    raw_params = dict(args.params)
    params = coerce_params(capability, raw_params)

    print(f"Replaying '{capability.name}' v{capability.version} (risk_level={capability.risk_level})")
    print(f"Parameters: {params}\n")

    result = replay_capability(capability, params, headless=args.headless, confirmed=args.confirm)

    print(f"=== Replay finished: {result.status} ===")
    if result.status == "success":
        print(f"Outputs: {result.outputs}")
    elif result.status == "business_outcome":
        print(f"Outcome: {result.outcome_name}")
        print(f"Description: {result.outcome_description}")
    else:  # hard_failure
        print(f"Failed at step: {result.failure_step}")
        print(f"Expected: {result.failure_expected}")
        print(f"Observed: {result.failure_observed}")


if __name__ == "__main__":
    main()
    