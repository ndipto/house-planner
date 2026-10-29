# typology.py
# Day 2 typology placer: room program -> THREE floor-plan options.
#
# Planning patterns from the architect's own practice (PROJECT.md):
# - THREE-STRIP (main): a center public spine (foyer, living, dining,
#   family living front-to-back, porch outside the foyer, NO corridor)
#   with left/right side strips holding bedrooms, kitchen, toilets.
#   Bedrooms take back corners when possible (master placed per option);
#   toilets sit between bedrooms against the outer wall (leftover width
#   becomes a wardrobe/store); the kitchen sits mid-strip next to dining.
# - L-SHAPE WITH COURT (buildable width 45 ft+ only): a front wing for
#   foyer/living/dining/kitchen joined to a side wing for family living
#   and bedrooms, landscape/court filling the open corner.
# - NARROW plots (buildable under 30 ft): TWO strips (spine + one side).
# - Options: A = three-strip, kitchen west; B = three-strip mirrored
#   (kitchen east, master other corner); C = L-shape when it fits,
#   else a third three-strip variant. Genuinely different, each scored.
#
# Local frame: road at the bottom (y=0), x road-parallel from the
# viewer's left. Strip widths 10-15 ft, all dimensions rounded to
# 6 inches. Preferred PROJECT.md sizes stay; family living 10-15 and
# living room 12-17 are relaxed absolutes (penalty + note when used).
# Geometry is a HARD constraint: nothing is ever placed outside the
# buildable area; an unplaceable option is skipped with a clear reason.
# Fitting ladder: full width minus veranda margins, living room to a
# front corner when the spine runs long, small foyer, wished merges,
# then min-depths. Rooms that cannot reach their door-zone are still
# placed: the strict checker reports them honestly (bend/fail), never
# silently dropped. Wishes shape the plan: combined spaces are placed
# adjacent as one open space, a wished garden buffers the living room.

import itertools
import re

from ai_program import (
    MASTER_TOILET_D_RANGE,
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    TOILET_D_RANGE,
)
from layout import (
    EPS,
    RELAXED_RANGES,
    _add_porch,
    _add_verandas,
    _area_overlap,
    _as_rect,
    _branch_fill,
    _buckets,
    _check_all,
    _porch_size,
    _pref,
    _room_type,
    _round_half,
    _score,
    _type_range,
    _veranda_targets,
    livability_verdict,
    shared_wall,
)


class _Infeasible(Exception):
    """A typology cannot fit this brief: geometry is a hard constraint.

    Raised with a clear reason instead of placing anything outside the
    buildable area; build_options turns it into "Option X skipped: ...".
    """

# Spine order, front to back. The hub has no corridor by construction.
SPINE_ORDER = ["foyer", "living room", "dining", "family living"]

# Room words the wish parser understands (matched longest-first).
_WISH_ROOMS = {
    "living room": "living room", "family living": "family living",
    "dining room": "dining", "master bedroom": "bedroom",
    "living": "living room", "lounge": "living room",
    "dining": "dining", "family": "family living",
    "kitchen": "kitchen", "bedroom": "bedroom", "bed": "bedroom",
}

# "Combined X and Y", "X and Y as one (big) space", "open-plan X and Y".
_COMBINE_PATTERNS = (
    r"combin\w*\s+(?:the\s+)?([a-z ]+?)\s+and\s+(?:the\s+)?([a-z ]+?)"
    r"(?:[.,;]|$| as | into | to )",
    r"([a-z ]+?)\s+and\s+([a-z ]+?)\s+as\s+one(?:\s+\w+)?\s+space",
    r"open[\s-]?plan\s+(?:the\s+)?([a-z ]+?)\s+and\s+(?:the\s+)?"
    r"([a-z ]+?)(?:[.,;]|$)",
)


def _wish_room(phrase):
    """Map a wish phrase to a room type (None when no room word matches)."""
    words = " %s " % re.sub(r"[^a-z ]", " ", phrase.strip().lower())
    for key in sorted(_WISH_ROOMS, key=len, reverse=True):
        if " %s " % key in words:
            return _WISH_ROOMS[key]
    return None


def _parse_wishes(wishes):
    """Parse client wishes into layout directives.

    Returns {"combine": [(type_a, type_b)], "garden": bool, "notes": []}.
    Bedroom combinations are refused (privacy); unknown rooms are noted
    and skipped. The garden always sits beside the living room for now.
    """
    text = (wishes or "").strip().lower()
    directives = {"combine": [], "garden": False, "notes": []}
    if not text:
        return directives
    seen = set()
    for pattern in _COMBINE_PATTERNS:
        for first, second in re.findall(pattern, text):
            rooms = (_wish_room(first), _wish_room(second))
            if rooms[0] is None or rooms[1] is None:
                directives["notes"].append(
                    "Could not match rooms in '%s and %s'; skipped."
                    % (first.strip(), second.strip()))
                continue
            if rooms[0] == rooms[1] or tuple(sorted(rooms)) in seen:
                continue
            seen.add(tuple(sorted(rooms)))
            if "bedroom" in rooms:
                directives["notes"].append(
                    "Bedrooms stay separate (privacy); combination skipped.")
                continue
            directives["combine"].append(tuple(sorted(rooms)))
    if "garden" in text or "courtyard" in text or "lawn" in text:
        directives["garden"] = True
        match = re.search(
            r"(?:garden|courtyard|lawn)\s+(?:with|beside|next to|near|"
            r"outside|off|for|behind|in front of)\s+(?:the\s+)?([a-z ]+?)"
            r"(?:[.,;]|$| which | that | as | and )", text)
        if match and _wish_room(match.group(1)) not in (
                None, "living room"):
            directives["notes"].append(
                "Garden only supported beside the living room for now; "
                "living room used.")
        if "buffer" in text:
            directives["notes"].append(
                "Garden works as the indoor-outdoor buffer.")
    return directives


