"""
The action vocabulary for the discovery agent's "decide" step.

We use Claude's tool-calling rather than asking the model to emit free-form
JSON in a text response. Tool calling guarantees a validly-structured
response and gives us one clean, self-documenting place that defines exactly
what the agent is allowed to do — which doubles as useful material for
REPORT.md's Architecture section.

Every tool that targets an element takes (role, name) rather than a
selector string or coordinates — this is deliberate: role+name is exactly
what our perception layer (agent/perception.py) extracts from the page, and
exactly what Playwright's page.get_by_role(role, name=name) can act on. The
same (role, name) pair the model reasons about is the same locator that ends
up recorded in the artifact for replay.
"""

TOOLS = [
    {
        "name": "fill_field",
        "description": "Type text into a textbox on the current page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "The accessibility role of the target element, e.g. 'textbox'.",
                },
                "name": {
                    "type": "string",
                    "description": "The accessible name (visible label) of the target element, exactly as shown in the page snapshot.",
                },
                "text": {
                    "type": "string",
                    "description": "The text to type into the field.",
                },
            },
            "required": ["role", "name", "text"],
        },
    },
    {
        "name": "click_element",
        "description": "Click a button or link on the current page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "The accessibility role of the target element, e.g. 'button' or 'link'.",
                },
                "name": {
                    "type": "string",
                    "description": "The accessible name (visible label) of the target element, exactly as shown in the page snapshot.",
                },
            },
            "required": ["role", "name"],
        },
    },
    {
        "name": "select_option",
        "description": "Choose an option from a dropdown/combobox on the current page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "The accessibility role of the target element, e.g. 'combobox'.",
                },
                "name": {
                    "type": "string",
                    "description": "The accessible name (visible label) of the target element.",
                },
                "option": {
                    "type": "string",
                    "description": "The visible text of the option to select, exactly as shown in the page snapshot.",
                },
            },
            "required": ["role", "name", "option"],
        },
    },
    {
        "name": "goal_complete",
        "description": (
            "Declare that the goal has been fully accomplished and the current "
            "page is the correct end state (the checkpoint). Only call this "
            "once you can see, in the current page snapshot, clear evidence "
            "the goal was reached."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of why the goal is considered complete, referencing what's visible on the page.",
                },
                "outputs": {
                    "type": "object",
                    "description": "Any data extracted from the final page that the goal asked for, as key-value pairs (e.g. {'sub_account_id': 'SA-1234ABCD'}).",
                },
            },
            "required": ["reasoning", "outputs"],
        },
    },
    {
        "name": "stuck",
        "description": (
            "Declare that you cannot safely or confidently proceed toward the "
            "goal from the current state (e.g. an unexpected page, ambiguous "
            "elements, or repeated failed attempts). This will trigger "
            "escalation to a human operator."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're stuck and what you'd need a human to resolve.",
                },
            },
            "required": ["reason"],
        },
    },
]