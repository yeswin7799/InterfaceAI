"""
Serializes a DiscoveryResult to a structured JSON evidence file.

This is the "structured log of what the agent did and why" required by
Section 3.5. It's deliberately just a straightforward dump of the full step
trace (goal, target, every decision, every result, final outputs) -- nothing
fancy, but complete enough that a human reviewer can reconstruct exactly
what happened without re-running anything.
"""

import json
import os
import time
from dataclasses import asdict

from agent.loop import DiscoveryResult


def save_discovery_log(result: DiscoveryResult, goal: str, start_url: str, output_dir: str) -> str:
    """
    Write the full discovery trace to a timestamped JSON file in output_dir.
    Returns the path written.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(output_dir, f"discovery-log-{timestamp}.json")

    record = {
        "goal": goal,
        "start_url": start_url,
        "status": result.status,
        "outputs": result.outputs,
        "reasoning": result.reasoning,
        "screenshot_path": result.screenshot_path,
        "steps": [asdict(s) for s in result.steps],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return path