def _half(value):
    """Round to 6 inches (all typology dimensions are half-foot)."""
    return round(value * 2) / 2


def _local_dims(plot_width, plot_depth, road):
    """Plot-local extents + buildable: x parallel road, y road-inward."""
    if road in ("east", "west"):
        plot_w, plot_d = float(plot_depth), float(plot_width)
    else:
        plot_w, plot_d = float(plot_width), float(plot_depth)
    build_w = plot_w - SETBACK_SIDE_FT * 2
    build_d = plot_d - SETBACK_FRONT_FT - SETBACK_BACK_FT
    return plot_w, plot_d, build_w, build_d


def _west_strip_index(road):
    """Strip index on the compass-west side (None: west runs front-back).

    Viewer stands at the road looking inward, x to the right: road South
    -> west is low x (strip 0); road North -> west is high x (strip 2).
    On East/West roads west points front/back, so no strip is "west".
    """
    if road == "south":
        return 0
    if road == "north":
        return 2
    return None


def _strip_widths_three(build_w):
    """(side_w, center_w, x0, total, note): full width minus margins.

    The house stops 3 ft short of each side when the width allows, so
    side rooms keep veranda walls; below 38 ft it takes the full width
    (rooms first, verandas best-effort). Houses cap at 42 ft wide.
    """
    if build_w - 6 >= 32:
        total = min(build_w - 6, 42.0)
    else:
        total = min(build_w, 32.0)
    if total >= 32:
        center, side = 12.0, _half((total - 12.0) / 2)
    else:
        side, center = 10.0, total - 20.0
    x0 = _half((build_w - total) / 2)
    note = ""
    if build_w - total > 0.01:
        note = "House %.0f ft wide in %.0f ft buildable; sides stay landscape." % (
            total, build_w)
    return side, center, x0, total, note


def _strip_widths_two(build_w):
    """(center_w, side_w, x0, total): full width minus veranda margins."""
    if build_w - 6 >= 22:
        total = min(build_w - 6, 27.0)
    else:
        total = min(build_w, 22.0)
    center = min(12.0, total - 10.0)
    side = total - center
    x0 = _half((build_w - total) / 2)
    return center, side, x0, total


def _depth_options(room, width):
    """Valid depths (0.5 ft) + relaxed ones: ([preferred], [relaxed]).

    Preferred = PROJECT.md range + never-square vs width. Relaxed =
    family living 10-15 / living room 12-17 when preferred fails.
    """
    kind = _room_type(room)
    low, high = _type_range(kind)
    preferred, relaxed = [], []
    depth = low
    while depth <= high + EPS:
        if abs(depth - width) >= 1 - EPS:
            preferred.append(_half(depth))
        depth += 0.5
    if kind in RELAXED_RANGES and not preferred:
        low, high = RELAXED_RANGES[kind]
        depth = low
        while depth <= high + EPS:
            if abs(depth - width) >= 1 - EPS:
                relaxed.append(_half(depth))
            depth += 0.5
    return preferred, relaxed


def _spine_depths(spine_rooms, width, height, notes):
    """Depths filling the spine height exactly (front to back).

    Returns ([(room, depth)], [relaxed names], tried) or (None, [], tried)
    when no exact fill exists (caller falls back to preferred depths +
    gap). Prefers taller dining/family (bigger door-zone for side rooms).
    """
    option_lists = []
    for room in spine_rooms:
        preferred, relaxed = _depth_options(room, width)
        options = [(d, False) for d in preferred] + [(d, True) for d in relaxed]
        if _room_type(room) == "foyer":
            capped = [(d, flag) for d, flag in options if d <= 8 + EPS]
            if capped:
                options = capped  # small foyer (about 6 ft deep)
        if not options:
            return None, [], 1
        option_lists.append(options)
    tried = 1
    for options in option_lists:
        tried *= len(options)
    best = None
    for combo in itertools.product(*option_lists):
        if abs(sum(d for d, _ in combo) - height) > 0.01:
            continue
        relaxed = sum(1 for _, flag in combo if flag)
        depths = {}
        for room, (d, _) in zip(spine_rooms, combo):
            depths[_room_type(room)] = d
        key = (relaxed, -depths.get("dining", 0),
               -depths.get("family living", 0), depths.get("foyer", 0))
        if best is None or key < best[0]:
            best = (key, combo)
    if best is None:
        return None, [], tried
    _key, combo = best
    relaxed_names = [room["name"] for room, (_, flag) in zip(spine_rooms, combo)
                     if flag]
    for name in relaxed_names:
        notes.append("%s uses a relaxed size (bend, -2)." % name)
    return ([(room, d) for room, (d, _) in zip(spine_rooms, combo)],
            relaxed_names, tried)


def _bath_extra(bath, master_name):
    """Slot extra for a bath: (real width, is_master_toilet).

    Toilets keep a real 5 ft width (never stretched to fill the strip);
    the master toilet gets the longer 6-10 ft depth range instead of
    extra width, so side stacks stay compact enough for every door.
    """
    is_master = bath.get("attached_to", "") == master_name and bool(master_name)
    return (5.0, is_master)


def _valid_pairs(buckets, directives, notes):
    """Wished combine pairs whose rooms are both in the program (noted)."""
    present = {_room_type(r) for key in
               ("foyer", "living", "kitchen", "dining", "family")
               for r in buckets[key]}
    valid = []
    for pair in directives["combine"]:
        if pair[0] in present and pair[1] in present:
            valid.append(pair)
        else:
            notes.append("Wish needs %s + %s; not in the program, skipped."
                         % pair)
    return valid


