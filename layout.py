# layout.py
# Step 2 of House Planner: room program -> floor plan layout (plain Python, no AI).
#
# What this file does:
#   1. Places every room as a rectangle inside the buildable area (plot minus
#      setbacks), following the architect's zoning: front band (porch, foyer,
#      living), middle band (dining, kitchen, family living), back band
#      (bedrooms + toilets). Family living is the circulation hub, so the plan
#      needs no corridors at all.
#   2. Tries MANY candidate layouts (different room orders, widths, toilet
#      slots), scores each against the hard rules, and keeps the best one.
#   3. Checks the winning plan against all 12 hard rules + design goals and
#      reports PASS / FAIL / PENDING for each (door/window rules stay PENDING
#      until Day 3, when doors and windows are modeled).
#
# Local frame (everything is placed here, the drawing rotates it later):
#   - x runs parallel to the road, from the viewer's left (standing at the
#     road looking at the house). y runs from the road inward (y = 0 at the
#     buildable front edge). All sizes in feet.
#   - Rooms may stretch or shrink within their size rules so each row fills
#     neatly with no gaps. Rows may step (different widths); steps, porch and
#     verandas break the outline so it is not a plain rectangle.
#
# Toilets: small rooms need a home. A bathroom can sit full-depth in a
# 10 ft deep back row with the bedrooms (the only depth they share), as one
# half of a stacked pair inside a deeper row, as a single in a narrow
# front bath strip between the front and middle rows (common baths only:
# door to the middle row above), or as a single in a narrow back strip
# behind the bedrooms (attached only: touching its bedroom). No strip
# ever sits between middle and back rows: a full row there would block
# every bedroom door.
#
# NOTE (Day 2, proposed defaults, architect to confirm): foyer 6-12 ft per
# side, porch 6-12 ft wide x 4-6 ft deep, veranda projection 3-5 ft.
# Porch/veranda are outdoor projections, so like corridors they are exempt
# from the never-square rule.

import itertools
import math
import time

