# layout.py
# Step 2 of House Planner: shared geometry + strict rule checker (plain Python).
#
# What this file does (placement lives in typology.py, which imports from here):
#   1. Buckets the room program by role, builds placed-rectangle dicts, and
#      adds the porch + verandas to any placed plan.
#   2. Checks a placed plan against the hard rules 1-12, geometry row G, the
#      strict livability rules 13-17, toilet real sizes (18), and the soft
#      design goals, reporting PASS / BEND / FAIL / PENDING for each
#      (door/window rules stay PENDING until Day 3, when doors and windows
#      are modeled).
#   3. Scores an option for ranking, and gives the LIVABLE/UNLIVABLE verdict
#      (UNLIVABLE iff rules 7, 13-16 or geometry G fail; rule 17 never
#      flips it).
#
# Local frame (everything is placed here, the drawing rotates it later):
#   - x runs parallel to the road, from the viewer's left (standing at the
#     road looking at the house). y runs from the road inward (y = 0 at the
#     buildable front edge). All sizes in feet.
#   - Rooms may stretch or shrink within their size rules; family living and
#     living room may use their relaxed absolute limits (bend + note).
#   - Wardrobe/store filler beside side-strip baths is leftover space, not a
#     room: exempt from size rules and circulation.
#
# NOTE (Day 2, proposed defaults, architect to confirm): foyer 6-12 ft per
# side, porch 6-12 ft wide x 4-6 ft deep, veranda projection 3-5 ft.
# Porch/veranda are outdoor projections, so like corridors they are exempt
# from the never-square rule.

import math

from ai_program import (
    CORRIDOR_MIN_WIDTH_FT,
    MASTER_TOILET_D_RANGE,
    MASTER_TOILET_W_RANGE,
    SIZE_RULES,
    TOILET_D_RANGE,
    TOILET_W_RANGE,
    format_ft_in,
)

# --- Proposed size defaults (Day 2, architect to confirm, see note above) ---
FOYER_MIN_FT = 6
FOYER_MAX_FT = 12
PORCH_MIN_W_FT = 6
PORCH_MAX_W_FT = 12
PORCH_MIN_D_FT = 4
PORCH_MAX_D_FT = 6
VERANDA_PROJ_MIN_FT = 3  # how far the veranda sticks out from the wall
VERANDA_PROJ_MAX_FT = 5
VERANDA_MIN_LEN_FT = 3

# Relaxed absolute limits (preferred PROJECT.md ranges stay; a room sized
# inside its relaxed range but outside preferred BENDS rule 1, -2 each).
RELAXED_RANGES = {"family living": (10, 15), "living room": (12, 17)}

# Tiny tolerance for float comparisons.
EPS = 1e-6

# North direction (degrees clockwise from "north away from the road"):
# 0 = road South, 90 = road East, 180 = road North, 270 = road West.
# Angled plots use any value; orientation picks the closest plot side.
NORTH_ANGLE = {"south": 0.0, "east": 90.0, "north": 180.0, "west": 270.0}

# Local sides, tie-break order for closest-side picks (strips first).
SIDE_ORDER = ("lowx", "highx", "front", "back")

# Short labels for tiny rooms in the drawing.
SHORT_NAMES = {
    "bathroom": "Bath",
    "family living": "Family",
    "living room": "Living",
    "dining": "Dining",
    "kitchen": "Kitchen",
    "bedroom": "Bed",
    "foyer": "Foyer",
    "porch": "Porch",
    "veranda": "Ver",
}


def _room_type(room):
    """Lower-cased room type, '' when missing."""
    return str(room.get("type", "")).strip().lower()


def _room_area(room):
    """Width x depth, 0 when numbers are missing."""
    try:
        return float(room.get("width_ft", 0)) * float(room.get("depth_ft", 0))
    except (TypeError, ValueError):
        return 0


def _type_range(room_type):
    """Allowed (min, max) side in ft for row rooms. None for outdoor rooms."""
    if room_type in SIZE_RULES:
        return SIZE_RULES[room_type]
    if room_type == "foyer":
        return (FOYER_MIN_FT, FOYER_MAX_FT)
    return None


def _pref(room, key, room_type):
    """Preferred width/depth from the AI, or the middle of the size range."""
    try:
        value = float(room.get(key, 0))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    known = _type_range(room_type)
    if known:
        return (known[0] + known[1]) / 2
    return 8.0


def _clamp(value, low, high):
    """Force value inside [low, high]."""
    return max(low, min(high, value))


def _fill_widths(items, target, relax=False):
    """Spread `target` width over cells, each inside its [lo, hi] range.

    items: list of dicts {lo, hi, pref}. Starts from preferred widths, then
    grows/shrinks rooms proportionally to their spare room until the row sums
    exactly to `target` (no gaps). Returns the width list, or None when the
    target cannot be met. With relax=True (last-resort tiny plots) the target
    is clamped and ranges widened 30% so we still return a best attempt.
    """
    los = [it["lo"] for it in items]
    his = [it["hi"] for it in items]
    if relax:
        los = [lo - (hi - lo) * 0.3 for lo, hi in zip(los, his)]
        his = [hi + (hi - lo) * 0.3 for lo, hi in zip(
            [it["lo"] for it in items], [it["hi"] for it in items])]
        target = _clamp(target, sum(los), sum(his))
    if target < sum(los) - EPS or target > sum(his) + EPS:
        return None
    widths = [_clamp(it["pref"], lo, hi)
              for it, lo, hi in zip(items, los, his)]
    diff = target - sum(widths)
    for _ in range(100):
        if abs(diff) < 0.001:
            break
        if diff > 0:
            # Grow rooms that still have headroom, proportionally.
            spare = [max(0.0, hi - w) for w, hi in zip(widths, his)]
        else:
            # Shrink rooms that still have slack, proportionally.
            spare = [max(0.0, w - lo) for w, lo in zip(widths, los)]
        total = sum(spare)
        if total <= EPS:
            return None
        for i in range(len(widths)):
            step = diff * spare[i] / total
            widths[i] += step
            diff -= step
    if abs(target - sum(widths)) > 0.01:
        return None
    return widths


def _branch_fill(boxes, target, depth, _level=0):
    """Water-fill that branches around the never-square rule.

    boxes: [(lo, hi, pref)] per room. Fills to `target`, then picks the
    first square-ish room and tries both legal sides (<= depth-1 and
    >= depth+1), recursing. Returns widths or None. Best-first: the plain
    fill is tried before any branch, branches nearer the preference first.
    """
    if _level > len(boxes) + 1:
        return None
    widths = _fill_widths([{"lo": lo, "hi": hi, "pref": pref}
                           for lo, hi, pref in boxes], target)
    if widths is None:
        return None
    for i, width in enumerate(widths):
        if abs(width - depth) < 1 - EPS:
            lo, hi, pref = boxes[i]
            branches = []
            if lo <= depth - 1 + EPS and lo <= min(hi, depth - 1) + EPS:
                branches.append((lo, min(hi, depth - 1)))
            if max(lo, depth + 1) - EPS <= hi:
                branches.append((max(lo, depth + 1), hi))
            branches.sort(key=lambda side: abs((side[0] + side[1]) / 2 - pref))
            for branch_lo, branch_hi in branches:
                narrowed = list(boxes)
                narrowed[i] = (branch_lo, branch_hi, pref)
                got = _branch_fill(narrowed, target, depth, _level + 1)
                if got is not None:
                    return got
            return None
    return widths


