# ai_program.py
# Step 1 of House Planner: brief -> room program (AI).
#
# What this file does:
#   1. Sends the user's brief to Muse Spark on the Meta Model API.
#   2. Gets back structured JSON: rooms + design explanation.
#   3. Checks room sizes, the toilet rule, and the area budget in plain Python.
#   4. If the program is too big, asks the AI once to shrink rooms to fit.
#
# The API key is read from the META_API_KEY variable (see .env.example).
# The key is NEVER written into any file by this code.

import json
import math
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
# BOTH sides of the room must fall inside this range. Bathrooms are NOT
# here: toilets have per-side ranges (below), so they are checked apart.
SIZE_RULES = {
    "bedroom": (10, 15),
    "kitchen": (8, 15),
    "living room": (12, 15),
    "family living": (12, 15),
    "dining": (10, 14),
}

# Toilet real sizes (architect's own practice, Oct 29): narrow
# (road-parallel) side 4-6 ft, long side 6 ft to 8 ft 6 in. The master
# toilet (attached to the largest bedroom) may be up to 6 ft 6 in wide
# by 10 ft long. Never-square still applies. Toilets are NEVER stretched
# to fill a strip; leftover space becomes wardrobe, store, or open notch.
TOILET_W_RANGE = (4.0, 6.0)
TOILET_D_RANGE = (6.0, 8.5)
MASTER_TOILET_W_RANGE = (4.0, 6.5)
MASTER_TOILET_D_RANGE = (6.0, 10.0)

# Corridors are long and thin: only the narrow side is checked.
CORRIDOR_MIN_WIDTH_FT = 3.5  # 3'-6"

# --- Setbacks and walls (defaults from PROJECT.md) ---
SETBACK_FRONT_FT = 6
SETBACK_SIDE_FT = 1.5
SETBACK_BACK_FT = 4
WALL_EXT_FT = 10 / 12  # 10 in exterior walls
WALL_INT_FT = 5 / 12  # 5 in interior walls

# Rooms where a common toilet door may open (reachable without a bedroom).
COMMON_SPACES = ("dining", "family living", "corridor")