def _assign_three_strip(buckets, kitchen_strip, master_strip, notes,
                        directives, living_out):
    """Back-to-front slot lists ((west, east)) + valid pairs + merged flag.

    Master takes its back corner, second bedroom the other back corner,
    attached baths pin below their bedroom, kitchen goes mid-strip on
    its side, the common toilet mid-strip opposite. The living room (when
    out of the spine) takes a front corner: kitchen side when merged with
    the kitchen (directly below it, one open space), else the shorter
    side. Extra bedrooms stack front-ward (placed, reported honestly).
    """
    kitchen_side = 0 if kitchen_strip == 0 else 1
    master_side = 0 if master_strip == 0 else 1
    other_side = 1 - kitchen_side
    beds = list(buckets["bedrooms"])
    master_name = beds[0]["name"] if beds else ""
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    living = buckets["living"][0] if buckets["living"] else None
    bath_of, loose_baths, common = _bath_map(buckets, notes)
    valid_pairs = _valid_pairs(buckets, directives, notes)
    merge_lk = living_out and living is not None and kitchen is not None \
        and any("living room" in pair and "kitchen" in pair
                for pair in valid_pairs)
    sides = [[], []]

    def _bed_with_bath(bed, strip):
        sides[strip].append(("bedroom", bed, None))
        for bath in bath_of.get(bed["name"], []):
            sides[strip].append(("bath", bath, _bath_extra(bath, master_name)))

    if beds:
        _bed_with_bath(beds[0], master_side)
    if len(beds) > 1:
        _bed_with_bath(beds[1], 1 - master_side)
    # Two middle orders on the non-kitchen side (common above/below bed 3).
    middle_beds = beds[2:]
    variants = []
    for common_first in (True, False):
        order = [list(sides[0]), list(sides[1])]
        if kitchen is not None:
            order[kitchen_side].append(("kitchen", kitchen, None))
        middle = list(middle_beds)
        if common is not None and not common_first and middle:
            first, middle = middle[0], middle[1:]
            order[other_side].append(("bedroom", first, None))
            for bath in bath_of.get(first["name"], []):
                order[other_side].append(
                    ("bath", bath, _bath_extra(bath, master_name)))
        if common is not None:
            order[other_side].append(("common", common, (5.0, False)))
        for bed in middle:
            order[other_side].append(("bedroom", bed, None))
            for bath in bath_of.get(bed["name"], []):
                order[other_side].append(
                    ("bath", bath, _bath_extra(bath, master_name)))
        for bath in loose_baths:
            order[other_side].append(("common", bath, (5.0, False)))
        if living_out and living is not None:
            if merge_lk:
                living_side = kitchen_side
            elif len(order[0]) < len(order[1]):
                living_side = 0
            elif len(order[1]) < len(order[0]):
                living_side = 1
            else:
                living_side = kitchen_side
            order[living_side].append(("living", living, None))
        variants.append(order)
    return variants, valid_pairs, merge_lk


def _slot_options(kind, room, strip_w, bath_info=None):
    """Depth options (0.5 ft) for one side-stack slot (valid only).

    Baths keep real widths (slot extra: width + master flag, never
    stretched); depths run the per-side toilet ranges. Other rooms span
    the strip full-width.
    """
    if kind in ("bath", "common"):
        width = bath_info[0]
        if bath_info[1]:
            low, high = MASTER_TOILET_D_RANGE
        else:
            low, high = TOILET_D_RANGE
    else:
        width = strip_w
        low, high = _type_range(_room_type(room))
    options = []
    depth = low
    while depth <= high + EPS:
        if abs(depth - width) >= 1 - EPS:
            options.append(_half(depth))
        depth += 0.5
    if not options:  # best attempt: middle of range (checker reports it)
        options = [_half((low + high) / 2)]
    return options


def _stack_side(slots, strip_x0, strip_w, build_d, spans, notes,
                outer_east=False, min_bottom=0.0):
    """Stack slots back-anchored (top at build_d); maximize door-zone touch.

    spans = {"foyer"/"dining"/"family": (y0, y1)} spine door-zones.
    Attached baths sit against the outer wall (east edge when outer_east)
    with a wardrobe/store filling the leftover width beside them; the
    common bath sits on the inner edge (direct spine door) with an open
    notch outside it (ventilation + outline break). Combos below
    min_bottom are rejected: geometry is a hard constraint (G), so an
    unstackable side raises _Infeasible instead of overflowing.
    Returns (rects, satisfied, total_targets, tried): every slot placed
    even when its door-zone is missed (reported, never dropped).
    """
    option_lists = [_slot_options(kind, room, strip_w, extra)
                    for kind, room, extra in slots]
    tried = 1
    for options in option_lists:
        tried *= len(options)
    best = None
    for combo in itertools.product(*option_lists):
        heights = sum(combo)
        bottom = build_d - heights
        if bottom < min_bottom - EPS:
            continue  # hard floor: never below the plot (or garden gap)
        score, satisfied, total = 0.0, 0, 0
        top = build_d
        for (kind, room, extra), depth in zip(slots, combo):
            keys = []
            if kind == "kitchen":
                keys = ["dining", "family"]
            elif kind in ("bedroom", "common"):
                keys = ["family", "dining"]
            elif kind == "living":
                keys = ["foyer", "dining"]
            overlaps = []
            for key in keys:
                if key in spans:
                    span = spans[key]
                    overlaps.append(max(
                        0.0, min(top, span[1]) - max(top - depth, span[0])))
            if overlaps:
                total += 1
                reach = max(overlaps)
                if reach >= 3 - EPS:
                    satisfied += 1
                    score += 100.0
                score += reach * 2.0
                if overlaps[0] >= 3 - EPS:
                    score += 1.0  # preferred door-zone (family / dining)
            top -= depth
        score -= max(0.0, bottom) * 0.05
        key = (satisfied, score)
        if best is None or key > best[0]:
            best = (key, combo, satisfied, total)
    if best is None:
        need = sum(min(options) for options in option_lists)
        raise _Infeasible("side rooms need at least %.0f ft depth, have "
                          "%.0f ft" % (need, build_d - min_bottom))
    _key, combo, satisfied, total = best
    rects = []
    top = build_d
    kitchen_side = any(s_kind == "kitchen" for s_kind, _r, _e in slots)
    for (kind, room, extra), depth in zip(slots, combo):
        bottom = top - depth
        if kind == "bath":
            bath_w = extra[0]
            label = "Store" if kitchen_side else "Wardrobe"
            filler_w = strip_w - bath_w
            if outer_east:
                bath_x, filler_x = strip_x0 + strip_w - bath_w, strip_x0
            else:
                bath_x, filler_x = strip_x0, strip_x0 + bath_w
            rects.append(_as_rect(room, bath_x, bottom, bath_w, depth))
            rects.append(_as_rect({"name": "%s (%s)" % (label, room["name"]),
                                   "type": "wardrobe",
                                   "width_range": [filler_w, filler_w],
                                   "depth_range": [depth, depth]},
                                  filler_x, bottom, filler_w, depth))
        elif kind == "common":
            bath_w = extra[0]
            if outer_east:
                bath_x = strip_x0  # inner (west) edge: direct spine door
            else:
                bath_x = strip_x0 + strip_w - bath_w  # inner (east) edge
            rects.append(_as_rect(room, bath_x, bottom, bath_w, depth))
        else:
            rects.append(_as_rect(room, strip_x0, bottom, strip_w, depth))
        top = bottom
    return rects, satisfied, total, tried