def _round_half(widths, boxes, depth, target):
    """Round room widths to half feet, preserving their sum.

    Half-foot dimensions build better (and match the AI prompt's prefs).
    Largest-remainder keeps the row total exact. Returns the rounded list,
    or None when rounding would break a range or the never-square rule
    (the caller then keeps the unrounded widths).
    """
    floors = [math.floor(width * 2) / 2 for width in widths]
    remainders = [width - floor for width, floor in zip(widths, floors)]
    short = int(round((target - sum(floors)) * 2))
    if short < 0 or short > len(widths):
        return None
    order = sorted(range(len(widths)), key=lambda i: remainders[i],
                   reverse=True)
    rounded = list(floors)
    for i in order[:short]:
        rounded[i] += 0.5
    if abs(sum(rounded) - target) > 0.01:
        return None
    for width, (low, high, _pref) in zip(rounded, boxes):
        if not low - EPS <= width <= high + EPS:
            return None
        if abs(width - depth) < 1 - EPS:
            return None
    return rounded


def _as_rect(room, x, y, width, depth):
    """One placed room: geometry plus the program facts the checker needs."""
    return {
        "name": room.get("name", "?"),
        "type": _room_type(room),
        "x": x, "y": y, "w": width, "d": depth,
        "bathroom_kind": str(room.get("bathroom_kind", "")).strip().lower(),
        "attached_to": str(room.get("attached_to", "")).strip(),
        "needs_veranda": bool(room.get("needs_veranda")),
    }


# --- Small geometry helpers (all in the local frame) ---

def _overlap_1d(a0, a1, b0, b1):
    """Overlap length of two 1D segments, 0 when they just miss."""
    return max(0.0, min(a1, b1) - max(a0, b0))


def shared_wall(a, b):
    """Shared wall length (ft) of two room rects, 0 when not adjacent.

    Two rooms share a wall when one edge touches and the overlap along that
    edge is positive. A 3 ft door needs at least 3 ft of shared wall.
    """
    a_x1, a_y1 = a["x"] + a["w"], a["y"] + a["d"]
    b_x1, b_y1 = b["x"] + b["w"], b["y"] + b["d"]
    if abs(a_x1 - b["x"]) < 0.01 or abs(b_x1 - a["x"]) < 0.01:
        return _overlap_1d(a["y"], a_y1, b["y"], b_y1)
    if abs(a_y1 - b["y"]) < 0.01 or abs(b_y1 - a["y"]) < 0.01:
        return _overlap_1d(a["x"], a_x1, b["x"], b_x1)
    return 0.0


def _area_overlap(a, b):
    """Overlapping floor area of two rects (0 when they just touch)."""
    return (_overlap_1d(a["x"], a["x"] + a["w"], b["x"], b["x"] + b["w"])
            * _overlap_1d(a["y"], a["y"] + a["d"], b["y"], b["y"] + b["d"]))


def _rects_touch(a, b, gap=0.0):
    """True when two rects overlap or come within `gap` ft (even at corners)."""
    return (
        a["x"] < b["x"] + b["w"] + gap and b["x"] < a["x"] + a["w"] + gap
        and a["y"] < b["y"] + b["d"] + gap and b["y"] < a["y"] + a["d"] + gap
    )


def _exterior_walls(rect, others):
    """Which of the 4 walls face outside: dict wall -> exterior length (ft).

    Walls are "W" (low x), "E" (high x), "S" (low y, road side), "N" (high y,
    back side). A wall is exterior where no other room covers it.
    """
    walls = {"W": rect["d"], "E": rect["d"], "S": rect["w"], "N": rect["w"]}
    for other in others:
        if other is rect:
            continue
        if _area_overlap(rect, other) > EPS:
            continue  # overlapping rooms share no clean wall; checker flags it
        walls["W"] -= _wall_cover(rect, other, "W")
        walls["E"] -= _wall_cover(rect, other, "E")
        walls["S"] -= _wall_cover(rect, other, "S")
        walls["N"] -= _wall_cover(rect, other, "N")
    return {wall: max(0.0, length) for wall, length in walls.items()}


def _wall_cover(rect, other, wall):
    """How much of `rect`'s `wall` is covered by `other` (ft)."""
    x0, y0, x1, y1 = rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["d"]
    o_x0, o_y0 = other["x"], other["y"]
    o_x1, o_y1 = o_x0 + other["w"], o_y0 + other["d"]
    if wall == "W" and abs(o_x1 - x0) < 0.01:
        return _overlap_1d(y0, y1, o_y0, o_y1)
    if wall == "E" and abs(o_x0 - x1) < 0.01:
        return _overlap_1d(y0, y1, o_y0, o_y1)
    if wall == "S" and abs(o_y1 - y0) < 0.01:
        return _overlap_1d(x0, x1, o_x0, o_x1)
    if wall == "N" and abs(o_y0 - y1) < 0.01:
        return _overlap_1d(x0, x1, o_x0, o_x1)
    return 0.0


# --- Program sorting: which rooms go in which band ---

def _buckets(program_rooms):
    """Sort the AI program into bands; note rooms the placer skips.

    Returns (buckets, notes). Corridors are skipped on purpose (family
    living is the circulation hub, so no corridor is needed); veranda-type
    rooms are skipped because verandas are generated from `needs_veranda`
    flags instead (the AI's veranda entries name no parent room).
    """
    buckets = {"foyer": [], "living": [], "kitchen": [], "dining": [],
               "family": [], "bedrooms": [], "bathrooms": [], "porch": []}
    notes = []
    for room in program_rooms or []:
        kind = _room_type(room)
        if kind == "corridor":
            notes.append("Corridor '%s' from the program was not placed: "
                         "family living is the circulation hub." % room.get("name", "?"))
        elif kind == "veranda":
            notes.append("Veranda '%s' from the program was rebuilt from "
                         "needs_veranda flags instead." % room.get("name", "?"))
        elif kind == "foyer":
            buckets["foyer"].append(room)
        elif kind == "living room":
            buckets["living"].append(room)
        elif kind == "kitchen":
            buckets["kitchen"].append(room)
        elif kind == "dining":
            buckets["dining"].append(room)
        elif kind == "family living":
            buckets["family"].append(room)
        elif kind == "bedroom":
            buckets["bedrooms"].append(room)
        elif kind == "bathroom":
            buckets["bathrooms"].append(room)
        elif kind == "porch":
            buckets["porch"].append(room)
        else:
            notes.append("Room '%s' has unknown type '%s' and was skipped."
                         % (room.get("name", "?"), kind))
    # One room per role; extras are noted and skipped.
    for key in ("foyer", "living", "kitchen", "dining", "family", "porch"):
        if len(buckets[key]) > 1:
            extras = ", ".join(r.get("name", "?") for r in buckets[key][1:])
            notes.append("Extra %s room(s) skipped (%s); the plan places one."
                         % (key, extras))
            buckets[key] = buckets[key][:1]
    buckets["bedrooms"].sort(key=_room_area, reverse=True)
    return buckets, notes


def _porch_size(program_porch):
    """Porch width/depth: AI size clamped to the proposed range, else 8x5."""
    width, depth = 8.0, 5.0
    if program_porch:
        try:
            width = _clamp(float(program_porch.get("width_ft", width)),
                           PORCH_MIN_W_FT, PORCH_MAX_W_FT)
        except (TypeError, ValueError):
            pass
        try:
            depth = _clamp(float(program_porch.get("depth_ft", depth)),
                           PORCH_MIN_D_FT, PORCH_MAX_D_FT)
        except (TypeError, ValueError):
            pass
    return width, depth


