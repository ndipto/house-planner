# ai_program.py
# Step 1 of House Planner: brief -> room program (AI).
#
# What this file does:
#   1. Sends the user's brief to Muse Spark on the Meta Model API.
#   2. Gets back structured JSON: a list of rooms + a short design explanation.
#   3. Checks every room size against our size rules in plain Python.
#
# The API key is read from the META_API_KEY variable (see .env.example).
# The key is NEVER written into any file by this code.

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

# Load the local .env file (if it exists) into environment variables.
load_dotenv()

# --- API settings (from PROJECT.md, checked Oct 29, 2026) ---
# The Meta Model API is OpenAI-compatible, so we use the normal
# OpenAI Python client and only change the base URL and key.
MODEL_NAME = "muse-spark-1.3"
BASE_URL = "https://api.meta.ai/v1"


# --- Size rules (from PROJECT.md, architect's design rules) ---
# Each entry: room type -> (minimum side in ft, maximum side in ft).
# BOTH sides of the room must fall inside this range.
SIZE_RULES = {
    "bedroom": (10, 15),
    "kitchen": (8, 15),
    "living room": (12, 15),
    "family living": (12, 15),
    "dining": (10, 14),
    "bathroom": (6, 10),
}

# Corridors are long and thin: only the narrow side is checked.
CORRIDOR_MIN_WIDTH_FT = 3.5  # 3 ft 6 in

# Room types whose sizes are not fixed yet (see PROJECT.md).
# We skip the size check for these instead of guessing.
UNCHECKED_TYPES = {"porch", "foyer", "veranda", "corridor"}


# --- System prompt: architect role + design rules + JSON shape ---
# This is the instruction the AI always follows. Keep it short to save cost.
SYSTEM_PROMPT = """You are a Bangladeshi architect designing a single-floor house concept.
Units are feet and inches. Room sizes below are clear internal dimensions.

ROOM SIZES (both sides of each room must be inside its range):
- bedroom: 10 to 15 ft per side
- kitchen: 8 to 15 ft per side
- living room: 12 to 15 ft per side
- family living: 12 to 15 ft per side
- dining: 10 to 14 ft per side
- bathroom: 6 to 10 ft per side (one side of 7 ft preferred)
- corridor: at least 3 ft 6 in wide (long and thin is fine)
A room is NEVER square: its two sides must differ by at least 1 ft (corridors exempt).

HARD RULES (follow all of them):
1. Respect the room sizes and the never-square rule above.
2. No central corridor with rooms on both long sides. Use family living as the circulation hub.
3. Corridors are 25% or less of the built area.
4. Kitchen has exactly one inner door, into dining. One extra door to its own veranda is allowed.
5. Every bedroom door opens into family living. Only if there is no shared wall left for a 3 ft door, it may open into dining. NEVER into the living room.
6. Every bedroom has at least 1 window (2 preferred).
7. Try one attached bathroom per bedroom. There MUST be at least one common bathroom with a door to common space (dining, family living, or corridor), reachable without passing through any bedroom.
8. Bathrooms touch an exterior wall for ventilation. Never on the front (road) wall.
9. Bathroom windows NEVER face the front (road) side.
10. Verandas: up to 2 bedrooms get one veranda each (every bedroom if fewer than 2), plus the kitchen gets one. Verandas never touch each other. Width 3 to 5 ft, length at least 3 ft, never longer than its room's wall.
11. Bedrooms and living spaces need openings on at least 2 different walls (opposite walls preferred, adjacent walls minimum).
12. Doors and windows connect specific rooms/walls (model them, do not just draw boxes).

ZONING (road side inward): porch and foyer first, then living room (public); then dining, kitchen, family living (semi-private); bedrooms at back and sides (private), clustered around family living.

ORIENTATION (tropical monsoon climate): bedrooms and living prefer windows facing south/southeast (breeze); avoid large west-facing openings in bedrooms and living (afternoon heat); kitchen prefers the WEST side.

BATHROOMS: derive the count from the rules above (attached attempt + one common). The user does not enter it.

REPLY FORMAT: reply with JSON only, exactly this shape, no extra text:
{
  "rooms": [
    {
      "name": "Bedroom 1",
      "type": "bedroom",
      "width_ft": 12,
      "depth_ft": 14,
      "adjacencies": ["Family Living"],
      "door_opens_into": "Family Living",
      "needs_veranda": true,
      "preferred_orientation": "south"
    }
  ],
  "design_explanation": "Two or three short sentences in an architect's voice: why this room list fits the brief, climate, and zoning."
}
Use one of these types per room: bedroom, kitchen, living room, family living, dining, bathroom, corridor, porch, foyer, veranda.
Keep widths and depths as whole or half feet (for example 10, 10.5, 12).
"""