from ai_program import (
    CORRIDOR_MIN_WIDTH_FT,
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    SIZE_RULES,
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

# Row depths we try (ft). Middle rows hold family rooms (12-15 range, dining
# caps at 14); back rows hold bedrooms; the strip holds only bathrooms.
MID_DEPTH_OPTIONS = (12, 13, 14)
BACK_DEPTH_OPTIONS = (12, 13)
BACK_WITH_BATH_DEPTH = 10  # only depth shared by bedrooms (10-15) and baths (6-10)
STRIP_DEPTH_FT = 7
FRONT_DEPTH_WITH_LIVING = 12  # only depth shared by foyer (6-12) and living (12-15)

# Safety cap so odd briefs cannot hang the app; search stops here (best wins).
EVAL_CAP = 8000

# Tiny tolerance for float comparisons.
EPS = 1e-6

# Which local side is WEST (for the kitchen-west preference). Standing at the
# road looking inward, x grows to the viewer's right, so: road South -> west
# is low x; road North -> west is high x. For East/West roads the middle row
# runs north-south, so "west end of the row" does not exist (N/A, reported).
WEST_SIDE = {"south": "low-x", "north": "high-x", "east": "n/a", "west": "n/a"}

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


def _stack_width_options(depth):
    """Valid stacked-cell widths at this row depth, nearest 7.5 ft first.

    A stack needs a split into two non-square 6-10 ft bathrooms; not every
    width allows one (e.g. at 13 ft depth only 8-10 ft widths split). Empty
    list means no stack fits this depth.
    """
    options = [width / 2 for width in range(12, 21)
               if _stack_split(depth, width / 2) is not None]
    options.sort(key=lambda width: abs(width - 7.5))
    return options


def _width_combos(option_lists, cap=40):
    """Best-first stacked-width combos (each list already nearest-first)."""
    if not option_lists:
        yield ()
        return
    seen = 0
    for combo in itertools.product(*option_lists):
        yield combo
        seen += 1
        if seen >= cap:
            return


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


def _stack_split(depth, width):
    """Split a stacked cell of `depth` into two bathrooms of `width`.

    Returns (lower_depth, upper_depth) with both sides in 6-10 ft and both
    halves non-square, preferring the most even split. None when impossible.
    """
    best = None
    depth_ft = depth
    low = max(6.0, depth_ft - 10.0)
    high = min(10.0, depth_ft - 6.0)
    steps = int(round((high - low) / 0.5)) + 1
    for step in range(max(steps, 0)):
        first = low + step * 0.5
        second = depth_ft - first
        if second < 6.0 - EPS or second > 10.0 + EPS:
            continue
        if abs(first - width) < 1 - EPS:
            continue
        if abs(second - width) < 1 - EPS:
            continue
        if best is None or abs(first - second) < abs(best[0] - best[1]):
            best = (first, second)
    return best


def _cells_sig(cells):
    """Hashable signature of row cells for the row cache."""
    sig = []
    for cell in cells:
        if cell["kind"] == "stack":
            sig.append(("S", cell["rooms"][0].get("name"),
                        cell["rooms"][1].get("name")))
        else:
            room = cell["room"]
            kind = _room_type(room)
            sig.append(("R", room.get("name"), kind,
                        _pref(room, "width_ft", kind)))
    return tuple(sig)


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


def _safe_single_targets(pref, los, his, cap, depth):
    """Width options for a one-room row: nearest-pref first, never square.

    A single room must span its row exactly, so a target within 1 ft of
    the row depth could never satisfy the never-square rule; these targets
    skip that trap. Empty list means no legal width exists.
    """
    hi = min(his, cap)
    options = []
    for delta in (0, 1, -1, 1.5, -1.5, 2, -2, 2.5, -2.5, 3, -3):
        cand = pref + delta
        if los - EPS <= cand <= hi + EPS and abs(cand - depth) >= 1 - EPS:
            if all(abs(cand - seen) > 0.01 for seen in options):
                options.append(cand)
    return options


def _place_row(cells, target_w, depth, x0, y0, relax=False, cache=None):
    """Row placement with an optional memo cache (copies on cache hit).

    The search tries the same rows hundreds of times across candidates;
    the cache (owned by build_layout) makes repeats free. Cached rects
    are copied because callers shift them in place.
    """
    if cache is None:
        return _place_row_inner(cells, target_w, depth, x0, y0, relax)
    key = (_cells_sig(cells), round(target_w, 3), depth, relax)
    if key in cache:
        hit = cache[key]
        if hit is None:
            return None
        return [dict(rect) for rect in hit[0]], tuple(hit[1])
    result = _place_row_inner(cells, target_w, depth, x0, y0, relax)
    if result is None:
        cache[key] = None
    else:
        cache[key] = ([dict(rect) for rect in result[0]], tuple(result[1]))
    return result


def _place_row_inner(cells, target_w, depth, x0, y0, relax):
    """Place one row of cells at (x0, y0) with row depth `depth`.

    cells: singles {"kind": "single", "room": {...}} and stacks {"kind":
    "stack", "rooms": [lower, upper]}. Returns (rects, widths) or None
    when the row cannot be filled within the size rules (target met
    exactly, never-square holds, stacks split). Stack widths enumerate
    best-first; singles branch around never-square. Relax skips repair.
    """
    if relax:
        # Last resort: plain fill, the checker will report the violations.
        items = []
        for cell in cells:
            if cell["kind"] == "stack":
                items.append({"lo": 6.0, "hi": 10.0, "pref": 7.5})
            else:
                low, high = _type_range(_room_type(cell["room"]))
                items.append({"lo": low, "hi": high,
                              "pref": _pref(cell["room"], "width_ft",
                                            _room_type(cell["room"]))})
        widths = _fill_widths(items, target_w, relax=True)
        if widths is None:
            return None
        return _emit_row(cells, widths, depth, x0, y0), widths
    stack_cells = [c for c in cells if c["kind"] == "stack"]
    single_cells = [c for c in cells if c["kind"] == "single"]
    stack_opts = [_stack_width_options(depth) for _ in stack_cells]
    if any(not opts for opts in stack_opts):
        return None
    single_boxes = []
    for cell in single_cells:
        low, high = _type_range(_room_type(cell["room"]))
        single_boxes.append((low, high, _pref(cell["room"], "width_ft",
                                              _room_type(cell["room"]))))
    for combo in _width_combos(stack_opts):
        rest = target_w - sum(combo)
        if single_boxes:
            single_widths = _branch_fill(single_boxes, rest, depth)
            if single_widths is None:
                continue
            rounded = _round_half(single_widths, single_boxes, depth, rest)
            if rounded is not None:
                single_widths = rounded
        elif abs(rest) > 0.01:
            continue  # stacks alone must sum exactly (rare degenerate row)
        else:
            single_widths = []
        widths, stack_iter, single_iter = [], iter(combo), iter(single_widths)
        for cell in cells:
            widths.append(next(stack_iter) if cell["kind"] == "stack"
                          else next(single_iter))
        return _emit_row(cells, widths, depth, x0, y0), widths
    return None


def _emit_row(cells, widths, depth, x0, y0):
    """Turn final cell widths into room rectangles (dicts with x, y, w, d)."""
    rects = []
    x = x0
    for cell, width in zip(cells, widths):
        if cell["kind"] == "single":
            rects.append(_as_rect(cell["room"], x, y0, width, depth))
        else:
            lower, upper = cell["rooms"]
            split = _stack_split(depth, width)
            if split is None:  # relax mode only; split evenly as best attempt
                split = (depth / 2, depth / 2)
            rects.append(_as_rect(lower, x, y0, width, split[0]))
            rects.append(_as_rect(upper, x, y0 + split[0], width, split[1]))
        x += width
    return rects


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


def _bath_assignments(bathrooms):
    """Ways to slot bathrooms: strips, one stacked pair, back-row singles.

    Yields {front: [...], mid_pair: None|(lower, upper), back_pairs: [...],
    back10: [...], back_strip: [...]}. Common baths ride the front strip
    (door to the middle row above), a 10 ft back row (door to the row in
    front), or the bottom of the single stacked pair. Attached baths sit
    full-depth in the 10 ft back row, on top of the stacked pair (middle
    row: under their bedroom; back row: beside it), or as singles in the
    back strip behind the bedrooms (touching their bedroom in front).
    Leftover attached baths always fit the back strip, so attached-attached
    pairs (which would fail touch or ventilation somewhere) never form.
    No strip ever sits between middle and back: a full row there would
    block every bedroom door (slab stacking).
    """
    attached = [b for b in bathrooms
                if str(b.get("bathroom_kind", "")).strip().lower() == "attached"]
    commons = [b for b in bathrooms if b not in attached]
    if len(commons) == 1:
        front_options = [[commons[0]], []]
    else:
        # 0 or 2+ commons (bad program): all ride the front strip,
        # and the checker flags the count.
        front_options = [list(commons)]
    for front in front_options:
        pool_common = [c for c in commons if c not in front]
        for back10_count in range(min(len(attached), 2) + 1):
            for common_in_back10 in ([False, True] if pool_common else [False]):
                back10 = attached[:back10_count]
                if common_in_back10:
                    back10 = back10 + pool_common
                rest = attached[back10_count:]
                mid_choices = [None]
                if pool_common and not common_in_back10:
                    for partner in rest[:4]:
                        mid_choices.append((pool_common[0], partner))
                for mid_pair in mid_choices:
                    rest2 = [b for b in rest
                             if mid_pair is None or b is not mid_pair[1]]
                    back_choices = [None]
                    if pool_common and not common_in_back10 and mid_pair is None:
                        # Common still homeless: it bottoms a back pair.
                        back_choices = [(pool_common[0], partner)
                                        for partner in rest2[:3]]
                        if not back_choices:
                            continue
                    for back_pair in back_choices:
                        rest3 = [b for b in rest2
                                 if back_pair is None or b is not back_pair[1]]
                        back_pairs = [back_pair] if back_pair else []
                        if back10 and back_pairs:
                            continue  # D10 singles + stacks share no row
                        yield {"front": list(front), "mid_pair": mid_pair,
                               "back_pairs": back_pairs, "back10": list(back10),
                               "back_strip": list(rest3)}
    if not bathrooms:
        yield {"front": [], "mid_pair": None, "back_pairs": [],
               "back10": [], "back_strip": []}


def _orient_pair(lower, upper, row):
    """Put an attached bath where it can touch its bedroom.

    Middle-row pair: attached goes on top (touches the back row). Back-row
    pair: the common bath goes below (touches the row in front); attached
    baths touch their side bedroom from either half.
    """
    if row == "mid" and lower.get("bathroom_kind", "") == "attached" \
            and upper.get("bathroom_kind", "") != "attached":
        return upper, lower
    if row == "back" and upper.get("bathroom_kind", "") != "attached" \
            and lower.get("bathroom_kind", "") == "attached":
        return upper, lower
    return lower, upper


# --- Candidate layouts: orders, rows, porch, verandas ---

def _mid_orders(mid_rooms, pair_count, road_side):
    """Distinct middle-row orders, kitchen-west orders first (cap 12).

    mid_rooms: the kitchen/dining/family rooms present. "S" marks a stacked
    bath pair cell. Trying orders matters: it decides which rooms touch.
    Stacks sit at a row end only: a middle stack's lower bath would be
    fully interior (no exterior wall for ventilation).
    """
    tags = ["R%d" % i for i in range(len(mid_rooms))] + ["S"] * pair_count
    if not tags:
        return [()]
    west = WEST_SIDE.get(road_side, "n/a")
    kitchen_idx = None
    for i, room in enumerate(mid_rooms):
        if _room_type(room) == "kitchen":
            kitchen_idx = i
    orders = sorted(set(itertools.permutations(tags)))
    if pair_count:
        orders = [o for o in orders if o[0] == "S" or o[-1] == "S"]

    def _kitchen_west(order):
        if kitchen_idx is None or west == "n/a":
            return 0
        pos = order.index("R%d" % kitchen_idx)
        if west == "low-x":
            return 0 if pos == 0 else 1
        return 0 if pos == len(order) - 1 else 1

    orders.sort(key=lambda order: (_kitchen_west(order), order))
    return orders[:12]


def _back_variants(bedrooms, has_stacks):
    """(bedroom order, stack slot) variants for the back row.

    Orders: largest-from-west and largest-from-east. The stacked pair (a
    common bath below its attached partner) sits at the row start or end:
    end slots keep both halves on an exterior side wall, and the slot
    beside the partner's bedroom gives the attached touch. Without stacks
    there is only the end slot (positions would duplicate).
    """
    orders = [list(bedrooms)]
    if len(bedrooms) >= 2:
        orders.append(list(reversed(bedrooms)))  # buckets() sorted desc
    slots = ["end"]
    if has_stacks and orders[0]:
        slots.append("start")
    return [(order, slot) for order in orders for slot in slots]


def _insert_back10(bedrooms, singles):
    """Back-row order with full-depth baths tucked after their bedroom."""
    order = list(bedrooms)
    homeless = []
    for bath in singles:
        target = str(bath.get("attached_to", "")).strip()
        placed = False
        for i, bed in enumerate(order):
            if isinstance(bed, dict) and bed.get("name", "") == target:
                order.insert(i + 1, bath)
                placed = True
                break
        if not placed:
            homeless.append(bath)
    return order + homeless


def _front_strip_offsets(strip_rects, above_rects, house_w):
    """Candidate x-offsets for the front bath strip (house coords).

    The strip center aims under the dining/family span of the row above
    (the common bath's door wall); center and both ends are fallbacks.
    Offsets keep the strip inside the house width.
    """
    if not strip_rects:
        return [0.0]
    strip_w = sum(r["w"] for r in strip_rects)
    roomy = max(0.0, house_w - strip_w)
    targets = []
    span = [r for r in above_rects if r["type"] in ("dining", "family living")]
    if span:
        middle = sum(r["x"] + r["w"] / 2 for r in span) / len(span)
        targets.append(middle - strip_w / 2)
    targets += [roomy / 2, 0.0, roomy]
    offsets = []
    for value in targets:
        value = _clamp(value, 0.0, roomy)
        if all(abs(value - seen) > 0.25 for seen in offsets):
            offsets.append(value)
    # Single baths need fewer fallbacks (target + center + one end).
    return offsets[:3] if len(strip_rects) == 1 else offsets[:4]


def _back_strip_offsets(strip_rects, bed_rects, house_w):
    """Candidate x-offsets for the back bath strip (house coords).

    Each bath aims under its named bedroom in the row in front; center and
    both ends are fallbacks. Offsets keep the strip inside the house width.
    """
    if not strip_rects:
        return [0.0]
    strip_w = sum(r["w"] for r in strip_rects)
    roomy = max(0.0, house_w - strip_w)
    targets = []
    x = 0.0
    for bath in strip_rects:
        center = x + bath["w"] / 2
        x += bath["w"]
        for bed in bed_rects:
            if bed["type"] == "bedroom" and bed["name"] == bath["attached_to"]:
                targets.append(bed["x"] + bed["w"] / 2 - center)
                break
    targets += [roomy / 2, 0.0, roomy]
    offsets = []
    for value in targets:
        value = _clamp(value, 0.0, roomy)
        if all(abs(value - seen) > 0.25 for seen in offsets):
            offsets.append(value)
    # Single baths need fewer fallbacks (target + center + one end).
    return offsets[:3] if len(strip_rects) == 1 else offsets[:4]


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


def _veranda_targets(buckets, rects, notes):
    """Which rooms get a veranda: flags say, capped at 2 bedrooms + kitchen.

    `needs_veranda` flags come from the AI. When nothing is flagged at all,
    the two largest bedrooms + kitchen are veranda'd automatically (rule 10).
    Returns [(room_rect, wall_order), ...].
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
    targets = [(_by_name(rects, r["name"]), ["W", "E", "N", "S"])
               for r in flagged_beds]
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
                        if any(_rects_touch(cand, other, gap=0.5)
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


def _row_width_pref(cells):
    """Preferred total width of row cells (rooms prefs, stacks 7.5)."""
    total = 0.0
    for cell in cells:
        if cell["kind"] == "stack":
            total += 7.5
        else:
            total += _pref(cell["room"], "width_ft", _room_type(cell["room"]))
    return total


def _cells_width_bounds(cells):
    """(min, max) total width of row cells from their size ranges."""
    los, his = 0.0, 0.0
    for cell in cells:
        if cell["kind"] == "stack":
            los += 6.0
            his += 10.0
        else:
            low, high = _type_range(_room_type(cell["room"]))
            los += low
            his += high
    return los, his


def _place_mid_split(mid_cells, mid_depth, build_w, relax, cache):
    """Two-row middle for narrow plots: rooms split across two full rows.

    Tries a 2/rest cut first (kitchen+dining, then family + stacks), then a
    1/rest cut. Each row fills its own preferred width. Returns [(rects,
    depth), (rects, depth)] road-inward, or None.
    """
    singles = [c for c in mid_cells if c["kind"] == "single"]
    stacks = [c for c in mid_cells if c["kind"] == "stack"]
    for cut in (2, 1):
        groups = [singles[:cut], singles[cut:] + stacks]
        if not groups[0] or not groups[1]:
            continue  # same as the single row (which already failed)
        rows = []
        for group in groups:
            los, his = _cells_width_bounds(group)
            if los > build_w + EPS and not relax:
                break
            placed = _place_row(group, _clamp(_row_width_pref(group), los,
                                              min(his, build_w)),
                                mid_depth, 0.0, 0.0, relax, cache)
            if placed is None:
                break
            rows.append((placed[0], mid_depth))
        if len(rows) == 2:
            return rows
    return None


def _place_strip_xs(baths, house_w, relax, cache):
    """X-layout of one bath strip at x=0 (narrowed for exterior sides).

    Returns rects, [] when the strip is empty, None when it cannot fill.
    """
    if not baths:
        return []
    strip_cells = [{"kind": "single", "room": b} for b in baths]
    strip_los, strip_his = _cells_width_bounds(strip_cells)
    cap = house_w if strip_los > house_w - 2 else house_w - 2
    if len(strip_cells) == 1 and not relax:
        targets = _safe_single_targets(_row_width_pref(strip_cells),
                                       strip_los, strip_his, cap,
                                       STRIP_DEPTH_FT)
    else:
        targets = [_clamp(_row_width_pref(strip_cells), strip_los,
                          min(strip_his, cap))]
    for target in targets:
        if target < strip_los - EPS or target > house_w + EPS:
            continue
        placed = _place_row(strip_cells, target, STRIP_DEPTH_FT,
                            0.0, 0.0, relax, cache)
        if placed is not None:
            return placed[0]
    return None


def _place_row_xs(buckets, assignment, mid_order, bed_order, stack_slot,
                  mid_depth, back_depth, mid_width, build_w, relax,
                  combo_notes, cache, front_baths, back_baths):
    """X-layouts of every row at y=0 (house coords). Returns layout or None.

    layout = {"front": ..., "mids": [...], "fstrip": ..., "back": ...,
    "bstrip": ..., "house_w": width}, each row (rects, depth). Rows come
    out centered; strips keep x=0 and their searched offsets apply at
    assembly. None means the rows cannot fill (another combination of
    order/slot/depth may still work).
    """
    # Front row: foyer + living (own stepped width is fine).
    front_cells = ([{"kind": "single", "room": buckets["foyer"][0]}]
                   if buckets["foyer"] else [])
    front_cells += ([{"kind": "single", "room": buckets["living"][0]}]
                    if buckets["living"] else [])
    front_rects = []
    front_depth = FRONT_DEPTH_WITH_LIVING
    if front_cells:
        if len(front_cells) == 1:
            only = front_cells[0]["room"]
            low, high = _type_range(_room_type(only))
            front_depth = _clamp(_pref(only, "depth_ft", _room_type(only)), low, high)
        front_los, front_his = _cells_width_bounds(front_cells)
        if len(front_cells) == 1 and not relax:
            only = front_cells[0]["room"]
            front_targets = _safe_single_targets(
                _pref(only, "width_ft", _room_type(only)),
                front_los, front_his, build_w, front_depth)
        else:
            front_targets = [_clamp(_row_width_pref(front_cells), front_los,
                                    min(front_his, build_w))]
        for target in front_targets:
            placed = _place_row(front_cells, target, front_depth,
                                0.0, 0.0, relax, cache)
            if placed is not None:
                front_rects, _ = placed
                break
        if not front_rects:
            return None

    # Middle row(s): kitchen/dining/family + one stacked pair at most. One
    # row when it fits; two rows when the plot is too narrow for one row.
    mid_rooms = buckets["kitchen"] + buckets["dining"] + buckets["family"]
    mid_row_list = []  # (rects, depth, tag) in road-inward order
    mid_pair = assignment["mid_pair"]
    if mid_order:
        mid_cells = []
        pair_used = False
        for tag in mid_order:
            if tag == "S":
                if mid_pair is None or pair_used:
                    return None
                pair_used = True
                lower, upper = _orient_pair(mid_pair[0], mid_pair[1], "mid")
                mid_cells.append({"kind": "stack", "rooms": [lower, upper]})
            else:
                mid_cells.append({"kind": "single",
                                  "room": mid_rooms[int(tag[1:])]})
        if mid_pair is not None and not pair_used:
            return None
        if len(mid_cells) == 1 and not relax:
            only = mid_cells[0]
            if only["kind"] == "stack":
                mid_targets = _safe_single_targets(
                    7.5, 6.0, 10.0, build_w, mid_depth)
            else:
                kind = _room_type(only["room"])
                low, high = _type_range(kind)
                mid_targets = _safe_single_targets(
                    _pref(only["room"], "width_ft", kind),
                    low, high, build_w, mid_depth)
        else:
            mid_targets = [mid_width]
        placed = None
        for target in mid_targets:
            placed = _place_row(mid_cells, target, mid_depth,
                                0.0, 0.0, relax, cache)
            if placed is not None:
                break
        if placed is not None:
            mid_row_list.append((placed[0], mid_depth, "mid"))
        else:
            split = _place_mid_split(mid_cells, mid_depth, build_w, relax, cache)
            if split is None:
                return None
            mid_row_list.append((split[0][0], mid_depth, "midA"))
            mid_row_list.append((split[1][0], mid_depth, "midB"))
            combo_notes.append("Middle band split in two rows (narrow plot).")
    mid_rects = [r for rects, _row_d, _tag in mid_row_list for r in rects]

    # Back row: bedrooms + full-depth baths and/or the stacked pair at
    # the searched slot (row start or end). Own stepped width is fine.
    back_cells = []
    if assignment["back10"]:
        for room in _insert_back10(bed_order, assignment["back10"]):
            back_cells.append({"kind": "single", "room": room})
    else:
        stack_cells = []
        for lower, upper in assignment["back_pairs"]:
            lower, upper = _orient_pair(lower, upper, "back")
            stack_cells.append({"kind": "stack", "rooms": [lower, upper]})
        beds = [{"kind": "single", "room": r} for r in bed_order]
        if stack_slot == "start":
            back_cells = stack_cells + beds
        else:
            back_cells = beds + stack_cells
    back_rects = []
    depth = BACK_WITH_BATH_DEPTH if assignment["back10"] else back_depth
    if back_cells:
        back_los, back_his = _cells_width_bounds(back_cells)
        back_pref = _row_width_pref(back_cells)
        if len(back_cells) == 1 and not relax:
            targets = _safe_single_targets(back_pref, back_los, back_his,
                                           build_w, depth)
        else:
            targets = [mid_width, _clamp(back_pref, back_los,
                                         min(back_his, build_w))]
            if back_his >= build_w - EPS and build_w - max(targets) > 0.5:
                targets.append(build_w)  # wide back row for many bedrooms
        for target in targets:
            placed = _place_row(back_cells, target, depth, 0.0, 0.0, relax, cache)
            if placed is not None:
                back_rects, _ = placed
                break
        if not back_rects:
            return None

    house_w = max([r["x"] + r["w"] for r in front_rects + mid_rects + back_rects]
                  or [0.0])
    if house_w < EPS:
        return None

    # Bath strips (x=0; assembly applies the searched offsets).
    fstrip_rects = _place_strip_xs(front_baths, house_w, relax, cache)
    if fstrip_rects is None:
        return None
    bstrip_rects = _place_strip_xs(back_baths, house_w, relax, cache)
    if bstrip_rects is None:
        return None

    # Center rows in the house width. The front row keeps x=0: like the
    # strips, its searched offset applies at assembly (a middle kitchen
    # needs the front row shifted aside for its veranda's south wall).
    for rects in [r for r, _d, _t in mid_row_list] + [back_rects]:
        if not rects:
            continue
        row_w = max(r["x"] + r["w"] for r in rects)
        for rect in rects:
            rect["x"] += (house_w - row_w) / 2
    return {"front": (front_rects, front_depth), "mids": mid_row_list,
            "fstrip": (fstrip_rects, STRIP_DEPTH_FT),
            "back": (back_rects, depth),
            "bstrip": (bstrip_rects, STRIP_DEPTH_FT), "house_w": house_w}


def _front_row_offsets(layout):
    """Candidate x-offsets for the front row (house coords).

    Centered, always. Plus both ends when the kitchen sits mid-row: its
    side walls are covered then, so only a shifted front row leaves its
    south wall an exterior run for its veranda. Ends qualify only when
    they expose at least 3 ft of that wall.
    """
    front_rects = layout["front"][0]
    if not front_rects:
        return [0.0]
    house_w = layout["house_w"]
    front_w = max(r["x"] + r["w"] for r in front_rects)
    roomy = max(0.0, house_w - front_w)
    middle_kitchen = None
    for rects, _row_d, _tag in layout["mids"]:
        rooms = sorted(rects, key=lambda r: r["x"])
        for i, room in enumerate(rooms):
            if room["type"] == "kitchen" and 0 < i < len(rooms) - 1:
                middle_kitchen = room
    offsets = [roomy / 2]
    if middle_kitchen is not None:
        kx0 = middle_kitchen["x"]
        kx1 = kx0 + middle_kitchen["w"]
        if kx1 - front_w >= 3 - EPS:
            offsets.append(0.0)
        if house_w - front_w - kx0 >= 3 - EPS:
            offsets.append(roomy)
    deduped = []
    for value in offsets:
        value = _clamp(value, 0.0, roomy)
        if all(abs(value - seen) > 0.25 for seen in deduped):
            deduped.append(value)
    return deduped


def _assemble(layout, row_offset, front_offset, back_offset, buckets,
              build_w, build_d, notes):
    """One full candidate from x-layouts: fresh copy per row offset.

    Shifts the front row and both strips, stacks rows road-inward (front,
    front strip, middles, back, back strip), centers the house in the
    buildable area, adds porch + verandas. Returns (rects, info).
    Geometry overflow is kept, not rejected: the checker reports it and
    the scorer penalizes it (best attempt + failed rules).
    """
    rows = []
    if layout["front"][0]:
        rows.append((layout["front"][0], layout["front"][1], "front"))
    if layout["fstrip"][0]:
        rows.append((layout["fstrip"][0], layout["fstrip"][1], "strip"))
    rows += [(rects, row_d, tag) for rects, row_d, tag in layout["mids"]]
    if layout["back"][0]:
        rows.append((layout["back"][0], layout["back"][1], "back"))
    if layout["bstrip"][0]:
        rows.append((layout["bstrip"][0], layout["bstrip"][1], "bstrip"))
    house_w = layout["house_w"]
    # Fresh copies: the same layout is reused across strip offsets.
    rows = [([dict(rect) for rect in rects], row_d, tag)
            for rects, row_d, tag in rows]
    for rects, _row_d, tag in rows:
        if tag in ("front", "strip", "bstrip"):
            if tag == "front":
                offset = row_offset
            else:
                offset = front_offset if tag == "strip" else back_offset
            row_w = max(r["x"] + r["w"] for r in rects)
            roomy = max(0.0, house_w - row_w)
            for rect in rects:
                rect["x"] += _clamp(offset, 0.0, roomy)
    _porch_w, porch_depth = _porch_size(
        buckets["porch"][0] if buckets["porch"] else None)
    y_cursor = porch_depth + 1.0 if (buckets["foyer"] or buckets["living"]) else 2.0
    row_front_y = y_cursor
    for rects, row_d, tag in rows:
        for rect in rects:
            rect["y"] += y_cursor
            rect["row"] = tag  # front/strip/mid/midA/midB/back/bstrip
        y_cursor += row_d
    house_back = y_cursor

    # Center the house in the buildable area, then add porch + verandas.
    rects = [rect for row_rects, _row_d, _tag in rows for rect in row_rects]
    for rect in rects:
        rect["x"] += (build_w - house_w) / 2
    auto_porch = not buckets["porch"]
    if buckets["porch"] or buckets["foyer"] or buckets["living"]:
        _add_porch(rects, buckets, build_w, notes, auto_porch)
    _add_verandas(rects, _veranda_targets(buckets, rects, notes),
                  build_w, build_d, notes)

    info = {"house_w": house_w, "house_back": house_back,
            "row_front_y": row_front_y,
            "row_widths": [max(r["x"] + r["w"] for r in row_rects)
                           - min(r["x"] for r in row_rects)
                           for row_rects, _row_d, _tag in rows],
            "rows": rows}
    return rects, info


# --- Rule checker: all 12 hard rules + geometry + design goals ---

def _check_all(rects, info, build_w, build_d, road_side, num_toilets):
    """Check one placed plan. Returns (rules, goals, quality).

    rules: [{id, name, status, detail}] with status PASS/FAIL/PENDING.
    Door/window rules are PENDING until Day 3 but already report the useful
    adjacency facts. goals: [{name, status, detail}] (MET/MISSED/N/A).
    quality: small dict of tiebreak facts for the scorer.
    """
    rules = []
    baths = [r for r in rects if r["type"] == "bathroom"]
    beds = [r for r in rects if r["type"] == "bedroom"]
    verandas = [r for r in rects if r["type"] == "veranda"]

    # Rule 1: room sizes + never square.
    size_problems = []
    for rect in rects:
        problems = _check_room_size(rect, rects)
        size_problems.extend(problems)
    rules.append(_rule("1", "Room sizes + never square",
                       "FAIL" if size_problems else "PASS",
                       "; ".join(size_problems) if size_problems
                       else "all %d rooms in range, none square" % len(rects)))

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
                     if r["type"] not in ("porch", "veranda"))
    goals.append(_goal("Landscape left on big plots",
                       "MET" if back_margin >= 0 and (back_margin >= 4 or
                       house_area <= 0.85 * build_w * build_d) else "MISSED",
                       "back garden %.1f ft deep" % back_margin
                       if back_margin >= 0 else "house overflows by %.1f ft"
                       % -back_margin))
    west = WEST_SIDE.get(road_side, "n/a")
    if west == "n/a" or not kitchens:
        goals.append(_goal("Kitchen west (within its band)", "N/A",
                           "middle row runs north-south" if west == "n/a"
                           else "no kitchen in plan"))
        west_met = None
    else:
        mid_types = ("kitchen", "dining", "family living")
        mid = [r for r in rects if r["type"] in mid_types]
        centers = sorted(r["x"] + r["w"] / 2 for r in mid)
        kitchen_c = kitchens[0]["x"] + kitchens[0]["w"] / 2
        at_west = (kitchen_c <= centers[0] + 0.01) if west == "low-x" \
            else (kitchen_c >= centers[-1] - 0.01)
        goals.append(_goal("Kitchen west (within its band)",
                           "MET" if at_west else "MISSED",
                           "kitchen at west end" if at_west
                           else "kitchen not at west end"))
        west_met = at_west

    quality = {"direct_doors": direct, "fallback_doors": fallback,
               "back_margin": back_margin, "west_met": west_met,
               "windowed_beds": windowed_beds}
    return rules, goals, quality


def _rule(rule_id, name, status, detail):
    """One hard-rule result row."""
    return {"id": rule_id, "name": name, "status": status, "detail": detail}


def _goal(name, status, detail):
    """One design-goal result row."""
    return {"name": name, "status": status, "detail": detail}


def _check_room_size(rect, rects):
    """Rule 1 for one placed room. Returns a list of problem strings."""
    problems = []
    name = rect["name"]
    kind = rect["type"]
    width, depth = rect["w"], rect["d"]
    if kind in SIZE_RULES:
        low, high = SIZE_RULES[kind]
        for side, label in ((width, "width"), (depth, "depth")):
            if not low - EPS <= side <= high + EPS:
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
    else:
        problems.append("%s: unknown type '%s'" % (name, kind))
    return problems


def _score(rules, goals, quality):
    """One number per candidate: hard fails hurt most, goals break ties."""
    fails = sum(1 for r in rules if r["status"] == "FAIL")
    met = sum(1 for g in goals if g["status"] == "MET")
    return (-100 * fails + 5 * met + 2 * quality["direct_doors"]
            + quality["windowed_beds"]
            + 0.05 * max(0.0, quality["back_margin"])
            + 0.5 * min(0.0, quality["back_margin"]))


# --- Main entry point ---

def build_layout(program_rooms, plot_width, plot_depth, road_side, num_toilets):
    """Place the program, try candidates, return the best plan + rule report.

    Returns a dict: {ok, placements (plot-local rects), rules, goals, notes,
    score, candidates_tried, feasible, seconds, truncated, plot, buildable,
    house}. When nothing fits, ok is False and placements holds the best
    attempt (or []), with the failed rules listed.
    """
    started = time.time()
    road = str(road_side or "South").strip().lower()
    if road not in WEST_SIDE:
        road = "south"
    if road in ("east", "west"):
        plot_w, plot_d = float(plot_depth), float(plot_width)
    else:
        plot_w, plot_d = float(plot_width), float(plot_depth)
    build_w = plot_w - SETBACK_SIDE_FT * 2
    build_d = plot_d - SETBACK_FRONT_FT - SETBACK_BACK_FT
    base = {"plot": {"w": plot_w, "d": plot_d, "road": road},
            "buildable": {"w": build_w, "d": build_d},
            "candidates_tried": 0, "feasible": 0, "seconds": 0.0,
            "truncated": False, "score": 0.0}
    if build_w <= 0 or build_d <= 0:
        base.update({"ok": False, "placements": [], "rules": [], "goals": [],
                     "notes": ["Plot too small: setbacks leave no buildable area."],
                     "house": {}})
        return base

    buckets, notes = _buckets(program_rooms)
    for key, label in (("kitchen", "kitchen"), ("dining", "dining"),
                       ("family", "family living"), ("bedrooms", "bedroom")):
        if not buckets[key]:
            notes.append("No %s in the program; its row sits empty." % label)
    mid_rooms = buckets["kitchen"] + buckets["dining"] + buckets["family"]
    total_baths = len(buckets["bathrooms"])
    # Odd bath counts need a single slot (front strip) first; even counts
    # pair cleanly, so compact no-strip variants go first.
    bath_options = sorted(
        _bath_assignments(buckets["bathrooms"]),
        key=lambda v: (len(v["front"]) if total_baths % 2 == 0
                       else -len(v["front"]), len(v["back10"])))

    best = None
    tried, feasible, truncated = 0, 0, False
    row_cache = {}  # memo for _place_row across all candidates (relax in key)
    for relax in (False, True):  # strict first; relaxed best-attempt fallback
        for assignment in bath_options:
            pair_count = 1 if assignment["mid_pair"] is not None else 0
            orders = _mid_orders(mid_rooms, pair_count, road)
            back_variant_list = _back_variants(
                buckets["bedrooms"], bool(assignment["back_pairs"]))
            front_orders = [assignment["front"]]
            if len(assignment["front"]) > 1:
                front_orders.append(list(reversed(assignment["front"])))
            back_orders = [assignment["back_strip"]]
            if len(assignment["back_strip"]) > 1:
                back_orders.append(list(reversed(assignment["back_strip"])))
            mid_los = sum(6.0 for _ in range(pair_count)) + sum(
                _type_range(_room_type(r))[0] for r in mid_rooms)
            mid_his = sum(10.0 for _ in range(pair_count)) + sum(
                _type_range(_room_type(r))[1] for r in mid_rooms)
            mid_pref = sum(7.5 for _ in range(pair_count)) + sum(
                _pref(r, "width_ft", _room_type(r)) for r in mid_rooms)
            widths = []
            if mid_order_cells(mid_rooms, pair_count):
                if mid_los <= build_w + EPS:
                    widths.append(_clamp(mid_pref, mid_los, min(mid_his, build_w)))
                    if abs(widths[0] - build_w) > 0.5 and build_w <= mid_his + EPS:
                        widths.append(build_w)
                else:
                    # Single row cannot fit; the split fallback may save it.
                    widths.append(build_w)
            else:
                widths.append(min(build_w, 20.0))
            for mid_width in widths:
                for mid_depth in MID_DEPTH_OPTIONS:
                    for back_depth in BACK_DEPTH_OPTIONS:
                        for mid_order in orders:
                            for bed_order, stack_slot in back_variant_list:
                                for front_baths in front_orders:
                                    for back_baths in back_orders:
                                        if tried >= (EVAL_CAP if not relax else 500):
                                            truncated = True
                                            break
                                        combo_notes = []
                                        layout = _place_row_xs(
                                            buckets, assignment, mid_order,
                                            bed_order, stack_slot, mid_depth,
                                            back_depth, mid_width, build_w,
                                            relax, combo_notes, row_cache,
                                            front_baths, back_baths)
                                        if layout is None:
                                            continue
                                        # Strips aim: front under the
                                        # dining/family span of the row above
                                        # (mid/midA), back under bedrooms.
                                        above = layout["mids"][0][0] \
                                            if layout["mids"] else []
                                        row_offsets = _front_row_offsets(layout)
                                        front_offsets = _front_strip_offsets(
                                            layout["fstrip"][0], above,
                                            layout["house_w"])
                                        bed_rects = [r for r in layout["back"][0]
                                                     if r["type"] == "bedroom"]
                                        back_offsets = _back_strip_offsets(
                                            layout["bstrip"][0], bed_rects,
                                            layout["house_w"])
                                        for row_offset in row_offsets:
                                            for front_offset in front_offsets:
                                                for back_offset in back_offsets:
                                                    cap = EVAL_CAP if not relax else 500
                                                    if tried >= cap:
                                                        truncated = True
                                                        break
                                                    cand_notes = []
                                                    cand_rects, cand_info = _assemble(
                                                        layout, row_offset,
                                                        front_offset,
                                                        back_offset, buckets,
                                                        build_w, build_d,
                                                        cand_notes)
                                                    tried += 1
                                                    feasible += 1
                                                    sub = list(notes) + combo_notes
                                                    rules, goals, quality = _check_all(
                                                        cand_rects, cand_info,
                                                        build_w, build_d,
                                                        road, num_toilets)
                                                    # Rows must connect:
                                                    # consecutive rows share
                                                    # x-range, else penalize.
                                                    connected = _rows_connect(
                                                        cand_info)
                                                    score = _score(
                                                        rules, goals, quality)
                                                    if not connected:
                                                        score -= 50
                                                        sub.append(
                                                            "Rows do not all "
                                                            "connect; "
                                                            "circulation gap "
                                                            "penalized.")
                                                    if best is None or \
                                                            score > best["score"]:
                                                        best = {
                                                            "rects": cand_rects,
                                                            "info": cand_info,
                                                            "rules": rules,
                                                            "goals": goals,
                                                            "score": score,
                                                            "extra_notes":
                                                                sub + cand_notes}
                                                if truncated:
                                                    break
                                            if truncated:
                                                break
                                        if truncated:
                                            break
                                    if truncated:
                                        break
                                if truncated:
                                    break
                            if truncated:
                                break
                        if truncated:
                            break
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break
        if best is not None or truncated:
            break  # strict pass done (or cap hit); skip/keep relax fallback
        if not relax:
            notes.append("Nothing fits strictly; retrying relaxed (best attempt).")

    base.update({"candidates_tried": tried, "feasible": feasible,
                 "seconds": time.time() - started, "truncated": truncated})
    if truncated:
        notes.append("Search stopped at the %d-candidate cap; showing the "
                     "best found." % tried)
        if best is not None:
            best["extra_notes"].append(notes[-1])
    if best is None:
        base.update({"ok": False, "placements": [], "rules": [], "goals": [],
                     "notes": notes + ["No candidate could be built at all."],
                     "house": {}})
        return base
    placements = []
    for rect in best["rects"]:
        moved = dict(rect)
        moved["x"] += SETBACK_SIDE_FT
        moved["y"] += SETBACK_FRONT_FT
        placements.append(moved)
    base.update({"ok": True, "placements": placements, "rules": best["rules"],
                 "goals": best["goals"], "score": best["score"],
                 "notes": best["extra_notes"],
                 "house": {"w": best["info"]["house_w"],
                           "back": best["info"]["house_back"]}})
    return base


def mid_order_cells(mid_rooms, pair_count):
    """True when the middle row has any cells (rooms or stacked pairs)."""
    return bool(mid_rooms) or pair_count > 0


def _rows_connect(info):
    """Consecutive rows share x-range (else the plan has a gap)."""
    rows = [row for row, _row_d, _tag in info["rows"]]
    for lower, upper in zip(rows, rows[1:]):
        low_span = (min(r["x"] for r in lower), max(r["x"] + r["w"] for r in lower))
        up_span = (min(r["x"] for r in upper), max(r["x"] + r["w"] for r in upper))
        if _overlap_1d(low_span[0], low_span[1], up_span[0], up_span[1]) < 1 - EPS:
            return False
    return True