def _add_porch(rects, buckets, build_w, notes, auto):
    """Stick the porch on the foyer's road-side wall (or living room's).

    Returns the porch depth reserved in front of the house (0 when skipped).
    The porch lives in the front margin, inside the buildable area.
    """
    host = None
    for rect in rects:
        if rect["type"] == "foyer":
            host = rect
            break
    if host is None:
        for rect in rects:
            if rect["type"] == "living room":
                host = rect
                break
    if host is None:
        notes.append("Porch skipped: no foyer or living room to attach to.")
        return 0.0
    width, depth = _porch_size(buckets["porch"][0] if buckets["porch"] else None)
    width = min(width, host["w"])
    x = _clamp(host["x"] + (host["w"] - width) / 2, 0.0, build_w - width)
    y = host["y"] - depth
    if y < -EPS:
        notes.append("Porch skipped: no room left in the front margin.")
        return 0.0
    rects.append({"name": "Porch", "type": "porch", "x": x, "y": max(0.0, y),
                  "w": width, "d": depth, "bathroom_kind": "",
                  "attached_to": "", "needs_veranda": False})
    if auto:
        notes.append("Porch auto-added in front of the %s (entry goal)."
                     % host["type"])
    return depth


def _exterior_segments(rect, others, wall):
    """Exterior runs along one wall: list of (start, end) in wall coords."""
    full = rect["d"] if wall in ("W", "E") else rect["w"]
    covered = []
    x0, y0 = rect["x"], rect["y"]
    x1, y1 = x0 + rect["w"], y0 + rect["d"]
    for other in others:
        if other is rect or _area_overlap(rect, other) > EPS:
            continue
        o_x0, o_y0 = other["x"], other["y"]
        o_x1, o_y1 = o_x0 + other["w"], o_y0 + other["d"]
        if wall == "W" and abs(o_x1 - x0) < 0.01:
            covered.append((o_y0 - y0, o_y1 - y0))
        elif wall == "E" and abs(o_x0 - x1) < 0.01:
            covered.append((o_y0 - y0, o_y1 - y0))
        elif wall == "S" and abs(o_y1 - y0) < 0.01:
            covered.append((o_x0 - x0, o_x1 - x0))
        elif wall == "N" and abs(o_y0 - y1) < 0.01:
            covered.append((o_x0 - x0, o_x1 - x0))
    covered.sort()
    segments, cursor = [], 0.0
    for start, end in covered:
        if start > cursor + EPS:
            segments.append((cursor, min(start, full)))
        cursor = max(cursor, end)
    if cursor < full - EPS:
        segments.append((cursor, full))
    return [(s, e) for s, e in segments if e - s > EPS]


def _veranda_targets(buckets, rects, notes, wall_first=None):
    """Which rooms get a veranda: flags say, capped at 2 bedrooms + kitchen.

    `needs_veranda` flags come from the AI. When nothing is flagged at all,
    the two largest bedrooms + kitchen are veranda'd automatically (rule 10).
    wall_first ({room name: wall}) tries a facing-wished wall before the
    default order. Returns [(room_rect, wall_order), ...].
    """
    beds = [r for r in rects if r["type"] == "bedroom"]
    flagged_beds = [r for r in beds if r["needs_veranda"]][:2]
    kitchens = [r for r in rects if r["type"] == "kitchen"]
    flagged_kitchen = [r for r in kitchens if r["needs_veranda"]]
    if not flagged_beds and not flagged_kitchen and (beds or kitchens):
        flagged_beds = sorted(beds, key=lambda r: r["w"] * r["d"],
                              reverse=True)[:2]
        flagged_kitchen = kitchens[:1]
        if flagged_beds or flagged_kitchen:
            notes.append("Verandas auto-added (2 largest bedrooms + kitchen); "
                         "the program flagged none.")
    targets = []
    for room in flagged_beds:
        order = ["W", "E", "N", "S"]
        first = (wall_first or {}).get(room["name"])
        if first in order:
            order.remove(first)
            order.insert(0, first)
        targets.append((_by_name(rects, room["name"]), order))
    targets += [(_by_name(rects, r["name"]), ["W", "E", "N", "S"])
                for r in flagged_kitchen]
    return [(room, walls) for room, walls in targets if room is not None]


def _by_name(rects, name):
    """Find a placed rect by room name (None when missing)."""
    for rect in rects:
        if rect["name"] == name:
            return rect
    return None


def _add_verandas(rects, targets, build_w, build_d, notes):
    """Attach one separate veranda to each target room's outside wall.

    Each veranda projects 3-5 ft out, spans at least 3 ft of exterior wall,
    stays inside the buildable area, and never touches another veranda.
    Walls are tried in order; the first fit wins. Returns veranda rects.
    """
    verandas = []
    for room, wall_order in targets:
        placed = None
        for wall in wall_order:
            for start, end in _exterior_segments(room, rects, wall):
                seg_len = end - start
                if seg_len < VERANDA_MIN_LEN_FT - EPS:
                    continue
                length = min(seg_len, 8.0)
                # Slide along long walls: start, far end, then middle.
                starts = [start]
                if seg_len - length > 0.25:
                    starts.append(end - length)
                    middle = (start + end - length) / 2
                    if min(abs(middle - s) for s in starts) > 0.25:
                        starts.append(middle)
                for pos in starts:
                    seg = (pos, pos + length)
                    for proj in (4.0, 3.0):
                        cand = _veranda_rect(room, wall, seg, proj)
                        if cand["x"] < -EPS or cand["y"] < -EPS:
                            continue
                        if cand["x"] + cand["w"] > build_w + EPS:
                            continue
                        if cand["y"] + cand["d"] > build_d + EPS:
                            continue
                        if any(_area_overlap(cand, other) > EPS for other in rects):
                            continue
                        if any(_rects_touch(cand, other, gap=0.0)
                               for other in verandas):
                            continue
                        placed = cand
                        break
                    if placed is not None:
                        break
                if placed is not None:
                    break
            if placed is not None:
                break
        if placed is None:
            notes.append("No separate veranda spot found for %s "
                         "(its flag stays unfulfilled; the checker decides "
                         "pass/fail)." % room["name"])
            continue
        placed["name"] = "%s veranda" % room["name"]
        placed["veranda_for"] = room["name"]
        rects.append(placed)
        verandas.append(placed)
    return verandas


def _veranda_rect(room, wall, segment, proj):
    """Veranda rectangle projecting `proj` ft out from a wall segment."""
    start, end = segment
    if wall == "W":
        return {"name": "", "type": "veranda", "x": room["x"] - proj,
                "y": room["y"] + start, "w": proj, "d": end - start,
                "bathroom_kind": "", "attached_to": "", "needs_veranda": False}
    if wall == "E":
        return {"name": "", "type": "veranda", "x": room["x"] + room["w"],
                "y": room["y"] + start, "w": proj, "d": end - start,
                "bathroom_kind": "", "attached_to": "", "needs_veranda": False}
    if wall == "S":
        return {"name": "", "type": "veranda", "x": room["x"] + start,
                "y": room["y"] - proj, "w": end - start, "d": proj,
                "bathroom_kind": "", "attached_to": "", "needs_veranda": False}
    return {"name": "", "type": "veranda", "x": room["x"] + start,
            "y": room["y"] + room["d"], "w": end - start, "d": proj,
            "bathroom_kind": "", "attached_to": "", "needs_veranda": False}


# --- Livability helpers (strict Day-2 checks; 13-16 + G decide the verdict) ---