def get_api_key():
    """META_API_KEY from Streamlit secrets first, else the environment.

    st.secrets wins on Streamlit Cloud; the local .env (loaded above)
    wins on a laptop. Returns "" when missing (callers raise a
    friendly error).
    """
    try:
        import streamlit as st
        key = st.secrets.get("META_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass
    return (os.getenv("META_API_KEY") or "").strip()


def format_ft_in(feet):
    """Show a dimension in feet and inches: 14 -> 14'-0", 3.5 -> 3'-6".

    Rounds to the nearest inch. Returns "?" when the number is missing.
    """
    if feet is None:
        return "?"
    try:
        total_inches = int(round(float(feet) * 12))
    except (TypeError, ValueError):
        return "?"
    ft = total_inches // 12
    inch = total_inches % 12
    return f"{ft}'-{inch}\""


def calculate_buildable_area(frontage_ft, depth_ft, road_side):
    """Plot minus setbacks = the rectangle the house must fit inside.

    Inputs are road-relative (frontage = road side), so front (6 ft)
    + back (4 ft) always come off the depth and the side setbacks
    (1.5 ft each) off the frontage. The road side only rotates the
    drawing and sets the real orientation. Returns a dict with width,
    depth, and area in sq ft.
    """
    buildable_width = frontage_ft - SETBACK_SIDE_FT * 2
    buildable_depth = depth_ft - SETBACK_FRONT_FT - SETBACK_BACK_FT
    # A tiny plot can leave nothing (or less); clamp at zero, never negative.
    buildable_width = max(0, buildable_width)
    buildable_depth = max(0, buildable_depth)
    return {
        "width": buildable_width,
        "depth": buildable_depth,
        "area": buildable_width * buildable_depth,
    }


def calculate_program_area(rooms):
    """Add up room areas + wall thickness so we can compare to buildable.

    Simple estimates, explained so a non-programmer can follow:
    - net: sum of every room's width x depth (corridors included).
    - circulation: the corridor part of net (shown for info, not added twice).
    - interior walls: each room adds about one average-length wall, 5 in thick.
    - exterior walls: walls wrap the house; we guess the perimeter by
      pretending the house (net + interior walls) is a square.
    - total: net + interior + exterior. Compare this to buildable area.
    """
    net = 0.0
    circulation = 0.0
    interior = 0.0
    for room in rooms or []:
        width = room.get("width_ft")
        depth = room.get("depth_ft")
        if width is None or depth is None:
            continue
        area = float(width) * float(depth)
        net += area
        room_type = str(room.get("type", "")).strip().lower()
        if room_type == "corridor":
            circulation += area
        # One average side of interior wall (5 in thick) per room.
        interior += ((float(width) + float(depth)) / 2) * WALL_INT_FT
    # Exterior: perimeter of a square with the same area, times 10 in thick.
    footprint = net + interior
    if footprint > 0:
        side = math.sqrt(footprint)
        exterior = 4 * side * WALL_EXT_FT
    else:
        exterior = 0.0
    return {
        "net": net,
        "circulation": circulation,
        "interior_walls": interior,
        "exterior_walls": exterior,
        "total": net + interior + exterior,
    }


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
- bathroom: 4 to 6 ft wide (road-parallel side) by 6 ft to 8 ft 6 in long; the master toilet (attached to the largest bedroom) may be up to 6 ft 6 in by 10 ft
- corridor: at least 3 ft 6 in wide (long and thin is fine)
A room is NEVER square: its two sides must differ by at least 1 ft (corridors exempt).

HARD RULES (follow all of them):
1. Respect the room sizes and the never-square rule above.
2. No central corridor with rooms on both long sides. Use family living as the circulation hub.
3. Corridors are 25% or less of the built area.
4. Kitchen has exactly one inner door, into dining. One extra door to its own veranda is allowed.
5. Every bedroom door opens into family living. Only if there is no shared wall left for a 3 ft door, it may open into dining. NEVER into the living room.
6. Every bedroom has at least 1 window (2 preferred).
7. TOILETS (client enters the count): return EXACTLY that many bathrooms. Exactly 1 is COMMON (door to dining, family living, or corridor; reachable without passing through any bedroom). All others are ATTACHED: master (largest) bedroom first, then next largest bedrooms, one each. 1-bedroom home: the single toilet is common; a 2nd toilet attaches to the master.
8. Bathrooms touch an exterior wall for ventilation. Never on the front (road) wall.
9. Bathroom windows NEVER face the front (road) side.
10. Verandas: up to 2 bedrooms get one veranda each (every bedroom if fewer than 2), plus the kitchen gets one. Verandas never touch each other. Width 3 to 5 ft, length at least 3 ft, never longer than its room's wall.
11. Bedrooms and living spaces need openings on at least 2 different walls (opposite walls preferred, adjacent walls minimum).
12. Doors and windows connect specific rooms/walls (model them, do not just draw boxes).

ZONING (road side inward): porch and foyer first, then living room (public); then dining, kitchen, family living (semi-private); bedrooms at back and sides (private), clustered around family living.

ORIENTATION (tropical monsoon climate): bedrooms and living prefer windows facing south/southeast (breeze); avoid large west-facing openings in bedrooms and living (afternoon heat); kitchen prefers the WEST side.

FEATURES: wishes that are not separate rooms (study nook, outdoor sitting, prayer corner) go in that room's "features" list so they are recorded for the drawing step.

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
      "preferred_orientation": "south",
      "features": []
    },
    {
      "name": "Common Toilet",
      "type": "bathroom",
      "width_ft": 5,
      "depth_ft": 7.5,
      "adjacencies": ["Dining"],
      "door_opens_into": "Dining",
      "needs_veranda": false,
      "preferred_orientation": "north",
      "features": [],
      "bathroom_kind": "common",
      "attached_to": ""
    }
  ],
  "design_explanation": "Two or three short sentences in an architect's voice: why this room list fits the brief, climate, and zoning."
}
Types: bedroom, kitchen, living room, family living, dining, bathroom, corridor, porch, foyer, veranda.
Bathrooms MUST set "bathroom_kind" to "common" or "attached"; attached ones MUST name their bedroom in "attached_to".
Keep widths and depths as whole or half feet (for example 10, 10.5, 12).
Keep the whole program (rooms + walls) inside the buildable area the user message gives you.
"""


def _build_user_message(frontage_ft, depth_ft, road_side, num_bedrooms,
                         num_toilets, wishes, buildable, north_angle=None):
    """Turn the form inputs into one short message for the AI."""
    wishes = (wishes or "").strip() or "No extra wishes."
    if north_angle is None:
        direction = f"Road side: {road_side}. "
    else:
        direction = (f"North direction: {north_angle:g} deg (0 = north "
                     f"points away from the road, clockwise). Road on "
                     f"the {road_side} side. ")
    return (
        f"Plot: {frontage_ft} ft road frontage x {depth_ft} ft deep "
        f"from the road. "
        + direction +
        f"Bedrooms wanted: {num_bedrooms}. "
        f"Toilets wanted: {num_toilets} (exactly 1 common, rest attached). "
        f"Buildable area after setbacks: {buildable['area']:.0f} sq ft "
        f"({buildable['width']:.1f} x {buildable['depth']:.1f} ft). "
        f"Family wishes: {wishes} "
        f"Return the room program JSON now."
    )


def _build_revision_message(program_area, buildable):
    """Short follow-up asking the AI to shrink rooms so the program fits."""
    return (
        f"Your program needs about {program_area['total']:.0f} sq ft "
        f"(rooms + walls) but the buildable area is only "
        f"{buildable['area']:.0f} sq ft. Revise the SAME room list with "
        f"smaller widths/depths that still obey every size rule "
        f"(both sides in range, never square). Return the full JSON again."
    )


def _ask_model(client, system_prompt, messages):
    """Ask Muse Spark and return the raw JSON text.

    We try the Responses API first (the current default), then fall
    back to Chat Completions if a library only supports that.
    Both calls request structured JSON output so the reply parses.
    `messages` is a list of {"role": ..., "content": ...} dicts.
    """
    # Attempt 1: Responses API with JSON output.
    try:
        response = client.responses.create(
            model=MODEL_NAME,
            input=messages,
            text={"format": {"type": "json_object"}},
        )
        return response.output_text
    except Exception:
        # Attempt 2 (fallback): Chat Completions with JSON output.
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": m["role"], "content": m["content"]} for m in messages
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


def _master_bedroom_name(rooms):
    """Name of the largest bedroom by area ("" when none is sized)."""
    best_name, best_area = "", 0.0
    for room in rooms or []:
        if str(room.get("type", "")).strip().lower() != "bedroom":
            continue
        try:
            area = float(room.get("width_ft")) * float(room.get("depth_ft"))
        except (TypeError, ValueError):
            continue
        if area > best_area:
            best_name, best_area = room.get("name", "?"), area
    return best_name


def check_room_sizes(rooms):
    """Check each room against SIZE_RULES in plain Python.

    Returns a list of problem strings. An empty list means all good.
    Checks: both sides inside the type's range, never square
    (sides differ by at least 1 ft). Corridors only need min width.
    Bathrooms use the per-side toilet ranges (master bounds for the
    toilet attached to the largest bedroom). Porch, foyer, veranda
    sizes are not fixed yet, so they are skipped.
    All dimensions are shown in feet and inches.
    """
    problems = []
    master = _master_bedroom_name(rooms)

    for room in rooms:
        name = room.get("name", "?")
        room_type = str(room.get("type", "")).strip().lower()
        width = room.get("width_ft")
        depth = room.get("depth_ft")

        # Skip types with no fixed sizes yet.
        if room_type in ("porch", "foyer", "veranda"):
            continue

        # Bathrooms: per-side toilet ranges + never square.
        if room_type == "bathroom":
            if width is None or depth is None:
                problems.append(f"{name}: missing width or depth.")
                continue
            if master and str(room.get("attached_to", "")).strip() == master:
                w_low, w_high = MASTER_TOILET_W_RANGE
                d_low, d_high = MASTER_TOILET_D_RANGE
                bounds = "master"
            else:
                w_low, w_high = TOILET_W_RANGE
                d_low, d_high = TOILET_D_RANGE
                bounds = "standard"
            if not (w_low <= width <= w_high):
                problems.append(
                    f"{name}: width {format_ft_in(width)} is outside "
                    f"{bounds} toilet {format_ft_in(w_low)}-"
                    f"{format_ft_in(w_high)}."
                )
            if not (d_low <= depth <= d_high):
                problems.append(
                    f"{name}: depth {format_ft_in(depth)} is outside "
                    f"{bounds} toilet {format_ft_in(d_low)}-"
                    f"{format_ft_in(d_high)}."
                )
            if abs(width - depth) < 1:
                problems.append(
                    f"{name}: {format_ft_in(width)} x {format_ft_in(depth)} "
                    "is square-ish; sides must differ by at least 1 ft."
                )
            continue

        # Corridor: only check the narrow side (min width).
        if room_type == "corridor":
            if width is None or depth is None:
                problems.append(f"{name}: corridor is missing width or depth.")
                continue
            narrow = min(width, depth)
            if narrow < CORRIDOR_MIN_WIDTH_FT:
                problems.append(
                    f"{name}: corridor is {format_ft_in(narrow)} wide, "
                    f"minimum is {format_ft_in(CORRIDOR_MIN_WIDTH_FT)}."
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
                f"{name}: width {format_ft_in(width)} is outside "
                f"{format_ft_in(low)}-{format_ft_in(high)}."
            )
        if not (low <= depth <= high):
            problems.append(
                f"{name}: depth {format_ft_in(depth)} is outside "
                f"{format_ft_in(low)}-{format_ft_in(high)}."
            )

        # Never square: sides must differ by at least 1 ft.
        if abs(width - depth) < 1:
            problems.append(
                f"{name}: {format_ft_in(width)} x {format_ft_in(depth)} "
                "is square-ish; sides must differ by at least 1 ft."
            )

    return problems


def check_toilets(rooms, num_toilets):
    """Check the new toilet rule in plain Python (HARD rule).

    Rule: EXACTLY num_toilets bathrooms; exactly 1 is COMMON (door to
    dining/family living/corridor); the rest are ATTACHED, master
    (largest) bedroom first, then next largest, one each.
    Returns a list of problem strings; empty means the rule passes.
    """
    problems = []
    bathrooms = [
        r for r in (rooms or [])
        if str(r.get("type", "")).strip().lower() == "bathroom"
    ]
    bedrooms = [
        r for r in (rooms or [])
        if str(r.get("type", "")).strip().lower() == "bedroom"
    ]

    # Count must match what the client entered.
    if len(bathrooms) != num_toilets:
        problems.append(
            f"Toilet count: wanted {num_toilets}, program has {len(bathrooms)}."
        )

    # Split into common vs attached by the AI's bathroom_kind label.
    common = [
        b for b in bathrooms
        if str(b.get("bathroom_kind", "")).strip().lower() == "common"
    ]
    attached = [
        b for b in bathrooms
        if str(b.get("bathroom_kind", "")).strip().lower() == "attached"
    ]
    unlabeled = [b for b in bathrooms if b not in common and b not in attached]
    for bath in unlabeled:
        problems.append(
            f"{bath.get('name', '?')}: set bathroom_kind to "
            "'common' or 'attached'."
        )

    # Exactly 1 common toilet, with a door to common space.
    if len(common) != 1:
        problems.append(
            f"Common toilets: wanted exactly 1, program has {len(common)}."
        )
    for bath in common:
        door = str(bath.get("door_opens_into", "")).strip().lower()
        if door not in COMMON_SPACES:
            problems.append(
                f"{bath.get('name', '?')}: common toilet door opens into "
                f"'{bath.get('door_opens_into', '?')}'; must open into "
                "dining, family living, or corridor."
            )

    # Attached toilets: master first, then next largest bedrooms.
    # Master = largest bedroom by area (width x depth).
    def _area(room):
        try:
            return float(room.get("width_ft", 0)) * float(room.get("depth_ft", 0))
        except (TypeError, ValueError):
            return 0

    bedrooms_by_size = sorted(bedrooms, key=_area, reverse=True)
    expected = [b.get("name", "") for b in bedrooms_by_size[:max(0, num_toilets - 1)]]
    seen = []
    for bath in attached:
        target = str(bath.get("attached_to", "")).strip()
        if not target:
            problems.append(
                f"{bath.get('name', '?')}: attached toilet must name "
                "its bedroom in 'attached_to'."
            )
            continue
        if target in seen:
            problems.append(
                f"{bath.get('name', '?')}: bedroom '{target}' already "
                "has an attached toilet."
            )
        seen.append(target)
        if target not in expected:
            problems.append(
                f"{bath.get('name', '?')}: attached to '{target}'; "
                f"expected attached bedrooms in order: {', '.join(expected) or 'none'}."
            )
    # Every expected bedroom should have exactly one attached toilet.
    for name in expected:
        if name not in seen:
            problems.append(
                f"Bedroom '{name}' should have an attached toilet (largest-first order)."
            )

    return problems


def get_room_program(frontage_ft, depth_ft, road_side, num_bedrooms,
                     num_toilets, wishes, north_angle=None):
    """Send the brief to Muse Spark; return rooms + checks + area budget.

    Returns a dict with:
      "rooms": list of room dicts (name, type, width_ft, depth_ft,
        adjacencies, door_opens_into, needs_veranda,
        preferred_orientation, features, + bathroom_kind/attached_to
        for bathrooms),
      "design_explanation": short paragraph in an architect's voice,
      "size_problems": list from check_room_sizes(),
      "toilet_problems": list from check_toilets(),
      "buildable": dict from calculate_buildable_area(),
      "program_area": dict from calculate_program_area(),
      "revised": True if we asked the AI to shrink rooms to fit,
      "area_warning": "" when it fits, else a clear warning string.
    """
    # Read the key. The user creates .env themselves; we never ask for it.
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "META_API_KEY is missing. On Streamlit Cloud add it under "
            "Settings > Secrets; on your laptop create a .env file next "
            "to app.py with META_API_KEY=your-key-here (see .env.example)."
        )

    # Connect to the Meta Model API (OpenAI-compatible client).
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # Buildable area first, so the AI knows its budget.
    buildable = calculate_buildable_area(frontage_ft, depth_ft, road_side)

    # First ask: full brief -> room program JSON.
    user_message = _build_user_message(
        frontage_ft, depth_ft, road_side, num_bedrooms,
        num_toilets, wishes, buildable, north_angle
    )
    program = json.loads(_ask_model(client, SYSTEM_PROMPT, [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]))
    rooms = program.get("rooms", [])
    explanation = program.get("design_explanation", "")
    program_area = calculate_program_area(rooms)
    revised = False

    # Area budget: if too big, ask once to shrink within the size rules.
    if program_area["total"] > buildable["area"]:
        revised = True
        program = json.loads(_ask_model(client, SYSTEM_PROMPT, [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": json.dumps(program)},
            {"role": "user", "content": _build_revision_message(program_area, buildable)},
        ]))
        rooms = program.get("rooms", [])
        explanation = program.get("design_explanation", "")
        program_area = calculate_program_area(rooms)

    # Clear warning when it still cannot fit.
    area_warning = ""
    if program_area["total"] > buildable["area"]:
        over = program_area["total"] - buildable["area"]
        area_warning = (
            f"Your rooms need about {program_area['total']:.0f} sq ft "
            f"(rooms + walls) but the buildable area is only "
            f"{buildable['area']:.0f} sq ft -- over by {over:.0f} sq ft "
            f"even after shrinking. Try fewer rooms or a bigger plot."
        )

    # Plain-Python checks (no AI): sizes + toilet rule.
    size_problems = check_room_sizes(rooms)
    toilet_problems = check_toilets(rooms, num_toilets)

    return {
        "rooms": rooms,
        "design_explanation": explanation,
        "size_problems": size_problems,
        "toilet_problems": toilet_problems,
        "buildable": buildable,
        "program_area": program_area,
        "revised": revised,
        "area_warning": area_warning,
    }