def _spine_spans(rects):
    """Door-zone y-spans of the placed spine rooms (dining/family)."""
    spans = {}
    for rect in rects:
        kind = _room_type(rect)
        if kind == "dining":
            spans["dining"] = (rect["y"], rect["y"] + rect["d"])
        elif kind == "family living":
            spans["family"] = (rect["y"], rect["y"] + rect["d"])
        elif kind == "foyer":
            spans["foyer"] = (rect["y"], rect["y"] + rect["d"])
    return spans


def _y0_porch(buckets):
    """Front margin: porch depth (porch abuts the foyer), else 2 ft."""
    if not (buckets["porch"] or buckets["foyer"] or buckets["living"]):
        return 2.0
    program = buckets["porch"][0] if buckets["porch"] else None
    _width, depth = _porch_size(program)
    return depth


def _shell(rects, buckets, build_w, build_d, notes):
    """Add porch + verandas to placed rooms (inside the buildable area)."""
    if buckets["porch"] or buckets["foyer"] or buckets["living"]:
        _add_porch(rects, buckets, build_w, notes, not buckets["porch"])
    _add_verandas(rects, _veranda_targets(buckets, rects, notes),
                  build_w, build_d, notes)


def _place_spine(spine_rooms, x0, width, y0, height, notes):
    """Spine rooms front-to-back; raises _Infeasible when nothing fits.

    Exact fill first (small foyer, tall dining/family), then min-depths
    with an open back lobby. Geometry is a hard constraint: the spine
    never overflows the plot (G); it fails with a clear reason instead.
    Returns (rects, relaxed, tried).
    """
    depths, relaxed, tried = _spine_depths(spine_rooms, width, height, notes)
    if depths is None:
        depths, relaxed = [], []
        for room in spine_rooms:
            preferred, relaxed_opts = _depth_options(room, width)
            all_opts = [(d, False) for d in preferred] + \
                [(d, True) for d in relaxed_opts]
            if _room_type(room) == "foyer":
                capped = [(d, flag) for d, flag in all_opts if d <= 8 + EPS]
                if capped:
                    all_opts = capped
            if not all_opts:
                raise _Infeasible("no %s fits a %.0f ft strip"
                                  % (_room_type(room), width))
            depth, flag = min(all_opts)
            depths.append((room, depth))
            if flag and room["name"] not in relaxed:
                relaxed.append(room["name"])
                notes.append("%s uses a relaxed size (bend, -2)."
                             % room["name"])
        used = sum(d for _room, d in depths)
        if used > height + EPS:
            raise _Infeasible("spine needs %.0f ft depth, has %.0f ft"
                              % (used, height))
        notes.append("Spine rooms fill %.0f of %.0f ft; %.0f ft open "
                     "lobby at the back." % (used, height, height - used))
    rects, cursor = [], y0
    for room, depth in depths:
        rects.append(_as_rect(room, x0, cursor, width, depth))
        cursor += depth
    return rects, relaxed, tried


def _spine_rooms(buckets, living_out):
    """Spine rooms present, front-to-back (living out: foyer/dining/family)."""
    rooms = buckets["foyer"] + buckets["living"] + buckets["dining"] + \
        buckets["family"]
    if living_out:
        rooms = [r for r in rooms if _room_type(r) != "living room"]
    return sorted(rooms, key=lambda r: SPINE_ORDER.index(_room_type(r)))


def _living_out(buckets, center_w, avail, directives):
    """Living room leaves the spine for a side-strip front corner when the
    4-room spine cannot fit, when a wish combines it, or when the wished
    garden needs it outside. Returns (living_out, reason)."""
    if not buckets["living"]:
        return False, ""
    if any("living room" in pair for pair in directives["combine"]):
        return True, "combined with another space"
    if directives["garden"]:
        return True, "the wished garden needs it outside"
    need = 0.0
    rooms = buckets["foyer"] + buckets["living"] + buckets["dining"] + \
        buckets["family"]
    for room in rooms:
        preferred, relaxed = _depth_options(room, center_w)
        if not preferred and not relaxed:
            return True, "the 4-room spine is too long for the depth"
        need += min(preferred + relaxed)
    if need > avail + EPS:
        return True, "the 4-room spine is too long for the depth"
    return False, ""