# Hard-rule ids that decide the UNLIVABLE verdict: bedroom doors (5),
# toilets (7), the strict livability checks (13-16), master size (19).
# Geometry G joins them (see verdict).
LIVABILITY_IDS = ("5", "7", "13", "14", "15", "16", "19")

# Kitchen needs this much continuous exterior wall (ventilation opening
# plus the veranda door share it). Architect to confirm the 6 ft bar:
# the demo plan's kitchen has only a 3.5 ft notch wall.
KITCHEN_MIN_EXTERIOR_FT = 6

# Bedrooms need this much continuous exterior wall for a window.
BEDROOM_MIN_WINDOW_FT = 6

# Rooms wide enough to count as one cross-ventilation side.
VENT_SIDE_FT = 3

# Only these rooms may sit in the middle of a circulation route.
CIRCULATION_ROOMS = ("foyer", "living room", "dining", "family living")

# Two rects count as neighbours (a door could join them) past this
# much shared wall. Door-sized (3 ft) refinement arrives with Day 3.
NEIGHBOUR_FT = 0.5


def livability_verdict(rules):
    """(livable, failed_ids) from finished rule rows.

    UNLIVABLE iff any of rules 5, 7, 13-16, 19 FAIL, or the geometry
    row G FAILS (rooms outside the plot are unbuildable, hence unlivable).
    Rule 17 (cross-ventilation walls) is reported only and never flips
    the verdict.
    """
    failed = [row["id"] for row in rules
              if row["id"] in LIVABILITY_IDS and row["status"] == "FAIL"]
    if any(row["id"] == "G" and row["status"] == "FAIL" for row in rules):
        failed = ["G"] + failed
    return (not failed, failed)


def _normalize_angle(value):
    """North direction in [0, 360): number as-is, cardinal word mapped."""
    try:
        return float(value) % 360.0
    except (TypeError, ValueError):
        return NORTH_ANGLE.get(str(value or "").strip().lower(), 0.0)


def _resolve_angle(road_side, north_angle):
    """Explicit angle wins, else the road side's cardinal angle."""
    if north_angle is None:
        return _normalize_angle(road_side)
    return _normalize_angle(north_angle)


def _side_bearings(north_angle):
    """Compass bearing of each local side (front = road side)."""
    theta = _normalize_angle(north_angle)
    return {"lowx": (270.0 - theta) % 360.0,
            "highx": (90.0 - theta) % 360.0,
            "front": (180.0 - theta) % 360.0,
            "back": (0.0 - theta) % 360.0}


def _angular_dist(first, second):
    """Smallest angle between two bearings (0-180)."""
    return min((first - second) % 360.0, (second - first) % 360.0)


def _closest_side(north_angle, bearing):
    """Local side closest to a compass bearing (ties: strips first)."""
    bearings = _side_bearings(north_angle)
    return min(SIDE_ORDER,
               key=lambda side: (_angular_dist(bearings[side], bearing),
                                 SIDE_ORDER.index(side)))


def _bearing_name(bearing):
    """Closest cardinal name (N/E/S/W) for a bearing."""
    names = ((0.0, "North"), (90.0, "East"), (180.0, "South"),
             (270.0, "West"))
    return min(names, key=lambda item: (_angular_dist(item[0], bearing),
                                        item[0]))[1]


def _closest_road(north_angle):
    """Road side word (north/south/east/west) for a north angle."""
    return _bearing_name(
        _side_bearings(north_angle)["front"]).lower()


def _compass_west_wall(north_angle):
    """Local wall facing compass west (closest side to 270)."""
    return {"lowx": "W", "highx": "E", "front": "S", "back": "N"}[
        _closest_side(north_angle, 270.0)]


def _room_blockers(rects, rect):
    """Rects that block `rect`'s walls: toilets and rooms, never outdoor.

    Porch/verandas/gardens are outdoor space, so a wall facing them
    (including the room's own veranda) still counts as exterior.
    """
    return [other for other in rects
            if other is not rect
            and other["type"] not in ("porch", "veranda", "garden")]


def _wall_runs(rect, rects):
    """Exterior runs per wall: {"W": [(s, e)], ...} in wall coords."""
    blockers = _room_blockers(rects, rect)
    return {wall: _exterior_segments(rect, blockers, wall)
            for wall in ("W", "E", "S", "N")}


def _longest_run(runs):
    """(length, wall) of the longest exterior run, (0, "-") when none."""
    best, wall = 0.0, "-"
    for side, segments in runs.items():
        for start, end in segments:
            if end - start > best:
                best, wall = end - start, side
    return best, wall


def _neighbours(rect, rects):
    """Room names sharing a real wall with `rect` (not a corner graze)."""
    return sorted(other["name"] for other in rects
                  if other is not rect and shared_wall(rect, other) > NEIGHBOUR_FT)


def _find_route(rects, start_name, goal_name, allowed_types):
    """Shortest route (room names) with allowed middles, or None.

    Start and goal rooms are exempt (you begin in a bedroom, end in a
    toilet); every room between must be in `allowed_types`. Indoor rooms
    only: porch/verandas can never be pass-through space.
    """
    indoor = [r for r in rects if r["type"] not in ("porch", "veranda")]
    by_name = {r["name"]: r for r in indoor}
    if start_name not in by_name or goal_name not in by_name:
        return None
    queue, seen = [[start_name]], {start_name}
    while queue:
        path = queue.pop(0)
        if path[-1] == goal_name:
            return path
        for nxt in _neighbours(by_name[path[-1]], indoor):
            if nxt in seen:
                continue
            if nxt != goal_name and by_name[nxt]["type"] not in allowed_types:
                continue
            seen.add(nxt)
            queue.append(path + [nxt])
    return None


def _route_crosses(path, rects):
    """First forbidden room type on a path's middle, "" when clean."""
    by_name = {r["name"]: r for r in rects}
    for name in path[1:-1]:
        kind = by_name[name]["type"]
        if kind not in CIRCULATION_ROOMS:
            return kind
    return ""


# --- Rule checker: all 12 hard rules + geometry + design goals ---