def _build_user_message(plot_width, plot_depth, road_side, num_bedrooms, wishes):
    """Turn the form inputs into one short message for the AI."""
    wishes = (wishes or "").strip() or "No extra wishes."
    return (
        f"Plot: {plot_width} ft wide x {plot_depth} ft deep. "
        f"Road side: {road_side}. "
        f"Bedrooms wanted: {num_bedrooms}. "
        f"Family wishes: {wishes} "
        f"Return the room program JSON now."
    )


def _ask_model(client, system_prompt, user_message):
    """Ask Muse Spark and return the raw JSON text.

    We try the Responses API first (the current default), then fall
    back to Chat Completions if a library only supports that.
    Both calls request structured JSON output so the reply parses.
    """
    # Attempt 1: Responses API with JSON output.
    try:
        response = client.responses.create(
            model=MODEL_NAME,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            text={"format": {"type": "json_object"}},
        )
        return response.output_text
    except Exception:
        # Attempt 2 (fallback): Chat Completions with JSON output.
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


def check_room_sizes(rooms):
    """Check each room against SIZE_RULES in plain Python.

    Returns a list of problem strings. An empty list means all good.
    Checks: both sides inside the type's range, never square
    (sides differ by at least 1 ft). Corridors only need min width.
    Porch, foyer, veranda sizes are not fixed yet, so they are skipped.
    """
    problems = []

    for room in rooms:
        name = room.get("name", "?")
        room_type = str(room.get("type", "")).strip().lower()
        width = room.get("width_ft")
        depth = room.get("depth_ft")

        # Skip types with no fixed sizes yet.
        if room_type in ("porch", "foyer", "veranda"):
            continue

        # Corridor: only check the narrow side (min width).
        if room_type == "corridor":
            if width is None or depth is None:
                problems.append(f"{name}: corridor is missing width or depth.")
                continue
            narrow = min(width, depth)
            if narrow < CORRIDOR_MIN_WIDTH_FT:
                problems.append(
                    f"{name}: corridor is {narrow} ft wide, "
                    f"minimum is {CORRIDOR_MIN_WIDTH_FT} ft."
                )
            continue

        # Unknown type: we cannot check it, so say so plainly.
        if room_type not in SIZE_RULES:
            problems.append(f"{name}: unknown room type '{room_type}', skipped.")
            continue

        # Missing numbers: report instead of crashing.
        if width is None or depth is None:
            problems.append(f"{name}: missing width or depth.")
            continue

        # Both sides must be inside the allowed range.
        low, high = SIZE_RULES[room_type]
        if not (low <= width <= high):
            problems.append(
                f"{name}: width {width} ft is outside {low}-{high} ft."
            )
        if not (low <= depth <= high):
            problems.append(
                f"{name}: depth {depth} ft is outside {low}-{high} ft."
            )

        # Never square: sides must differ by at least 1 ft.
        if abs(width - depth) < 1:
            problems.append(
                f"{name}: {width} x {depth} ft is square-ish; "
                "sides must differ by at least 1 ft."
            )

    return problems


def get_room_program(plot_width, plot_depth, road_side, num_bedrooms, wishes):
    """Send the brief to Muse Spark; return rooms + explanation + size check.

    Returns a dict with three keys:
      "rooms": list of room dicts (name, type, width_ft, depth_ft, ...),
      "design_explanation": short paragraph in an architect's voice,
      "size_problems": list of strings from check_room_sizes().
    """
    # Read the key. The user creates .env themselves; we never ask for it.
    api_key = os.getenv("META_API_KEY")
    if not api_key:
        raise RuntimeError(
            "META_API_KEY is missing. Create a .env file next to app.py "
            "with the line META_API_KEY=your-key-here (see .env.example)."
        )

    # Connect to the Meta Model API (OpenAI-compatible client).
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # Build the brief message and ask the model for JSON.
    user_message = _build_user_message(
        plot_width, plot_depth, road_side, num_bedrooms, wishes
    )
    json_text = _ask_model(client, SYSTEM_PROMPT, user_message)

    # Parse the JSON reply.
    program = json.loads(json_text)
    rooms = program.get("rooms", [])
    explanation = program.get("design_explanation", "")

    # Check sizes in plain Python (no AI): list any problems.
    size_problems = check_room_sizes(rooms)

    return {
        "rooms": rooms,
        "design_explanation": explanation,
        "size_problems": size_problems,
    }