def _bath_map(buckets, notes):
    """(attached baths per bedroom, loose baths, common toilet).

    The first non-attached bath is the common toilet (placed off the
    spine); the rest with no bedroom are loose (noted, placed mid-strip).
    """
    by_name = {bed["name"] for bed in buckets["bedrooms"]}
    bath_of, loose, common = {}, [], None
    for bath in buckets["bathrooms"]:
        host = bath.get("attached_to")
        kind = str(bath.get("bathroom_kind", "")).strip().lower()
        if kind != "attached" and common is None and host not in by_name:
            common = bath
        elif host in by_name:
            bath_of.setdefault(host, []).append(bath)
        else:
            loose.append(bath)
    if loose:
        notes.append("%s has no bedroom; placed mid-strip off the spine." %
                     ", ".join(b["name"] for b in loose))
    return bath_of, loose, common


def _place_garden(rects, living, strip_x0, strip_w, notes):
    """Wished garden in front of the living room (buffer to the street).

    Full strip width, up to 8 ft deep, inside the buildable front gap.
    Returns the garden rect, or None (noted) when no 5x5 spot is free.
    """
    gap = living["y"]
    if gap < 5 - EPS:
        notes.append("No room for the wished garden in front of %s; skipped."
                     % living["name"])
        return None
    garden = _as_rect({"name": "Garden", "type": "garden"},
                      strip_x0, 0.0, strip_w, min(gap, 8.0))
    garden["garden_for"] = living["name"]
    if any(_area_overlap(garden, other) > 0.01 for other in rects):
        notes.append("No clear spot for the wished garden; skipped.")
        return None
    rects.append(garden)
    notes.append("Garden placed in front of %s (%.0f x %.0f ft buffer)."
                 % (living["name"], garden["w"], garden["d"]))
    return garden


def _verify_open_plan(rects, valid_pairs, notes):
    """Note which wished combinations share a 6 ft+ opening (Day 3: no wall).

    Returns the achieved [(name_a, name_b)] pairs for the option record.
    """
    by_type = {}
    for rect in rects:
        by_type.setdefault(_room_type(rect), rect)
    achieved = []
    for pair in valid_pairs:
        first, second = by_type.get(pair[0]), by_type.get(pair[1])
        if first is None or second is None:
            continue
        shared = shared_wall(first, second)
        if shared >= 6 - EPS:
            notes.append("Open plan: %s + %s share %.0f ft (one gathering "
                         "space; wall omitted Day 3)."
                         % (first["name"], second["name"], shared))
            achieved.append((first["name"], second["name"]))
        else:
            notes.append("Open plan missed: %s + %s share only %.1f ft."
                         % (first["name"], second["name"], shared))
    return achieved