def _check_all(rects, info, build_w, build_d, road_side, num_toilets,
               north_angle=None):
    """Check one placed plan. Returns (rules, goals, quality).

    rules: [{id, name, status, detail}] with status PASS/BEND/FAIL/PENDING.
    BEND = requirement softened with a score penalty (relaxed size, missed
    preference); FAIL on rules 13-16 marks the plan UNLIVABLE.
    Door/window rules are PENDING until Day 3 but already report the useful
    adjacency facts. goals: [{name, status, detail}] (MET/MISSED/N/A).
    quality: small dict of tiebreak facts for the scorer.
    """
    rules = []
    baths = [r for r in rects if r["type"] == "bathroom"]
    beds = [r for r in rects if r["type"] == "bedroom"]
    verandas = [r for r in rects if r["type"] == "veranda"]

    # Rule 1: room sizes + never square (relaxed sizes bend, never fail).
    size_problems, size_bends = [], []
    for rect in rects:
        problems, bends = _check_room_size(rect, rects)
        size_problems.extend(problems)
        size_bends.extend(bends)
    relaxed_rooms = sorted({name for name, _text in size_bends})
    bend_texts = [text for _name, text in size_bends]
    status = "FAIL" if size_problems else ("BEND" if bend_texts else "PASS")
    detail = ("; ".join(size_problems + bend_texts) if size_problems
              else "; ".join(bend_texts) if bend_texts
              else "all %d rooms in range, none square" % len(rects))
    rules.append(_rule("1", "Room sizes + never square", status, detail))

    # Rules 2+3: corridors (the placer builds none; family living is the hub).
    corridors = [r for r in rects if r["type"] == "corridor"]
    rules.append(_rule("2", "No central corridor",
                       "PASS" if not corridors else "FAIL",
                       "no corridors in plan (family living is the hub)"
                       if not corridors else "corridor placed, check needed"))
    rules.append(_rule("3", "Corridors <= 25% of built area",
                       "PASS" if not corridors else "FAIL",
                       "corridor area 0 sq ft"
                       if not corridors else "corridor area present"))

    # Rule 4: kitchen door (PENDING doors, but adjacency is checkable now).
    kitchens = [r for r in rects if r["type"] == "kitchen"]
    dinings = [r for r in rects if r["type"] == "dining"]
    if kitchens and dinings:
        touch = max(shared_wall(k, d) for k in kitchens for d in dinings)
        detail = ("touches dining (%.1f ft shared, door possible)"
                  % touch if touch >= 1 else "does NOT touch dining (door impossible)")
    elif not kitchens:
        detail = "no kitchen in plan"
    else:
        detail = "no dining in plan"
    rules.append(_rule("4", "Kitchen door into dining", "PENDING",
                       "doors modeled Day 3; " + detail))

    # Rule 5: bedroom doors (PENDING doors; adjacency decides feasibility).
    bedroom_lines, direct, fallback, blocked = [], 0, 0, 0
    families = [r for r in rects if r["type"] == "family living"]
    for bed in beds:
        fam = max([shared_wall(bed, f) for f in families] or [0.0])
        din = max([shared_wall(bed, d) for d in dinings] or [0.0])
        if fam >= 3:
            direct += 1
            bedroom_lines.append("%s -> family (%.1f ft)" % (bed["name"], fam))
        elif din >= 3:
            fallback += 1
            bedroom_lines.append("%s -> DINING fallback (%.1f ft)" % (bed["name"], din))
        else:
            blocked += 1
            bedroom_lines.append("%s -> BLOCKED (no family/dining wall)"
                                 % bed["name"])
    status = "FAIL" if blocked else "PENDING"
    if not beds:
        status, bedroom_lines = "FAIL", ["no bedrooms in plan"]
    rules.append(_rule("5", "Bedroom doors into family living", status,
                       "doors modeled Day 3; " + "; ".join(bedroom_lines)))

    # Rule 6: bedroom windows (PENDING windows; exterior walls counted).
    # The room's own veranda does not block its windows (openings face it).
    wall_lines = []
    windowed_beds = 0
    for bed in beds:
        others = [r for r in rects if r.get("veranda_for") != bed["name"]]
        ext = sum(1 for length in _exterior_walls(bed, others).values()
                  if length >= 3)
        wall_lines.append("%s: %d walled sides" % (bed["name"], ext))
        if ext >= 1:
            windowed_beds += 1
    rules.append(_rule("6", "Bedrooms have windows", "PENDING",
                       "windows modeled Day 3; " + "; ".join(wall_lines)
                       if wall_lines else "windows modeled Day 3"))

    # Rule 7: toilet count, 1 common, attached touch their bedroom.
    toilet_lines, toilet_ok = [], True
    if len(baths) != num_toilets:
        toilet_ok = False
        toilet_lines.append("count %d, wanted %d" % (len(baths), num_toilets))
    commons = [b for b in baths if b["bathroom_kind"] != "attached"]
    if len(commons) != 1:
        toilet_ok = False
        toilet_lines.append("common toilets: %d, wanted exactly 1" % len(commons))
    for bath in baths:
        if bath["bathroom_kind"] == "attached":
            host = _by_name(rects, bath["attached_to"])
            touch = shared_wall(bath, host) if host else 0.0
            if host is None or touch < 3:
                toilet_ok = False
                toilet_lines.append("%s NOT on '%s' (%.1f ft, needs 3 "
                                    "for a door)"
                                    % (bath["name"], bath["attached_to"] or "?",
                                       touch))
            else:
                toilet_lines.append("%s touches %s (%.1f ft)"
                                    % (bath["name"], host["name"], touch))
        else:
            common_space = families + dinings
            touch = max([shared_wall(bath, c) for c in common_space] or [0.0])
            if touch < 3:
                toilet_ok = False
                toilet_lines.append("%s NOT on common space (%.1f ft)"
                                    % (bath["name"], touch))
            else:
                toilet_lines.append("%s on common space (%.1f ft)"
                                    % (bath["name"], touch))
    rules.append(_rule("7", "Toilets: 1 common + attached",
                       "PASS" if toilet_ok else "FAIL",
                       "; ".join(toilet_lines) if toilet_lines else "no toilets"))

    # Rule 8: baths on an exterior wall, never on the front wall.
    bath_lines, bath_ok = [], True
    for bath in baths:
        ext = sum(_exterior_walls(bath, rects).values())
        on_front = bath["y"] - info["row_front_y"] < 0.5
        if ext < 0.5:
            bath_ok = False
            bath_lines.append("%s has NO exterior wall" % bath["name"])
        elif on_front:
            bath_ok = False
            bath_lines.append("%s is on the FRONT wall (violation)" % bath["name"])
        else:
            bath_lines.append("%s exterior, off front wall" % bath["name"])
    rules.append(_rule("8", "Baths ventilated, off front wall",
                       "PASS" if bath_ok else "FAIL",
                       "; ".join(bath_lines) if bath_lines else "no toilets"))

    # Rule 9: bath windows never face front (PENDING windows).
    rules.append(_rule("9", "Bath windows never face road", "PENDING",
                       "windows modeled Day 3"))

    # Rule 10: verandas (count, separation, sizes).
    veranda_lines, veranda_ok = [], True
    bed_hosts = {v.get("veranda_for", "") for v in verandas
                 if _by_name(rects, v.get("veranda_for", ""))
                 and _by_name(rects, v.get("veranda_for", ""))["type"] == "bedroom"}
    if len(bed_hosts) > 2:
        veranda_ok = False
        veranda_lines.append("%d bedrooms veranda'd, max 2" % len(bed_hosts))
    if beds and len(beds) < 2 and len(bed_hosts) < len(beds):
        veranda_ok = False
        veranda_lines.append("small home: every bedroom needs a veranda")
    kitchen_hosts = [v for v in verandas
                     if _by_name(rects, v.get("veranda_for", ""))
                     and _by_name(rects, v.get("veranda_for", ""))["type"] == "kitchen"]
    if kitchens and not kitchen_hosts:
        veranda_ok = False
        veranda_lines.append("kitchen has no veranda")
    for i, first in enumerate(verandas):
        for second in verandas[i + 1:]:
            if _rects_touch(first, second, gap=0.01):
                veranda_ok = False
                veranda_lines.append("%s touches %s"
                                     % (first["name"], second["name"]))
    if not veranda_lines:
        veranda_lines.append("%d separate veranda(s)" % len(verandas))
    rules.append(_rule("10", "Verandas separate + sized",
                       "PASS" if veranda_ok else "FAIL",
                       "; ".join(veranda_lines)))

    # Rule 11: cross ventilation proxy (PENDING openings).
    rules.append(_rule("11", "Cross ventilation 2+ walls", "PENDING",
                       "openings modeled Day 3"))
    # Rule 12: doors/windows modeled (PENDING Day 3).
    rules.append(_rule("12", "Doors + windows modeled", "PENDING",
                       "arrives Day 3 with the door/window step"))

    # Geometry: inside buildable + no overlaps (must hold for a clean plan).
    geo_problems = []
    for rect in rects:
        if rect["x"] < -0.01 or rect["y"] < -0.01 \
                or rect["x"] + rect["w"] > build_w + 0.01 \
                or rect["y"] + rect["d"] > build_d + 0.01:
            geo_problems.append("%s outside buildable" % rect["name"])
    for i, first in enumerate(rects):
        for second in rects[i + 1:]:
            if _area_overlap(first, second) > 0.01:
                geo_problems.append("%s overlaps %s"
                                    % (first["name"], second["name"]))
    rules.append(_rule("G", "Inside buildable, no overlaps",
                       "FAIL" if geo_problems else "PASS",
                       "; ".join(geo_problems) if geo_problems
                       else "all %d rooms inside, no overlaps" % len(rects)))

    angle = _resolve_angle(road_side, north_angle)
    rules.extend(_check_livability(rects, angle))

    # Rule 18: toilet real sizes (per-side ranges, master bounds).
    bath_problems = []
    for rect in rects:
        if rect["type"] == "bathroom":
            bath_problems.extend(_check_bath_size(rect, rects))
    if bath_problems:
        detail_18 = "; ".join(bath_problems)
    elif baths:
        detail_18 = "all %d toilets sized 4-6 x 6-8.5 (master to 6.5 x 10)" \
            % len(baths)
    else:
        detail_18 = "no toilets"
    rules.append(_rule("18", "Toilet real sizes",
                       "FAIL" if bath_problems else "PASS", detail_18))
    rules.append(_check_master_size(rects))

    # Design goals (soft): entry, outline, landscape, kitchen west.
    goals = []
    porch = [r for r in rects if r["type"] == "porch"]
    foyer = [r for r in rects if r["type"] == "foyer"]
    goals.append(_goal("Good entry (porch + foyer)",
                       "MET" if porch and foyer else "MISSED",
                       "porch + foyer placed" if porch and foyer
                       else "missing %s" % " + ".join(
                           [t for t, got in (("porch", porch), ("foyer", foyer))
                            if not got])))
    widths = info["row_widths"]
    stepped = any(abs(w - widths[0]) > 0.5 for w in widths) if widths else False
    breakers = ([s for s, yes in (("stepped rows", stepped),
                                  ("porch", bool(porch)),
                                  ("%d verandas" % len(verandas), bool(verandas)))
                 if yes])
    goals.append(_goal("Outline not a plain rectangle",
                       "MET" if breakers else "MISSED",
                       "broken by " + " + ".join(breakers) if breakers
                       else "plain rectangle"))
    back_margin = build_d - info["house_back"]
    house_area = sum(r["w"] * r["d"] for r in rects
                     if r["type"] not in ("porch", "veranda", "garden"))
    goals.append(_goal("Landscape left on big plots",
                       "MET" if back_margin >= 0 and (back_margin >= 4 or
                       house_area <= 0.85 * build_w * build_d) else "MISSED",
                       "back garden %.1f ft deep" % back_margin
                       if back_margin >= 0 else "house overflows by %.1f ft"
                       % -back_margin))
    west_side = _closest_side(angle, 270.0)
    if not kitchens:
        goals.append(_goal("Kitchen west (among dining/family)", "N/A",
                           "no kitchen in plan"))
        west_met = None
    else:
        mid_types = ("kitchen", "dining", "family living")
        mid = [r for r in rects if r["type"] in mid_types]
        if west_side in ("lowx", "highx"):
            centers = sorted(r["x"] + r["w"] / 2 for r in mid)
            kitchen_c = kitchens[0]["x"] + kitchens[0]["w"] / 2
        else:
            centers = sorted(r["y"] + r["d"] / 2 for r in mid)
            kitchen_c = kitchens[0]["y"] + kitchens[0]["d"] / 2
        at_west = (kitchen_c <= centers[0] + 0.01) \
            if west_side in ("lowx", "front") \
            else (kitchen_c >= centers[-1] - 0.01)
        goals.append(_goal("Kitchen west (among dining/family)",
                           "MET" if at_west else "MISSED",
                           "kitchen at west end" if at_west
                           else "kitchen not at west end"))
        west_met = at_west

    quality = {"direct_doors": direct, "fallback_doors": fallback,
               "back_margin": back_margin, "west_met": west_met,
               "windowed_beds": windowed_beds,
               "relaxed_rooms": len(relaxed_rooms),
               "relaxed_names": relaxed_rooms}
    return rules, goals, quality


