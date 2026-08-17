"""
CLI entry point for running the discovery agent on any goal.

This is the canonical "record a new capability" entry point -- run a goal
here, then hand the resulting evidence log to artifacts.record to produce
a saved Capability. See README.md for the full demo path.

Usage:
    python -m agent.run_discovery "Open a new checking sub-account for member 10001 with an initial deposit of $150, and reach the confirmation screen." \\
        --start-url http://127.0.0.1:5000/search
"""

import argparse

from agent.loop import run_discovery
from agent.evidence import save_discovery_log


def main():
    parser = argparse.ArgumentParser(description="Run the LLM-driven discovery agent on a goal.")
    parser.add_argument("goal", help="Natural-language goal for the agent to accomplish.")
    parser.add_argument("--start-url", required=True, help="URL of the target app's entry point.")
    parser.add_argument("--max-steps", type=int, default=15, help="Stop after this many steps if not done.")
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser window.")
    parser.add_argument("--evidence-dir", default="evidence", help="Directory to save the log/screenshots into.")
    args = parser.parse_args()

    print(f"Goal: {args.goal}")
    print(f"Start URL: {args.start_url}\n")

    result = run_discovery(
        goal=args.goal,
        start_url=args.start_url,
        max_steps=args.max_steps,
        headless=args.headless,
        evidence_dir=args.evidence_dir,
    )

    print(f"\n=== Discovery finished: {result.status} ===")
    print(f"Outputs: {result.outputs}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Escalations: {len(result.escalations)}")
    print(f"\nSteps taken ({len(result.steps)}):")
    for s in result.steps:
        print(f"  {s.step_number}. {s.decision['tool']}({s.decision['input']}) -> {s.result_status}: {s.result_detail}")

    log_path = save_discovery_log(result, args.goal, args.start_url, args.evidence_dir)
    print(f"\nEvidence log saved to: {log_path}")

    if result.status == "goal_complete":
        print(
            "\nNext step: run `python -m artifacts.record` to convert this successful "
            "run into a reusable capability artifact."
        )


if __name__ == "__main__":
    main()