def _three_strip(buckets, build_w, build_d, kitchen_strip, master_strip,
                 notes, directives):
    """One three-strip option in buildable coords (rects, info, meta).

    Raises _Infeasible (geometry is hard) instead of placing anything
    outside the buildable area.
    """
    side_w, center_w, x0, _total, house_note = _strip_widths_three(build_w)
    if house_note:
        notes.append(house_note)
    y0 = _y0_porch(buckets)
    living_out, reason = _living_out(buckets, center_w, build_d - y0,
                                     directives)
    if living_out:
        notes.append("Living Room moves to a front corner (%s); the spine "
                     "holds foyer, dining, family." % reason)
    spine, relaxed, tried = _place_spine(
        _spine_rooms(buckets, living_out), x0 + side_w, center_w, y0,
        build_d - y0, notes)
    spans = _spine_spans(spine)
    variants, valid_pairs, _merge_lk = _assign_three_strip(
        buckets, kitchen_strip, master_strip, notes, directives, living_out)
    best, tried_all = None, tried
    for order in variants:
        living_side = None
        for index, slots in enumerate(order):
            if any(kind == "living" for kind, _r, _e in slots):
                living_side = index
        tribe, satisfied, tried_here, garden_ok = [], 0, tried_all, True
        try:
            for index, slots in enumerate(order):
                strip_x = x0 if index == 0 else x0 + side_w + center_w
                stacked = _stack_side(
                    slots, strip_x, side_w, build_d, spans, notes,
                    outer_east=(index == 1))
                if directives["garden"] and index == living_side:
                    # Garden gap only when it costs no doors (rooms win).
                    try:
                        reserved = _stack_side(
                            slots, strip_x, side_w, build_d, spans, notes,
                            outer_east=(index == 1), min_bottom=5.0)
                    except _Infeasible:
                        reserved = None
                    if reserved is not None:
                        tried_here += reserved[3]
                        if reserved[1] >= stacked[1]:
                            stacked = reserved
                        else:
                            garden_ok = False
                    else:
                        garden_ok = False
                placed, sat, _tot, count = stacked
                tribe.extend(placed)
                satisfied += sat
                tried_here += count
        except _Infeasible:
            continue  # this middle order cannot stack; try the next
        if best is None or satisfied > best[0]:
            best = (satisfied, tribe, tried_here, garden_ok, living_side)
    if best is None:
        raise _Infeasible("side rooms need more depth than %.0f ft" % build_d)
    _sat, sides, tried_all, garden_ok, living_side = best
    rects = spine + sides
    if directives["garden"] and garden_ok and living_side is not None:
        living = next(r for r in rects if r["type"] == "living room")
        strip_x = x0 if living_side == 0 else x0 + side_w + center_w
        _place_garden(rects, living, strip_x, side_w, notes)
    elif directives["garden"]:
        notes.append("No room for the wished garden; rooms kept.")
    _shell(rects, buckets, build_w, build_d, notes)
    achieved = _verify_open_plan(rects, valid_pairs, notes)
    house_w = 2 * side_w + center_w
    indoor = [r for r in rects
              if _room_type(r) not in ("porch", "veranda", "garden")]
    info = {"row_front_y": y0, "row_widths": [house_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried_all, "relaxed": relaxed,
                         "typology": "three-strip", "open_plan": achieved}


def _assign_two_strip(buckets, notes, kitchen_first, directives,
                      living_out):
    """Single side-strip order, back to front (narrow plots).

    Returns (slots, valid_pairs, merge_lk). The living room (when out of
    the spine) goes front-most; merged with the kitchen it sits directly
    below it (kitchen second-to-last), one open space.
    """
    beds = list(buckets["bedrooms"])
    master_name = beds[0]["name"] if beds else ""
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    living = buckets["living"][0] if buckets["living"] else None
    bath_of, loose, common = _bath_map(buckets, notes)
    valid_pairs = _valid_pairs(buckets, directives, notes)
    merge_lk = living_out and living is not None and kitchen is not None \
        and any("living room" in pair and "kitchen" in pair
                for pair in valid_pairs)
    slots = []

    def _bed_with_bath(bed):
        slots.append(("bedroom", bed, None))
        for bath in bath_of.get(bed["name"], []):
            slots.append(("bath", bath, _bath_extra(bath, master_name)))

    if beds:
        _bed_with_bath(beds[0])
    if len(beds) > 1:
        _bed_with_bath(beds[1])
    for bath in loose:
        slots.append(("common", bath, (5.0, False)))
    if merge_lk:
        if common is not None:
            slots.append(("common", common, (5.0, False)))
        slots.append(("kitchen", kitchen, None))
    elif kitchen_first:
        if kitchen is not None:
            slots.append(("kitchen", kitchen, None))
        if common is not None:
            slots.append(("common", common, (5.0, False)))
    else:
        if common is not None:
            slots.append(("common", common, (5.0, False)))
        if kitchen is not None:
            slots.append(("kitchen", kitchen, None))
    for bed in beds[2:]:
        _bed_with_bath(bed)
    if living_out and living is not None and not merge_lk:
        slots.append(("living", living, None))
    if merge_lk:
        slots.append(("living", living, None))
    return slots, valid_pairs, merge_lk


def _two_strip(buckets, build_w, build_d, side_west, kitchen_first,
               notes, directives):
    """One two-strip option in buildable coords (rects, info, meta).

    Raises _Infeasible (geometry is hard) instead of placing anything
    outside the buildable area.
    """
    center_w, side_w, x0, _total = _strip_widths_two(build_w)
    if side_west:
        side_x, spine_x = x0, x0 + side_w
    else:
        spine_x, side_x = x0, x0 + center_w
    y0 = _y0_porch(buckets)
    living_out, reason = _living_out(buckets, center_w, build_d - y0,
                                     directives)
    if living_out:
        notes.append("Living Room moves to a front corner (%s); the spine "
                     "holds foyer, dining, family." % reason)
    spine, relaxed, tried = _place_spine(
        _spine_rooms(buckets, living_out), spine_x, center_w, y0,
        build_d - y0, notes)
    spans = _spine_spans(spine)
    slots, valid_pairs, _merge_lk = _assign_two_strip(
        buckets, notes, kitchen_first, directives, living_out)
    has_living = any(kind == "living" for kind, _r, _e in slots)
    garden_ok = True
    stacked = _stack_side(slots, side_x, side_w, build_d, spans, notes,
                          outer_east=not side_west)
    if directives["garden"] and has_living:
        # Garden gap only when it costs no doors (rooms win).
        try:
            reserved = _stack_side(slots, side_x, side_w, build_d, spans,
                                   notes, outer_east=not side_west,
                                   min_bottom=5.0)
        except _Infeasible:
            reserved = None
        extra = reserved[3] if reserved is not None else 0
        if reserved is not None and reserved[1] >= stacked[1]:
            stacked = reserved
        else:
            garden_ok = False
    else:
        extra = 0
    sides, _sat, _tot, count = stacked
    count += extra
    rects = spine + sides
    if directives["garden"] and garden_ok and has_living:
        living = next(r for r in rects if r["type"] == "living room")
        _place_garden(rects, living, side_x, side_w, notes)
    elif directives["garden"]:
        notes.append("No room for the wished garden; rooms kept.")
    _shell(rects, buckets, build_w, build_d, notes)
    achieved = _verify_open_plan(rects, valid_pairs, notes)
    indoor = [r for r in rects
              if _room_type(r) not in ("porch", "veranda", "garden")]
    info = {"row_front_y": y0, "row_widths": [center_w + side_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried + count, "relaxed": relaxed,
                         "typology": "two-strip", "open_plan": achieved}


def _row_widths_l(rooms, target, depth, notes):
    """Valid 0.5-ft widths filling target (relaxed living/family if needed).

    Returns ([(room, width)], [relaxed names]) or (None, []) when the row
    cannot fill the target exactly.
    """
    for attempt in (False, True):  # preferred first, then relaxed
        boxes = []
        for room in rooms:
            kind = _room_type(room)
            low, high = _type_range(kind)
            if attempt and kind in RELAXED_RANGES:
                low, high = RELAXED_RANGES[kind]
            boxes.append((low, high, _pref(room, "width_ft", kind)))
        widths = _branch_fill(boxes, target, depth)
        if widths is None:
            continue
        widths = _round_half(widths, boxes, depth, target)
        if widths is None:
            continue
        used_relaxed = []
        for room, width in zip(rooms, widths):
            low, high = _type_range(_room_type(room))
            if width < low - EPS or width > high + EPS:
                used_relaxed.append(room["name"])
        for name in used_relaxed:
            notes.append("%s uses a relaxed size (bend, -2)." % name)
        return list(zip(rooms, widths)), used_relaxed
    return None, []


def _grow_stack(options_list, avail):
    """Depths from per-room options filling avail (min, then grow 0.5)."""
    depths = [min(options) for options in options_list]
    if sum(depths) > avail + EPS:
        return None
    grown = True
    while grown:
        grown = False
        for index, options in enumerate(options_list):
            bigger = [d for d in options if d > depths[index] + EPS]
            if bigger and sum(depths) - depths[index] + min(bigger) <= avail:
                depths[index] = min(bigger)
                grown = True
    return depths


def _try_l_combo(buckets, wing_a, build_w, build_d, wing_b_w, wing_a_d, y0,
                 notes, directives, valid_pairs):
    """One L wing-size combo; (rects, info, relaxed, achieved) or None."""
    target = build_w - wing_b_w
    row, relaxed = _row_widths_l(wing_a, target, wing_a_d, notes)
    if row is None:
        return None
    rects, cursor = [], wing_b_w
    for room, width in row:
        rects.append(_as_rect(room, cursor, y0, width, wing_a_d))
        cursor += width
    family = buckets["family"][0] if buckets["family"] else None
    if family is None:
        return None
    bath_of, loose, common = _bath_map(buckets, notes)
    min_fam = wing_a_d + (3.0 if common is not None else 0.0)
    fam_pref, fam_relax = _depth_options(family, wing_b_w)
    fam_options = [(d, False) for d in fam_pref
                   if d >= min_fam - EPS]
    fam_options += [(d, True) for d in fam_relax if d >= min_fam - EPS]
    if not fam_options:
        return None
    fam_d, fam_flag = min(fam_options)
    if fam_flag:
        relaxed = relaxed + [family["name"]]
        notes.append("%s uses a relaxed size (bend, -2)." % family["name"])
    rects.append(_as_rect(family, 0.0, y0, wing_b_w, fam_d))
    master_name = buckets["bedrooms"][0]["name"] if buckets["bedrooms"] else ""
    above = []
    for bed in buckets["bedrooms"]:
        above.append((bed, None))
        for bath in bath_of.get(bed["name"], []):
            above.append((bath, _bath_extra(bath, master_name)))
    for bath in loose:
        above.append((bath, (5.0, False)))
    options_list = []
    for room, bath_info in above:
        if bath_info is not None:
            width = bath_info[0]
            low, high = MASTER_TOILET_D_RANGE if bath_info[1] \
                else TOILET_D_RANGE
        else:
            width = wing_b_w
            low, high = _type_range(_room_type(room))
        options = [d / 2 for d in range(int(low * 2), int(high * 2) + 1)
                   if abs(d / 2 - width) >= 1 - EPS]
        if not options:
            return None
        options_list.append(options)
    avail = build_d - (y0 + fam_d)
    depths = _grow_stack(options_list, avail) if options_list else []
    if depths is None:
        return None
    cursor = y0 + fam_d
    for (room, bath_info), depth in zip(above, depths):
        if bath_info is not None:
            bath_w = bath_info[0]
            rects.append(_as_rect(room, 0.0, cursor, bath_w, depth))
            filler_w = wing_b_w - bath_w
            rects.append(_as_rect(
                {"name": "Wardrobe (%s)" % room["name"], "type": "wardrobe",
                 "width_range": [filler_w, filler_w],
                 "depth_range": [depth, depth]},
                bath_w, cursor, filler_w, depth))
        else:
            rects.append(_as_rect(room, 0.0, cursor, wing_b_w, depth))
        cursor += depth
    if common is not None:
        placed = None
        for cw, cd in ((5, 7), (6, 7), (5, 7.5), (6, 7.5),
                       (5, 8), (6, 8), (5, 6), (6, 8.5)):
            if wing_b_w + cw <= build_w + EPS and \
                    y0 + wing_a_d + cd <= build_d + EPS:
                placed = (cw, cd)
                break
        if placed is None:
            return None
        cw, cd = placed
        rects.append(_as_rect(common, wing_b_w, y0 + wing_a_d, cw, cd))
    if directives["garden"]:
        living = next((r for r in rects if r["type"] == "living room"), None)
        if living is not None and y0 >= 5 - EPS:
            garden = _as_rect({"name": "Garden", "type": "garden"},
                              living["x"], 0.0, living["w"], min(y0, 8.0))
            garden["garden_for"] = living["name"]
            if all(_area_overlap(garden, other) < 0.01 for other in rects):
                rects.append(garden)
                notes.append("Garden placed in front of %s (%.0f x %.0f ft "
                             "buffer)." % (living["name"], garden["w"],
                                            garden["d"]))
            else:
                notes.append("No clear spot for the wished garden; skipped.")
        else:
            notes.append("No room for the wished garden; rooms kept.")
    _shell(rects, buckets, build_w, build_d, notes)
    achieved = _verify_open_plan(rects, valid_pairs, notes)
    indoor = [r for r in rects
              if _room_type(r) not in ("porch", "veranda", "garden")]
    info = {"row_front_y": y0, "row_widths": [build_w, wing_b_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, relaxed, achieved


def _try_l_shape(buckets, build_w, build_d, notes, directives):
    """L-shape with court; (rects, info, meta) or None when nothing fits.

    Failed combos leave no notes behind (scratch list, kept on success).
    A wished living+kitchen combination reorders the front wing so the
    two sit adjacent (one open space).
    """
    if build_w < 45 - EPS:
        return None
    y0 = _y0_porch(buckets)
    wing_a = buckets["foyer"] + buckets["living"] + buckets["dining"] + \
        buckets["kitchen"][:1]
    present = {_room_type(r) for r in wing_a}
    merge_lk = any("living room" in pair and "kitchen" in pair
                   for pair in directives["combine"]
                   if pair[0] in present and pair[1] in present)
    order = ("foyer", "dining", "living room", "kitchen") if merge_lk \
        else ("foyer", "living room", "dining", "kitchen")
    wing_a = sorted(wing_a, key=lambda r: order.index(_room_type(r)))
    tried = 0
    for wing_b_w in (12, 13, 14, 11, 10):
        for wing_a_d in (12, 13, 14):
            tried += 1
            scratch = []
            valid_pairs = _valid_pairs(buckets, directives, scratch)
            result = _try_l_combo(buckets, wing_a, build_w, build_d,
                                  float(wing_b_w), float(wing_a_d), y0,
                                  scratch, directives, valid_pairs)
            if result is not None:
                rects, info, relaxed, achieved = result
                notes.extend(scratch)
                notes.append("Open court fills the L's back-east corner.")
                return rects, info, {"tried": tried, "relaxed": relaxed,
                                     "typology": "l-shape",
                                     "open_plan": achieved}
    return None


def _finish_option(rects, info, meta, label, title, build_w, build_d, road,
                   num_toilets, notes):
    """Check, score and shift one option to plot-local coordinates."""
    rules, goals, quality = _check_all(rects, info, build_w, build_d, road,
                                       num_toilets)
    score = _score(rules, goals, quality)
    livable, fails = livability_verdict(rules)
    shifted = []
    for rect in rects:
        moved = dict(rect)
        moved["x"] += SETBACK_SIDE_FT
        moved["y"] += SETBACK_FRONT_FT
        shifted.append(moved)
    return {"label": label, "title": title, "typology": meta["typology"],
            "placements": shifted, "rules": rules, "goals": goals,
            "score": score, "livable": livable, "livability_fails": fails,
            "notes": list(notes), "tried": meta["tried"],
            "relaxed": list(meta.get("relaxed", [])),
            "open_plan": list(meta.get("open_plan", []))}


def _option_specs(buckets, build_w, build_d, road, directives):
    """(label, title, builder) for A/B/C (builders take a notes list)."""
    if build_w < 30 - EPS:
        def _build_c_two(notes):
            if directives["combine"]:
                notes.append("Option C keeps rooms separate (compare with "
                             "the open plan).")
            plain = dict(directives, combine=[])
            return _two_strip(buckets, build_w, build_d, True, False, notes,
                              plain)

        return [
            ("A", "Two-strip, rooms west",
             lambda n: _two_strip(buckets, build_w, build_d, True, True, n,
                                  directives)),
            ("B", "Two-strip, rooms east",
             lambda n: _two_strip(buckets, build_w, build_d, False, True, n,
                                  directives)),
            ("C", "Two-strip, rooms west (alt order)", _build_c_two),
        ]
    west = _west_strip_index(road)
    kitchen_a = west if west is not None else 0
    west_word = "west" if west is not None else "road-left"
    east_word = "east" if west is not None else "road-right"

    def _build_c(notes):
        found = _try_l_shape(buckets, build_w, build_d, notes, directives)
        if found is not None:
            return found
        notes.append("L-shape does not fit this brief; "
                     "third three-strip variant instead.")
        return _three_strip(buckets, build_w, build_d, kitchen_a, kitchen_a,
                            notes, directives)

    return [
        ("A", "Three-strip, kitchen %s" % west_word,
         lambda n: _three_strip(buckets, build_w, build_d, kitchen_a,
                                2 - kitchen_a, n, directives)),
        ("B", "Three-strip, kitchen %s" % east_word,
         lambda n: _three_strip(buckets, build_w, build_d, 2 - kitchen_a,
                                kitchen_a, n, directives)),
        ("C", "L-shape with court" if build_w >= 45 - EPS
         else "Three-strip, kitchen + master %s" % west_word,
         _build_c),
    ]


def build_options(program_rooms, plot_width, plot_depth, road_side,
                  num_toilets, wishes=""):
    """Three typology options (A/B/C) for the brief, checked and scored.

    Wishes shape the layout (combined spaces, wished garden). Geometry
    is a hard constraint: an option that cannot fit inside the buildable
    area is skipped with a clear reason, never drawn broken.
    """
    road = (road_side or "south").lower()
    plot_w, plot_d, build_w, build_d = _local_dims(plot_width, plot_depth,
                                                   road)
    result = {"plot": {"width": plot_w, "depth": plot_d, "road": road},
              "buildable": {"width": build_w, "depth": build_d},
              "options": [], "notes": []}
    if build_w <= 0 or build_d <= 0:
        result["notes"].append("Buildable area is zero or negative; "
                               "setbacks leave no room to build.")
        return result
    buckets, bucket_notes = _buckets(program_rooms)
    result["notes"].extend(bucket_notes)
    directives = _parse_wishes(wishes)
    result["notes"].extend(directives["notes"])
    if build_w >= 30 - EPS and _west_strip_index(road) is None:
        result["notes"].append("Compass west points front/back on east/west "
                               "roads: Option A uses the road-left strip.")
    for label, title, builder in _option_specs(buckets, build_w, build_d,
                                               road, directives):
        notes = []
        try:
            rects, info, meta = builder(notes)
        except _Infeasible as exc:
            result["notes"].append("Option %s skipped: %s." % (label, exc))
            continue
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            notes.append("Option %s failed to build (%s)." % (label, exc))
            continue
        result["options"].append(_finish_option(
            rects, info, meta, label, title, build_w, build_d, road,
            num_toilets, notes))
    return result