def _check_livability(rects, north_angle):
    """Strict rules 13-17 rows (13-16 decide UNLIVABLE; 17 reported)."""
    return [_check_kitchen_exterior(rects, north_angle),
            _check_bedroom_walls(rects),
            _check_toilet_exterior(rects),
            _check_circulation(rects),
            _check_vent_walls(rects)]


def _shared_wall_and_span(host, other):
    """(wall, start, end) of `other` on `host`, (None, 0, 0) if apart."""
    x0, y0 = host["x"], host["y"]
    x1, y1 = x0 + host["w"], y0 + host["d"]
    o_x0, o_y0 = other["x"], other["y"]
    o_x1, o_y1 = o_x0 + other["w"], o_y0 + other["d"]
    if abs(o_x1 - x0) < 0.01:
        return "W", max(y0, o_y0) - y0, min(y1, o_y1) - y0
    if abs(o_x0 - x1) < 0.01:
        return "E", max(y0, o_y0) - y0, min(y1, o_y1) - y0
    if abs(o_y1 - y0) < 0.01:
        return "S", max(x0, o_x0) - x0, min(x1, o_x1) - x0
    if abs(o_y0 - y1) < 0.01:
        return "N", max(x0, o_x0) - x0, min(x1, o_x1) - x0
    return None, 0.0, 0.0


def _check_kitchen_exterior(rects, north_angle):
    """Rule 13: kitchen exterior wall (west preferred) + veranda on it."""
    kitchens = [r for r in rects if r["type"] == "kitchen"]
    if not kitchens:
        return _rule("13", "Kitchen exterior wall + veranda on it",
                     "FAIL", "no kitchen in plan")
    kitchen = kitchens[0]
    runs = _wall_runs(kitchen, rects)
    longest, wall = _longest_run(runs)
    west = _compass_west_wall(north_angle)
    west_best = max([end - start for start, end in runs[west]] or [0.0])
    problems, notes = [], []
    if longest < KITCHEN_MIN_EXTERIOR_FT - EPS:
        problems.append("longest exterior %.1f ft %s (needs %d)" % (
            longest, wall, KITCHEN_MIN_EXTERIOR_FT))
    else:
        notes.append("exterior %.1f ft %s" % (longest, wall))
    if west_best >= VENT_SIDE_FT - EPS:
        notes.append("west wall ventilated")
        west_bend = None
    else:
        west_bend = "west preferred (west has %.1f ft)" % west_best
    verandas = [r for r in rects if r["type"] == "veranda"
                and r.get("veranda_for") == kitchen["name"]]
    if not verandas:
        problems.append("kitchen has no veranda")
    else:
        side, start, end = _shared_wall_and_span(kitchen, verandas[0])
        on_exterior = 0.0
        if side is not None:
            for seg_start, seg_end in runs[side]:
                on_exterior += _overlap_1d(start, end, seg_start, seg_end)
        if on_exterior < VENT_SIDE_FT - EPS:
            problems.append("veranda not on an exterior wall")
        else:
            notes.append("veranda on %s exterior" % side)
    detail = "; ".join(problems + notes +
                        ([west_bend] if west_bend is not None else []))
    status = "FAIL" if problems else ("BEND" if west_bend is not None
                                      else "PASS")
    return _rule("13", "Kitchen exterior wall + veranda on it",
                 status, detail)


def _check_bedroom_walls(rects):
    """Rule 14: every bedroom needs 6 ft of exterior window wall."""
    beds = [r for r in rects if r["type"] == "bedroom"]
    if not beds:
        return _rule("14", "Bedroom window walls (6 ft+)",
                     "FAIL", "no bedrooms in plan")
    lines, fails, bends = [], 0, 0
    for bed in beds:
        runs = _wall_runs(bed, rects)
        longest, wall = _longest_run(runs)
        sides = sum(1 for segs in runs.values()
                    if max([e - s for s, e in segs] or [0.0]) >= VENT_SIDE_FT - EPS)
        if longest < BEDROOM_MIN_WINDOW_FT - EPS:
            fails += 1
            lines.append("%s: best %.1f ft %s (%d window wall(s), needs 6)"
                         % (bed["name"], longest, wall, sides))
        elif sides < 2:
            bends += 1
            lines.append("%s: %.1f ft %s (1 window wall; 2 better)"
                         % (bed["name"], longest, wall))
        else:
            lines.append("%s: %.1f ft %s (%d window walls)"
                         % (bed["name"], longest, wall, sides))
    status = "FAIL" if fails else ("BEND" if bends else "PASS")
    return _rule("14", "Bedroom window walls (6 ft+)",
                 status, "; ".join(lines))


def _check_toilet_exterior(rects):
    """Rule 15: every toilet has an exterior wall (with rule 8)."""
    baths = [r for r in rects if r["type"] == "bathroom"]
    if not baths:
        return _rule("15", "Every toilet has exterior wall",
                     "FAIL", "no toilets in plan")
    lines, ok = [], True
    for bath in baths:
        total = sum(end - start
                    for segs in _wall_runs(bath, rects).values()
                    for start, end in segs)
        if total < 0.5 - EPS:
            ok = False
            lines.append("%s: NO exterior wall" % bath["name"])
        else:
            lines.append("%s: %.1f ft exterior" % (bath["name"], total))
    return _rule("15", "Every toilet has exterior wall",
                 "PASS" if ok else "FAIL", "; ".join(lines))


def _check_circulation(rects):
    """Rule 16: routes only through foyer/living/dining/family.

    Every bedroom reaches the common toilet, and the foyer reaches every
    indoor room except attached baths (entered through their bedroom;
    porch/verandas are entered through their host room). Kitchen,
    bedrooms and toilets are never pass-through rooms.
    """
    beds = [r for r in rects if r["type"] == "bedroom"]
    foyers = [r for r in rects if r["type"] == "foyer"]
    commons = [r for r in rects if r["type"] == "bathroom"
               and r["bathroom_kind"] != "attached"]
    indoor = [r for r in rects if r["type"] not in
              ("porch", "veranda", "wardrobe", "storage", "garden")]
    targets = [r for r in indoor
               if not (r["type"] == "bathroom"
                       and r["bathroom_kind"] == "attached")]
    pairs = []
    if not commons:
        pairs.append((None, None, "no common toilet in plan"))
    for bed in beds:
        for common in commons:
            pairs.append((bed["name"], common["name"], ""))
    if not foyers:
        pairs.append((None, None, "no foyer in plan"))
    for target in targets:
        if foyers and target["name"] != foyers[0]["name"]:
            pairs.append((foyers[0]["name"], target["name"], ""))
    if not pairs:
        return _rule("16", "Circulation via common rooms only",
                     "FAIL", "nothing to route")
    all_types = tuple(sorted({r["type"] for r in indoor}))
    problems, good = [], 0
    for start, goal, missing in pairs:
        if start is None:
            problems.append(missing)
            continue
        if _find_route(rects, start, goal, CIRCULATION_ROOMS) is not None:
            good += 1
            continue
        raw = _find_route(rects, start, goal, all_types)
        if raw is None:
            problems.append("%s -> %s: NO route (disconnected)"
                            % (start, goal))
        else:
            problems.append("%s -> %s: crosses %s (%s)"
                            % (start, goal,
                               _route_crosses(raw, rects).upper() or "nowhere",
                               " -> ".join(raw)))
    detail = "; ".join(problems) if problems else ""
    summary = "%d/%d routes ok" % (good, len(pairs))
    detail = (detail + "; " + summary) if detail else summary
    return _rule("16", "Circulation via common rooms only",
                 "FAIL" if problems else "PASS", detail)


def _check_vent_walls(rects):
    """Rule 17 (soft): living spaces + bedrooms on 2 exterior sides.

    Soft = ranks options but never flips the verdict. One-sided rooms
    bend; a room with NO exterior wall fails.
    """
    rooms = [r for r in rects
             if r["type"] in ("living room", "family living", "dining",
                              "bedroom")]
    if not rooms:
        return _rule("17", "Cross-vent walls, 2 sides (soft)",
                     "FAIL", "no living spaces/bedrooms in plan")
    lines, fails, bends = [], 0, 0
    for room in rooms:
        runs = _wall_runs(room, rects)
        sides = sorted(wall for wall, segs in runs.items()
                       if max([e - s for s, e in segs] or [0.0])
                       >= VENT_SIDE_FT - EPS)
        if len(sides) >= 2:
            pair = "opposite" if ({"W", "E"} <= set(sides)
                                  or {"S", "N"} <= set(sides)) else "adjacent"
            lines.append("%s: %s (%s)" % (room["name"], pair, "+".join(sides)))
        elif len(sides) == 1:
            bends += 1
            lines.append("%s: 1 side (%s; 2 better)"
                         % (room["name"], sides[0]))
        else:
            fails += 1
            lines.append("%s: NO exterior wall" % room["name"])
    status = "FAIL" if fails else ("BEND" if bends else "PASS")
    return _rule("17", "Cross-vent walls, 2 sides (soft)",
                 status, "; ".join(lines))


def _rule(rule_id, name, status, detail):
    """One hard-rule result row."""
    return {"id": rule_id, "name": name, "status": status, "detail": detail}


def _goal(name, status, detail):
    """One design-goal result row."""
    return {"name": name, "status": status, "detail": detail}


def _check_room_size(rect, rects):
    """Rule 1 for one placed room. Returns (problems, [(name, bend)]).

    Wardrobe/store filler beside side-strip baths is leftover space, not a
    room: exempt from size rules. Family/living rooms inside their relaxed
    range bend instead of failing.
    """
    problems, bends = [], []
    name = rect["name"]
    kind = rect["type"]
    width, depth = rect["w"], rect["d"]
    if kind in SIZE_RULES:
        low, high = SIZE_RULES[kind]
        relaxed = RELAXED_RANGES.get(kind)
        for side, label in ((width, "width"), (depth, "depth")):
            if low - EPS <= side <= high + EPS:
                continue
            if relaxed is not None and relaxed[0] - EPS <= side \
                    <= relaxed[1] + EPS:
                bends.append((name, "%s: %s %s relaxed (preferred %s-%s)" % (
                    name, label, format_ft_in(side),
                    format_ft_in(low), format_ft_in(high))))
            else:
                problems.append("%s: %s %s outside %s-%s" % (
                    name, label, format_ft_in(side),
                    format_ft_in(low), format_ft_in(high)))
        if abs(width - depth) < 1 - EPS:
            problems.append("%s: %s x %s is square-ish" % (
                name, format_ft_in(width), format_ft_in(depth)))
    elif kind == "foyer":
        for side, label in ((width, "width"), (depth, "depth")):
            if not FOYER_MIN_FT - EPS <= side <= FOYER_MAX_FT + EPS:
                problems.append("%s: %s %s outside proposed %s-%s" % (
                    name, label, format_ft_in(side),
                    format_ft_in(FOYER_MIN_FT), format_ft_in(FOYER_MAX_FT)))
        if abs(width - depth) < 1 - EPS:
            problems.append("%s: %s x %s is square-ish" % (
                name, format_ft_in(width), format_ft_in(depth)))
    elif kind == "porch":
        if not PORCH_MIN_W_FT - EPS <= width <= PORCH_MAX_W_FT + EPS:
            problems.append("%s: width %s outside proposed %s-%s" % (
                name, format_ft_in(width), format_ft_in(PORCH_MIN_W_FT),
                format_ft_in(PORCH_MAX_W_FT)))
        if not PORCH_MIN_D_FT - EPS <= depth <= PORCH_MAX_D_FT + EPS:
            problems.append("%s: depth %s outside proposed %s-%s" % (
                name, format_ft_in(depth), format_ft_in(PORCH_MIN_D_FT),
                format_ft_in(PORCH_MAX_D_FT)))
    elif kind == "veranda":
        proj, length = min(width, depth), max(width, depth)
        if not VERANDA_PROJ_MIN_FT - EPS <= proj <= VERANDA_PROJ_MAX_FT + EPS:
            problems.append("%s: projection %s outside %s-%s" % (
                name, format_ft_in(proj), format_ft_in(VERANDA_PROJ_MIN_FT),
                format_ft_in(VERANDA_PROJ_MAX_FT)))
        if length < VERANDA_MIN_LEN_FT - EPS:
            problems.append("%s: length %s under %s" % (
                name, format_ft_in(length), format_ft_in(VERANDA_MIN_LEN_FT)))
        host = _by_name(rects, rect.get("veranda_for", ""))
        if host is not None and length > max(host["w"], host["d"]) + EPS:
            problems.append("%s: longer than its room's wall" % name)
    elif kind == "corridor":
        if min(width, depth) < CORRIDOR_MIN_WIDTH_FT - EPS:
            problems.append("%s: narrower than %s" % (
                name, format_ft_in(CORRIDOR_MIN_WIDTH_FT)))
    elif kind in ("wardrobe", "storage"):
        pass  # filler beside side-strip baths: leftover space, no rules
    elif kind == "bathroom":
        pass  # rule 18 checks toilet real sizes (per-side ranges)
    elif kind == "garden":
        pass  # outdoor landscape from wishes, no size rules
    else:
        problems.append("%s: unknown type '%s'" % (name, kind))
    return problems, bends


def _check_bath_size(rect, rects):
    """Rule 18 for one placed toilet. Returns a list of problem strings.

    Per-side ranges: 4-6 ft wide (road-parallel) by 6 ft to 8 ft 6 in
    long; the toilet attached to the largest bedroom may be up to
    6 ft 6 in by 10 ft. Never-square still applies. Toilets are never
    stretched to fill a strip.
    """
    problems = []
    name = rect["name"]
    width, depth = rect["w"], rect["d"]
    master, best_area = "", 0.0
    for other in rects:
        if other["type"] == "bedroom":
            area = other["w"] * other["d"]
            if area > best_area:
                master, best_area = other["name"], area
    if master and rect.get("attached_to", "") == master:
        w_low, w_high = MASTER_TOILET_W_RANGE
        d_low, d_high = MASTER_TOILET_D_RANGE
        bounds = "master"
    else:
        w_low, w_high = TOILET_W_RANGE
        d_low, d_high = TOILET_D_RANGE
        bounds = "standard"
    if not w_low - EPS <= width <= w_high + EPS:
        problems.append("%s: width %s outside %s toilet %s-%s" % (
            name, format_ft_in(width), bounds,
            format_ft_in(w_low), format_ft_in(w_high)))
    if not d_low - EPS <= depth <= d_high + EPS:
        problems.append("%s: depth %s outside %s toilet %s-%s" % (
            name, format_ft_in(depth), bounds,
            format_ft_in(d_low), format_ft_in(d_high)))
    if abs(width - depth) < 1 - EPS:
        problems.append("%s: %s x %s is square-ish" % (
            name, format_ft_in(width), format_ft_in(depth)))
    return problems


def _master_bedroom(rects):
    """The designated master: name says master, else Bedroom 1, else first."""
    beds = [r for r in rects if r["type"] == "bedroom"]
    if not beds:
        return None
    return sorted(beds, key=lambda r: ("master" not in r["name"].lower(),
                                       r["name"]))[0]


def _check_master_size(rects):
    """Rule 19: master is the largest bedroom (+10%) with the top toilet."""
    master = _master_bedroom(rects)
    if master is None:
        return _rule("19", "Master bedroom largest", "FAIL",
                     "no bedrooms in plan")
    problems, notes = [], []
    master_area = master["w"] * master["d"]
    for bed in rects:
        if bed["type"] != "bedroom" or bed is master:
            continue
        other = bed["w"] * bed["d"]
        if other <= 0:
            continue
        if master_area < 1.1 * other - 0.01:
            problems.append("%s (%d sq ft) not 10%% over %s (%d sq ft)"
                            % (master["name"], round(master_area),
                               bed["name"], round(other)))
    if not problems:
        notes.append("%s largest (%d sq ft)"
                     % (master["name"], round(master_area)))
    attached = [r for r in rects if r["type"] == "bathroom"
                and r["bathroom_kind"] == "attached"]
    master_baths = [b["w"] * b["d"] for b in attached
                    if b.get("attached_to", "") == master["name"]]
    other_baths = [b["w"] * b["d"] for b in attached
                   if b.get("attached_to", "") != master["name"]]
    if master_baths and other_baths \
            and max(master_baths) < max(other_baths) - 0.01:
        problems.append("master toilet (%d sq ft) smaller than another "
                        "attached toilet (%d sq ft)"
                        % (round(max(master_baths)), round(max(other_baths))))
    detail = "; ".join(problems + notes) if problems or notes \
        else "single bedroom"
    return _rule("19", "Master bedroom largest",
                 "FAIL" if problems else "PASS", detail)


def _score(rules, goals, quality):
    """One number per option: strict fails hurt most, bends cost a little.

    Every FAIL costs 100 (all rules rank options, while only 5, 7,
    13-16, 19 and G flip the verdict). BEND rows cost 1, except rule 1,
    whose relaxed rooms cost 2 each via quality. Goals, door facts and
    wishes break ties (met +10, missed -15: a plan missing a clear wish
    ranks lower); margins reward garden and punish overflow.
    """
    fails = sum(1 for r in rules if r["status"] == "FAIL")
    bends = sum(1 for r in rules
                if r["status"] == "BEND" and r["id"] != "1")
    met = sum(1 for g in goals if g["status"] == "MET")
    wishes_met = quality.get("wishes_met", 0)
    wishes_missed = quality.get("wishes_total", wishes_met) - wishes_met
    return (-100 * fails - bends + 5 * met + 2 * quality["direct_doors"]
            + quality["windowed_beds"]
            - 2 * quality["relaxed_rooms"]
            + 10 * wishes_met - 15 * wishes_missed
            + 0.05 * max(0.0, quality["back_margin"])
            + 0.5 * min(0.0, quality["back_margin"]))



