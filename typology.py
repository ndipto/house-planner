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
import math
import re

from ai_program import (
    MASTER_TOILET_D_RANGE,
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    TOILET_D_RANGE,
)
from openings import ROOM_W_FT
from openings import _shared_with as _wall_runs
from layout import (
    BEDROOM_MIN_WINDOW_FT,
    EPS,
    RELAXED_RANGES,
    _add_porch,
    _add_verandas,
    _area_overlap,
    _as_rect,
    _bearing_name,
    _branch_fill,
    _buckets,
    _by_name,
    _check_all,
    _closest_road,
    _closest_side,
    _exterior_walls,
    _porch_size,
    _resolve_angle,
    _side_bearings,
    _pref,
    _room_type,
    _round_half,
    _score,
    _shared_wall_and_span,
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

# "Combined X and Y", "X and Y as one (big) space", "open-plan X and Y",
# bare "open X and Y" (last: most general, deduped against the above).
_COMBINE_PATTERNS = (
    r"combin\w*\s+(?:the\s+)?([a-z ]+?)\s+and\s+(?:the\s+)?([a-z ]+?)"
    r"(?:[.,;]|$| as | into | to )",
    r"([a-z ]+?)\s+and\s+([a-z ]+?)\s+as\s+one(?:\s+\w+)?\s+space",
    r"open[\s-]?plan\s+(?:the\s+)?([a-z ]+?)\s+and\s+(?:the\s+)?"
    r"([a-z ]+?)(?:[.,;]|$)",
    r"open\s+(?:the\s+)?([a-z ]+?)\s+and\s+(?:the\s+)?([a-z ]+?)"
    r"(?:[.,;]|$| for | with | during | as )",
)

# "X near Y" (proximity: a door-able shared wall).
_NEAR_PATTERN = (r"([a-z ]+?)\s+near\s+(?:the\s+)?([a-z ]+?)"
                 r"(?:[.,;]|$| and | for | with | during )")

# "South facing master bedroom", "kitchen facing west".
_FACING_PATTERNS = (
    (r"(north|south|east|west)[- ]facing\s+(?:the\s+)?([a-z ]+?)"
     r"(?:[.,;]|$| and | with | which | that | as )", True),
    (r"([a-z ]+?)\s+facing\s+(?:to\s+)?(?:the\s+)?"
     r"(north|south|east|west)\b", False),
)

# Compass words -> bearings for facing wishes.
_FACING_BEARINGS = {"north": 0.0, "east": 90.0, "south": 180.0,
                    "west": 270.0}


def _facing_target(compass, north_angle):
    """("strip", 0/1) or ("position", "front"/"back") for a compass wish.

    Uses the real north angle: whichever local side is closest to the
    wished direction wins.
    """
    side = _closest_side(north_angle,
                         _FACING_BEARINGS.get(compass, 180.0))
    if side == "lowx":
        return ("strip", 0)
    if side == "highx":
        return ("strip", 1)
    if side == "front":
        return ("position", "front")
    return ("position", "back")


def _wish_room(phrase):
    """Map a wish phrase to a room type (None when no room word matches)."""
    words = " %s " % re.sub(r"[^a-z ]", " ", phrase.strip().lower())
    for key in sorted(_WISH_ROOMS, key=len, reverse=True):
        if " %s " % key in words:
            return _WISH_ROOMS[key]
    return None


def _parse_wishes(wishes):
    """Parse client wishes into layout directives.

    Returns {"combine": [(type_a, type_b)], "glass": [(type_a, type_b)],
    "refused": [(type_a, type_b)], "garden": bool,
    "facing": [{"room", "side", "master", "second", "phrase"}],
    "near": [{"room", "near", "master", "phrase"}], "notes": []}.
    Bedroom combinations are refused (privacy); kitchen combinations
    become glass partitions to dining/family (the kitchen always stays
    enclosed and never connects to the living room); unknown rooms are
    noted and skipped. The garden always sits beside the living room
    for now. Facing wishes ("south facing master bedroom") place that
    bedroom on the correct real-world side. Near wishes ("a bedroom
    near family living") are evaluated, not placed.
    """
    text = (wishes or "").strip().lower()
    directives = {"combine": [], "glass": [], "refused": [],
                  "garden": False, "facing": [], "near": [],
                  "notes": []}
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
            if "kitchen" in rooms:
                other = rooms[1] if rooms[0] == "kitchen" else rooms[0]
                pair = tuple(sorted(rooms))
                directives["combine"].append(pair)
                if other == "living room":
                    directives["refused"].append(pair)
                    if ("kitchen", "dining") not in directives["glass"]:
                        directives["glass"].append(("kitchen", "dining"))
                    directives["notes"].append(
                        "The kitchen always stays enclosed (Bangladeshi "
                        "cooking) and never connects to the living room; "
                        "it joins dining with a glass partition instead.")
                elif other in ("dining", "family living"):
                    if pair not in directives["glass"]:
                        directives["glass"].append(pair)
                else:
                    directives["refused"].append(pair)
                    directives["notes"].append(
                        "The kitchen combines only with dining or family "
                        "living (glass partition); '%s and %s' skipped."
                        % (first.strip(), second.strip()))
                continue
            directives["combine"].append(tuple(sorted(rooms)))
    seen_facing = set()
    for pattern, compass_first in _FACING_PATTERNS:
        for first, second in re.findall(pattern, text):
            compass, phrase = (first, second) if compass_first \
                else (second, first)
            room = _wish_room(phrase)
            key = (room, compass)
            if key in seen_facing:
                continue
            seen_facing.add(key)
            if room is None:
                directives["notes"].append(
                    "Could not match a room in '%s facing'; skipped."
                    % phrase.strip())
                continue
            clean = re.sub(r"[^a-z ]", " ", phrase.strip().lower())
            directives["facing"].append({
                "room": room, "side": compass,
                "master": "master" in clean,
                "second": any(word in clean for word in
                              ("second", "other", "guest", "kids",
                               "children")),
                "phrase": phrase.strip(),
            })
    seen_near = set()
    for first, second in re.findall(_NEAR_PATTERN, text):
        if any(word in first for word in ("garden", "courtyard", "lawn")):
            continue  # the garden wish, not proximity
        rooms = (_wish_room(first), _wish_room(second))
        if (rooms[0], rooms[1]) in seen_near:
            continue
        seen_near.add((rooms[0], rooms[1]))
        if rooms[0] is None or rooms[1] is None:
            directives["notes"].append(
                "Could not match rooms in '%s near %s'; skipped."
                % (first.strip(), second.strip()))
            continue
        clean = re.sub(r"[^a-z ]", " ", first.strip().lower())
        directives["near"].append(
            {"room": rooms[0], "near": rooms[1],
             "master": "master" in clean,
             "phrase": "%s near %s" % (first.strip(), second.strip())})
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


def _local_dims(frontage_ft, depth_ft):
    """Plot-local extents + buildable: x along frontage, y road-inward.

    Inputs are road-relative (frontage = road side), so no compass swap:
    the road side only rotates the drawing and sets real orientation.
    """
    plot_w, plot_d = float(frontage_ft), float(depth_ft)
    build_w = plot_w - SETBACK_SIDE_FT * 2
    build_d = plot_d - SETBACK_FRONT_FT - SETBACK_BACK_FT
    return plot_w, plot_d, build_w, build_d


def _west_strip_index(north_angle):
    """Strip index on the compass-west side (None: west runs front-back).

    Uses the real north angle: when a side strip (low/high x) is the
    closest side to west it wins (strip 0/2); when west points
    front/back no strip is "west".
    """
    side = _closest_side(north_angle, 270.0)
    if side == "lowx":
        return 0
    if side == "highx":
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


def _present_types(buckets):
    """Room types available to wishes in this program."""
    return {_room_type(r) for key in
            ("foyer", "living", "kitchen", "dining", "family")
            for r in buckets[key]}


def _valid_pairs(buckets, directives, notes):
    """Wished combine pairs whose rooms are both in the program (noted).

    Kitchen pairs verify through glass partitions, refused pairs never
    verify, so both stay out of the open-plan check.
    """
    present = _present_types(buckets)
    refused = set(directives.get("refused", []))
    valid = []
    for pair in directives["combine"]:
        if pair in refused or "kitchen" in pair:
            continue
        if pair[0] in present and pair[1] in present:
            valid.append(pair)
        else:
            notes.append("Wish needs %s + %s; not in the program, skipped."
                         % pair)
    return valid


def _face_assign(beds, facing):
    """[(wish, bed_index)] for bedroom facing wishes (pure, no notes).

    Master wishes take beds[0], second/other/guest beds[1], the rest the
    next free bedroom; index None when no bedroom is left for the wish.
    """
    assigned, taken = [], set()
    for wish in facing:
        if wish["room"] != "bedroom":
            continue
        if wish["master"]:
            index = 0 if beds else None
        elif wish["second"] and len(beds) > 1:
            index = 1
        else:
            free = [i for i in range(len(beds)) if i not in taken]
            index = free[0] if free else None
        if index is not None:
            taken.add(index)
        assigned.append((wish, index))
    return assigned


def _side_wall(compass, angle):
    """Local wall letter (W/E/S/N) closest to a compass wish (None: unknown)."""
    if compass not in _FACING_BEARINGS:
        return None
    side = _closest_side(angle, _FACING_BEARINGS[compass])
    return {"lowx": "W", "highx": "E", "front": "S", "back": "N"}[side]


def _wish_walls(beds, facing, road, north_angle):
    """{bed name: local wall} putting verandas on the wished side.

    A "south facing master" wish orders the master's veranda walls so
    the real-south side is tried first (wishes override zoning, even on
    the road side). Later wishes for the same bed keep the first wall.
    """
    angle = _resolve_angle(road, north_angle)
    walls, seen = {}, set()
    for wish, index in _face_assign(beds, facing):
        if index is None or index >= len(beds) or index in seen:
            continue
        wall = _side_wall(wish["side"], angle)
        if wall is None:
            continue
        seen.add(index)
        walls[beds[index]["name"]] = wall
    return walls


def _wishes_table(rects, meta, buckets, directives, road, north_angle):
    """Per-option client-wishes table + ranking counts.

    Combine wishes are MET when the pair shares an open plan (kitchen
    pairs verify through glass partitions instead, and refused pairs
    read SKIPPED); facing wishes when the bedroom has a window-able
    (6 ft+) exterior wall on the wished side (its veranda is ordered
    there best-effort); near wishes when a door-able (3.5 ft+) wall is
    shared; the garden wish when a garden is placed. Pairs outside the
    program and wishes for missing rooms are SKIPPED (noted at
    parse/place time, never ranked). Returns (rows, met, total): total
    counts MET + NOT MET only, so skipped wishes never rank an option
    down.
    """
    rows = []
    achieved = set()
    for first, second in meta.get("open_plan", []):
        pair_rects = [_by_name(rects, name) for name in (first, second)]
        if all(pair_rects):
            achieved.add(tuple(sorted(_room_type(r) for r in pair_rects)))
    glass_done = set()
    for first, second in meta.get("glass", []):
        pair_rects = [_by_name(rects, name) for name in (first, second)]
        if all(pair_rects):
            glass_done.add(tuple(sorted(_room_type(r) for r in pair_rects)))
    valid = _valid_pairs(buckets, directives, [])
    refused = set(directives.get("refused", []))
    present = _present_types(buckets)
    for pair in directives["combine"]:
        if "kitchen" in pair:
            text = "Glass partition: %s + %s" % pair
            if pair in refused or pair[0] not in present \
                    or pair[1] not in present:
                rows.append((text, "SKIPPED"))
            elif tuple(sorted(pair)) in glass_done:
                rows.append((text, "MET"))
            else:
                rows.append((text, "NOT MET"))
            continue
        text = "Open plan: %s + %s" % pair
        if pair not in valid:
            rows.append((text, "SKIPPED"))
        elif tuple(sorted(pair)) in achieved:
            rows.append((text, "MET"))
        else:
            rows.append((text, "NOT MET"))
    angle = _resolve_angle(road, north_angle)
    beds = buckets["bedrooms"]
    for wish in directives["facing"]:
        if wish["room"] != "bedroom":
            rows.append(("%s-facing %s" % (wish["side"], wish["phrase"]),
                         "SKIPPED"))
    for wish, index in _face_assign(beds, directives["facing"]):
        text = "%s-facing %s" % (wish["side"], wish["phrase"])
        wall = _side_wall(wish["side"], angle)
        bed = _by_name(rects, beds[index]["name"]) \
            if index is not None and index < len(beds) else None
        if bed is None or wall is None:
            rows.append((text, "SKIPPED"))
            continue
        others = [r for r in rects if r.get("veranda_for") != bed["name"]]
        ext = _exterior_walls(bed, others).get(wall, 0.0)
        rows.append((text, "MET"
                     if ext >= BEDROOM_MIN_WINDOW_FT - EPS else "NOT MET"))
    for wish in directives["near"]:
        if wish["room"] == "bedroom":
            if wish["master"]:
                group_a = [_by_name(rects, beds[0]["name"])] if beds else []
            else:
                group_a = [_by_name(rects, bed["name"]) for bed in beds]
            group_a = [r for r in group_a if r is not None]
            label = ("Master bedroom" if wish["master"] else "Bedroom") \
                + " near " + wish["near"]
        else:
            group_a = [r for r in rects if _room_type(r) == wish["room"]]
            label = wish["room"].capitalize() + " near " + wish["near"]
        group_b = [r for r in rects if _room_type(r) == wish["near"]]
        if not group_a or not group_b:
            rows.append((label, "SKIPPED"))
            continue
        near = any(shared_wall(a, b) >= 3.5 - EPS
                   for a in group_a for b in group_b)
        rows.append((label, "MET" if near else "NOT MET"))
    if directives["garden"]:
        rows.append(("Garden with the living room", "MET"
                     if any(r["type"] == "garden" and r.get("garden_for")
                             for r in rects)
                     else "NOT MET"))
    met = sum(1 for _wish, status in rows if status == "MET")
    total = sum(1 for _wish, status in rows if status != "SKIPPED")
    return rows, met, total


def _bed_facing_plan(beds, facing, road, notes, single_side=None,
                     north_angle=None):
    """({bed_index: strip}, {bed_index: front/back}) from facing wishes.

    Only bedrooms move: a side wish (west/east on north/south roads)
    picks the strip, a front/back wish the end of the strip. Other rooms
    are noted and stay where the typology puts them. With single_side
    set (two-strip options), a side wish only matches or misses.
    """
    sides, positions, taken = {}, {}, set()
    angle = _resolve_angle(road, north_angle)
    for wish in facing:
        if wish["room"] != "bedroom":
            if wish["room"] == "kitchen":
                notes.append("Kitchen stays by the dining; facing wishes "
                             "are honored for bedrooms.")
            else:
                notes.append("%s stays on the public spine; facing wishes "
                             "are honored for bedrooms."
                             % wish["phrase"].strip().capitalize())
    for wish, index in _face_assign(beds, facing):
        if index is None or index >= len(beds):
            notes.append("No bedroom for '%s facing'; skipped."
                         % wish["phrase"].strip())
            continue
        if index in taken:
            notes.append("'%s facing' already placed; second wish skipped."
                         % wish["phrase"].strip())
            continue
        taken.add(index)
        kind, value = _facing_target(wish["side"], angle)
        if kind == "strip":
            if single_side is not None and value != single_side:
                notes.append("%s faces %s in the other side-strip option."
                             % (beds[index]["name"], wish["side"]))
                continue
            if single_side is not None:
                notes.append("%s on the %s side (client wish)."
                             % (beds[index]["name"], wish["side"]))
                continue
            sides[index] = value
        else:
            positions[index] = value
        notes.append("%s placed %s (client wish: %s facing)."
                     % (beds[index]["name"],
                        "on the %s side" % wish["side"] if kind == "strip"
                        else "%s-most" % ("front" if value == "front"
                                          else "back"),
                        wish["side"]))
    return sides, positions


def _front_wish(directives, road, north_angle=None):
    """True when a bedroom wish maps to the front end (rule-8 guard)."""
    angle = _resolve_angle(road, north_angle)
    return any(wish["room"] == "bedroom"
               and _facing_target(wish["side"], angle) == ("position", "front")
               for wish in directives["facing"])


def _relocate_block(side_list, bed_name, bath_names, to_front):
    """Move a bedroom + its baths to the front/back end of a slot list."""
    block = [slot for slot in side_list
             if slot[1].get("name") == bed_name
             or slot[1].get("name") in bath_names]
    if not block:
        return
    rest = [slot for slot in side_list if slot not in block]
    if to_front:
        side_list[:] = rest + block
    else:
        side_list[:] = block + rest


def _assign_three_strip(buckets, kitchen_strip, master_strip, notes,
                        directives, living_out, road, common_side=None,
                        north_angle=None):
    """Back-to-front slot lists ((west, east)) + valid pairs + merged flag.

    Master takes its back corner, second bedroom the other back corner,
    attached baths pin below their bedroom, kitchen goes mid-strip on
    its side, the common toilet mid-strip opposite. The living room (when
    out of the spine) takes a front corner: kitchen side when merged with
    the kitchen (directly below it, one open space), else the shorter
    side. Extra bedrooms stack front-ward (placed, reported honestly).
    Facing wishes override a bedroom's strip or end (road-aware). Each
    bed-with-baths also yields a bath-above-bed variant (bath at the
    back corner, bed mid-strip with more door slack); the common toilet
    also tries the other side (before the kitchen there, else after the
    beds), so a crowded side can shed it for bedroom doors. When the
    living room is out, the kitchen also tries below it (front-most,
    for its dining door). A top bedroom with its bath below and the
    common on the same side also tries a paired top band (bath +
    common side by side), freeing 6 ft below. Best wins.
    """
    kitchen_side = 0 if kitchen_strip == 0 else 1
    master_side = 0 if master_strip == 0 else 1
    other_side = 1 - kitchen_side
    explicit_common = common_side is not None
    if common_side is None:
        common_side = other_side
    beds = list(buckets["bedrooms"])
    master_name = beds[0]["name"] if beds else ""
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    living = buckets["living"][0] if buckets["living"] else None
    bath_of, loose_baths, common = _bath_map(buckets, notes)
    face_sides, face_positions = _bed_facing_plan(
        beds, directives["facing"], road, notes,
        north_angle=north_angle)
    valid_pairs = _valid_pairs(buckets, directives, notes)
    merge_lk = living_out and living is not None and kitchen is not None \
        and any("living room" in pair and "kitchen" in pair
                for pair in valid_pairs)
    sides = [[], []]

    def _bed_with_bath(bed, strip):
        sides[strip].append(("bedroom", bed, None))
        for bath in bath_of.get(bed["name"], []):
            sides[strip].append(("bath", bath, _bath_extra(bath, master_name)))

    master_actual = face_sides.get(0, master_side)
    for index, end in face_positions.items():
        if end != "front" or explicit_common:
            continue
        if index == 0:
            bed_side = master_actual
        elif index == 1:
            bed_side = face_sides.get(1, 1 - master_actual)
        else:
            bed_side = face_sides.get(index, other_side)
        if common_side == bed_side:
            common_side = 1 - bed_side
            notes.append("Common toilet moves opposite the front-most "
                         "bedroom (door reach).")
        break
    if beds:
        _bed_with_bath(beds[0], master_actual)
    if len(beds) > 1:
        _bed_with_bath(beds[1], face_sides.get(1, 1 - master_actual))
    # Two middle orders on the non-kitchen side (common above/below bed 3).
    middle_beds = beds[2:]
    variants = []
    for common_first in (True, False):
        order = [list(sides[0]), list(sides[1])]
        shared_side = common_side == kitchen_side
        if shared_side and common is not None:
            # Common first: it needs dining/family height, the kitchen
            # takes the front (its dining door bends, reported Day 3).
            order[common_side].append(("common", common, (5.0, False)))
            for bath in loose_baths:
                order[common_side].append(("common", bath, (5.0, False)))
        if kitchen is not None:
            order[kitchen_side].append(("kitchen", kitchen, None))
        middle = list(enumerate(middle_beds, start=2))
        if common is not None and not common_first and middle:
            (first_index, first), middle = middle[0], middle[1:]
            first_side = face_sides.get(first_index, other_side)
            order[first_side].append(("bedroom", first, None))
            for bath in bath_of.get(first["name"], []):
                order[first_side].append(
                    ("bath", bath, _bath_extra(bath, master_name)))
        if common is not None and not shared_side:
            order[common_side].append(("common", common, (5.0, False)))
        for index, bed in middle:
            bed_side = face_sides.get(index, other_side)
            order[bed_side].append(("bedroom", bed, None))
            for bath in bath_of.get(bed["name"], []):
                order[bed_side].append(
                    ("bath", bath, _bath_extra(bath, master_name)))
        if not shared_side:
            for bath in loose_baths:
                order[common_side].append(("common", bath, (5.0, False)))
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
        for index, end in face_positions.items():
            names = {b["name"] for b in
                     bath_of.get(beds[index]["name"], [])}
            for side_list in order:
                if any(slot[1].get("name") == beds[index]["name"]
                       for slot in side_list):
                    _relocate_block(side_list, beds[index]["name"], names,
                                    end == "front")
                    if end == "front":
                        # A front-most bedroom can place smaller than its
                        # siblings: its baths keep the standard range so
                        # rule 18 (master = largest placed) never trips.
                        for pos, slot in enumerate(side_list):
                            if slot[0] == "bath" \
                                    and slot[1]["name"] in names:
                                side_list[pos] = (
                                    "bath", slot[1], (slot[2][0], False))
                    break
        variants.append(order)
        if living_out:
            # Swapped kitchen/living: the kitchen also tries the
            # front-most slot (below the living room), so a deep stack
            # cannot strand it off dining (rule 4 is verdict-hard).
            for side_index, side_list in enumerate(order):
                kinds = [slot[0] for slot in side_list]
                if "kitchen" in kinds and "living" in kinds:
                    at_k = kinds.index("kitchen")
                    at_l = kinds.index("living")
                    if at_k < at_l:
                        flipped = [list(side) for side in order]
                        slots = flipped[side_index]
                        slots[at_k], slots[at_l] = slots[at_l], slots[at_k]
                        variants.append(flipped)
        for bed in beds:
            names = {b["name"] for b in bath_of.get(bed["name"], [])}
            if not names:
                continue
            for side_index, side_list in enumerate(order):
                at = [i for i, slot in enumerate(side_list)
                      if slot[1].get("name") == bed["name"]]
                if not at:
                    continue
                i = at[0]
                baths = side_list[i + 1:i + 1 + len(names)]
                if len(baths) != len(names) or any(
                        s[0] != "bath" or s[1].get("name") not in names
                        for s in baths):
                    continue  # baths not pinned below; leave this order
                swapped = [list(side) for side in order]
                swapped[side_index][i:i + 1 + len(names)] = \
                    baths + [side_list[i]]
                variants.append(swapped)
        # Paired top band: a top bedroom with its bath below and
        # the common on the same side tries bath + common side by
        # side (5 ft each) plus a dressing band (ensuite chain).
        for side_index, side_list in enumerate(order):


            if len(side_list) >= 2 and side_list[0][0] == "bedroom" \
                    and side_list[1][0] == "bath" \
                    and common is not None:
                bed = side_list[0][1]
                bath = side_list[1][1]
                if bath not in bath_of.get(bed["name"], []):
                    continue
                at_c = [i for i, slot in enumerate(side_list)
                        if slot[0] == "common"]
                if not at_c:
                    continue
                rest = [slot for i, slot in enumerate(side_list)
                        if i not in (1, at_c[0])]
                paired = [list(side) for side in order]
                paired[side_index] = [("pair", common, bath)] + rest
                variants.append(paired)
        if common is not None and not explicit_common:
            # Floated common: the common toilet also tries the other
            # side, so a crowded side can shed it for bedroom doors
            # (an explicitly placed common keeps its option identity).
            target = 1 - common_side
            for side_index, side_list in enumerate(order):
                at = [i for i, slot in enumerate(side_list)
                      if slot[0] == "common"
                      and slot[1].get("name") == common["name"]]
                if not at or side_index == target:
                    continue
                moved = [list(side) for side in order]
                del moved[side_index][at[0]:at[0] + 1]
                if target == kitchen_side:
                    kitchen_at = [j for j, slot in enumerate(moved[target])
                                  if slot[0] == "kitchen"]
                    pos = kitchen_at[0] if kitchen_at \
                        else len(moved[target])
                else:
                    pos = next((j for j, slot in enumerate(moved[target])
                                if slot[0] not in ("bedroom", "bath")),
                               len(moved[target]))
                moved[target][pos:pos] = [side_list[at[0]]]
                variants.append(moved)
        if common is not None and not explicit_common and not common_first:
            # Floated common, back corner: it also tries the top of
            # the other side (family zone), so the kitchen side sheds
            # it AND the common keeps its own door (its bottom slot
            # often lands in the foyer zone, doorless).
            target = 1 - common_side
            for side_index, side_list in enumerate(order):
                at = [i for i, slot in enumerate(side_list)
                      if slot[0] == "common"
                      and slot[1].get("name") == common["name"]]
                if not at or side_index == target:
                    continue
                moved_top = [list(side) for side in order]
                floated = moved_top[side_index].pop(at[0])
                moved_top[target].insert(0, floated)
                variants.append(moved_top)
        if len(beds) > 3 and 2 not in face_sides \
                and 2 not in face_positions:
            # Floated beds[2] (4+ beds only): the third bedroom tries
            # the kitchen side too, inserted before the kitchen, so one
            # side is not stacked doorless. Wishes pin it otherwise.
            names = {b["name"] for b in bath_of.get(beds[2]["name"], [])}
            for side_index, side_list in enumerate(order):
                at = [i for i, slot in enumerate(side_list)
                      if slot[1].get("name") == beds[2]["name"]]
                if not at or side_index == kitchen_side:
                    continue
                i = at[0]
                baths = side_list[i + 1:i + 1 + len(names)]
                if len(baths) != len(names) or any(
                        s[0] != "bath" or s[1].get("name") not in names
                        for s in baths):
                    continue
                moved = [list(side) for side in order]
                block = [side_list[i]] + baths
                del moved[side_index][i:i + len(block)]
                kitchen_at = [j for j, slot in enumerate(moved[kitchen_side])
                              if slot[0] == "kitchen"]
                at_k = kitchen_at[0] if kitchen_at \
                    else len(moved[kitchen_side])
                moved[kitchen_side][at_k:at_k] = block
                variants.append(moved)
    return variants, valid_pairs, merge_lk


def _slot_options(kind, room, strip_w, bath_info=None,
                  depth_bounds=None):
    """Depth options (0.5 ft) for one side-stack slot (valid only).

    Baths keep real widths (slot extra: width + master flag, never
    stretched); depths run the per-side toilet ranges. Other rooms span
    the strip full-width. depth_bounds caps {room_name: (lo, hi)} from
    the master-size second pass; [] when bounds leave nothing valid.
    """
    if kind in ("pair", "compact_pair"):
        # Paired top band (attached bath + common side by side, 5 ft
        # each, 6 ft deep) over a 2.5 ft dressing band (item 7: the
        # ensuite chain); fixed 8.5 ft, honoring second-pass bounds.
        width = 5.0
        low, high = 8.5, 8.5
        bounded = False
        if depth_bounds:
            for name in (room["name"], bath_info["name"]):
                if name in depth_bounds:
                    blo, bhi = depth_bounds[name]
                    low, high = max(low, blo), min(high, bhi)
                    bounded = True
    elif kind in ("bath", "common"):
        width = bath_info[0]
        if bath_info[1]:
            low, high = MASTER_TOILET_D_RANGE
        else:
            low, high = TOILET_D_RANGE
    else:
        width = strip_w
        low, high = _type_range(_room_type(room))
    if kind not in ("pair", "compact_pair"):
        bounded = depth_bounds and room["name"] in depth_bounds
    if bounded and kind not in ("pair", "compact_pair"):
        blo, bhi = depth_bounds[room["name"]]
        low, high = max(low, blo), min(high, bhi)
    options = []
    depth = low
    while depth <= high + EPS:
        if abs(depth - width) >= 1 - EPS:
            options.append(_half(depth))
        depth += 0.5
    if not options and bounded:
        return []
    if not options:  # best attempt: middle of range (checker reports it)
        options = [_half((low + high) / 2)]
    return options


def _stack_side(slots, strip_x0, strip_w, build_d, spans, notes,
                outer_east=False, min_bottom=0.0, depth_bounds=None,
                stack_top=None):
    """Stack slots back-anchored (top at stack_top); maximize door-touch.

    spans = {"foyer"/"dining"/"family"/"living": (y0, y1)} door-zones
    (the scorer keys foyer/dining/family; living is for circulation).
    Attached baths sit against the outer wall (east edge when outer_east)
    with a wardrobe/store filling the leftover width beside them; the
    common bath sits on the inner edge (direct spine door) with an open
    notch outside it (ventilation + outline break). A paired top
    band holds an attached bath + the common side by side (5 ft
    each; 10 ft strips only). Combos below
    min_bottom are rejected: geometry is a hard constraint (G), so an
    unstackable side raises _Infeasible instead of overflowing.
    Returns (rects, satisfied, total_targets, tried): every slot placed
    even when its door-zone is missed (reported, never dropped).
    depth_bounds ({room_name: (lo, hi)}) constrains one second pass.
    stack_top (default build_d) notches the back: the second pass tries
    slightly lower tops so a shrunk back bedroom keeps its door.
    """
    if strip_w != 10.0 \
            and any(kind in ("pair", "compact_pair")
                    for kind, _r, _e in slots):
        raise _Infeasible("paired baths need a 10 ft strip")
    option_lists = [_slot_options(kind, room, strip_w, extra,
                                  depth_bounds=depth_bounds)
                    for kind, room, extra in slots]
    if any(not options for options in option_lists):
        raise _Infeasible("depth bounds leave a room with no valid size")
    tried = 1
    for options in option_lists:
        tried *= len(options)
    top0 = build_d if stack_top is None else stack_top
    best = None
    for combo in itertools.product(*option_lists):
        heights = sum(combo)
        bottom = top0 - heights
        if bottom < min_bottom - EPS:
            continue  # hard floor: never below the plot (or garden gap)
        score, satisfied, total = 0.0, 0, 0
        top = top0
        for (kind, room, extra), depth in zip(slots, combo):
            keys = []
            if kind == "kitchen":
                keys = ["dining"]  # kitchen doors open into dining only
            elif kind in ("bedroom", "common", "pair", "compact_pair"):
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
                # 3 ft doors need 3.5 ft bearings (T returns); the
                # stacker bears 3.5 natively (the nudge only rescues 3.0).
                if kind == "kitchen":
                    need, pref = 3.5, 3.5
                elif kind == "bedroom":
                    need, pref = 3.5, 3.5
                else:
                    need, pref = 3.0, 3.0
                if reach >= need - EPS:
                    satisfied += 1
                    score += 100.0
                if kind == "kitchen":
                    # Verdict-hard bearing: chase dining steeply to the
                    # need, cosmetically after (size must never beat it).
                    score += min(reach, pref) * 10.0
                    score += max(0.0, reach - pref) * 2.0
                else:
                    score += reach * 2.0
                if overlaps[0] >= pref - EPS:
                    score += 1.0  # preferred door-zone (family / dining)
            top -= depth
        score -= max(0.0, bottom) * 0.05
        key = (satisfied, score)
        if best is None or key > best[0]:
            best = (key, combo, satisfied, total)
    if best is None:
        need = sum(min(options) for options in option_lists)
        raise _Infeasible("side rooms need at least %.0f ft depth, have "
                          "%.0f ft" % (need, top0 - min_bottom))
    _key, combo, satisfied, total = best
    rects = []
    top = top0
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
        elif kind == "compact_pair":
            # Compact solid pair (round 2 item 2): no dressing band -
            # the full 8.5 ft stays wet so the common reaches family.
            bath = extra
            if outer_east:
                bath_x, common_x = strip_x0 + strip_w - 5.0, strip_x0
            else:
                bath_x, common_x = strip_x0, strip_x0 + 5.0
            rects.append(_as_rect(bath, bath_x, bottom, 5.0, depth))
            rects.append(_as_rect(room, common_x, bottom, 5.0, depth))
        elif kind == "pair":
            # Paired top band: attached bath outer, common inner (the
            # variant sits at the back, so both keep north light); a
            # 2.5 ft dressing band below keeps the ensuite chain.
            bath = extra
            if outer_east:
                bath_x, common_x = strip_x0 + strip_w - 5.0, strip_x0
            else:
                bath_x, common_x = strip_x0, strip_x0 + 5.0
            rects.append(_as_rect(bath, bath_x, bottom + 2.5, 5.0,
                                  depth - 2.5))
            rects.append(_as_rect(room, common_x, bottom + 2.5, 5.0,
                                  depth - 2.5))
            rects.append(_as_rect({"name": "Wardrobe (%s)" % bath["name"],
                                   "type": "wardrobe",
                                   "width_range": [strip_w, strip_w],
                                   "depth_range": [2.5, 2.5]},
                                  strip_x0, bottom, strip_w, 2.5))
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
    """Door-zone y-spans of the placed spine rooms (dining/family/...).

    The stack scorer keys dining/family/foyer only; the fatal-miss
    check also uses the living span (a side room touching the spine
    living room still circulates).
    """
    spans = {}
    for rect in rects:
        kind = _room_type(rect)
        if kind == "dining":
            spans["dining"] = (rect["y"], rect["y"] + rect["d"])
        elif kind == "family living":
            spans["family"] = (rect["y"], rect["y"] + rect["d"])
        elif kind == "foyer":
            spans["foyer"] = (rect["y"], rect["y"] + rect["d"])
        elif kind == "living room":
            spans["living"] = (rect["y"], rect["y"] + rect["d"])
    return spans


def _y0_porch(buckets):
    """Front margin: porch depth (porch abuts the foyer), else 2 ft."""
    if not (buckets["porch"] or buckets["foyer"] or buckets["living"]):
        return 2.0
    program = buckets["porch"][0] if buckets["porch"] else None
    _width, depth = _porch_size(program)
    return depth


def _shell(rects, buckets, build_w, build_d, notes, wall_first=None):
    """Add porch + verandas to placed rooms (inside the buildable area)."""
    if buckets["porch"] or buckets["foyer"] or buckets["living"]:
        _add_porch(rects, buckets, build_w, notes, not buckets["porch"])
    _add_verandas(rects, _veranda_targets(buckets, rects, notes, wall_first),
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


def _spine_cap(spine_rooms, width):
    """Tallest preferred spine (foyer capped at 8, like the placer)."""
    total = 0.0
    for room in spine_rooms:
        preferred, relaxed = _depth_options(room, width)
        if _room_type(room) == "foyer":
            preferred = [d for d in preferred if d <= 8 + EPS]
        options = preferred or relaxed
        total += max(options) if options else 0.0
    return total


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
    depth = min(gap, 8.0)
    garden = _as_rect({"name": "Garden", "type": "garden"},
                      strip_x0, living["y"] - depth, strip_w, depth)
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


def _verify_glass(rects, buckets, directives, notes):
    """Note which glass partitions share a 6 ft+ run (slider fits).

    Returns the achieved [(name_a, name_b)] pairs for the option record.
    """
    by_type = {}
    for rect in rects:
        by_type.setdefault(_room_type(rect), rect)
    present = _present_types(buckets)
    achieved = []
    for pair in directives.get("glass", []):
        first, second = by_type.get(pair[0]), by_type.get(pair[1])
        if pair[0] not in present or pair[1] not in present:
            notes.append("Glass partition needs %s + %s; not in the "
                         "program, skipped." % pair)
            continue
        if first is None or second is None:
            continue
        shared = shared_wall(first, second)
        if shared >= 6 - EPS:
            notes.append("Glass partition: %s + %s share %.0f ft (sliding "
                         "glass door)." % (first["name"], second["name"],
                                            shared))
            achieved.append((first["name"], second["name"]))
        else:
            notes.append("Glass partition missed: %s + %s share only "
                         "%.1f ft." % (first["name"], second["name"],
                                       shared))
    return achieved


def _ceil_half(value):
    """Smallest 0.5-ft step covering value (float-dust safe)."""
    return math.ceil(value * 2 - EPS) / 2


def _floor_half(value):
    """Largest 0.5-ft step inside value (float-dust safe)."""
    return math.floor(value * 2 + EPS) / 2


def _master_bounds(placed, master_name):
    """Depth bounds forcing rule 19, or {} when the stack already passes.

    placed: pass-1 side rects. Other bedrooms trim only to what the
    master can cover at <= 15 ft deep while the master grows to 10%+
    over every other (same strip width, so depth decides); the master's
    attached baths keep at least the other attached baths' depths. The
    master never shrinks to equal: others shrink first. {} doubles as
    the already-ok signal.
    """
    if not master_name:
        return {}
    beds = [r for r in placed if _room_type(r) == "bedroom"]
    baths = [r for r in placed if r["type"] == "bathroom"]
    master = next((r for r in beds if r["name"] == master_name), None)
    others = [r for r in beds if r["name"] != master_name]
    need_master = master is not None and any(
        master["w"] * master["d"] < 1.1 * r["w"] * r["d"] - 0.01
        for r in others)
    master_baths = [r for r in baths
                    if r.get("attached_to") == master_name]
    other_baths = [r for r in baths
                   if r.get("bathroom_kind") == "attached"
                   and r.get("attached_to") != master_name]
    need_bath = bool(master_baths and other_baths) and \
        max(r["d"] for r in master_baths) < \
        max(r["d"] for r in other_baths) - 0.01
    if not need_master and not need_bath:
        return {}
    bounds = {}
    if need_master:
        # Least displacement: each other keeps its depth when the master
        # can cover it at <= 15 ft, else trims to what the master covers.
        caps = {}
        for room in others:
            top = _floor_half(15.0 * master["w"] / (1.1 * room["w"]))
            cap = min(room["d"], max(10.0, top))
            caps[room["name"]] = cap
            bounds[room["name"]] = (10.0, cap)
        need = max(1.1 * caps[r["name"]] * r["w"] / master["w"]
                   for r in others)
        bounds[master["name"]] = (max(10.0, _ceil_half(need)), 15.0)
    if need_bath:
        top = max(r["d"] for r in other_baths)
        for room in master_baths:
            bounds[room["name"]] = (top, 10.0)
        for room in other_baths:
            bounds[room["name"]] = (6.0, room["d"])
    return bounds


# Second-pass back notches: lower tops keep a shrunk back bedroom's door.
_PASS2_TOPS = tuple(-float(i) for i in range(13))


def _stack_with_garden(slots, strip_x, strip_w, build_d, spans, notes,
                       outer_east, base_min, want_garden,
                       depth_bounds=None, tops=(0.0,)):
    """Stack one side; garden gap only when it costs no doors (rooms win).

    tops: back-notch offsets tried (best satisfied wins, least notch
    breaks ties). Returns (stacked, garden_ok, tried): stacked is the
    _stack_side tuple, tried counts all attempts.
    """
    def _best_for(bottom):
        best, best_off, tried_here, last = None, 0.0, 0, None
        for offset in tops:
            try:
                cand = _stack_side(
                    slots, strip_x, strip_w, build_d, spans, notes,
                    outer_east=outer_east, min_bottom=bottom,
                    depth_bounds=depth_bounds,
                    stack_top=build_d + offset)
            except _Infeasible as exc:
                last = exc
                continue
            tried_here += cand[3]
            if best is None or (cand[1], offset) > (best[1], best_off):
                best, best_off = cand, offset
        return best, tried_here, last

    stacked, tried, last = _best_for(base_min)
    if stacked is None:
        raise last
    if not want_garden:
        return stacked, True, tried
    reserved, tried_r, _last = _best_for(max(5.0, base_min))
    tried += tried_r
    if reserved is not None and reserved[1] >= stacked[1]:
        return reserved, True, tried
    return stacked, False, tried


def _master_bounds_shrunk(tribe, master_name):
    """Fallback bounds: others to minimum, master compact (rule 19).

    The grow-master pass fails when the master cannot grow (pinned by
    wishes or the stack floor); this pass instead pins other bedrooms
    to 10-11 ft (10x10 is square on 10 ft strips) while the master
    takes 11+ ft, which still clears the 10% rule. Attached baths
    pin to 6 ft (the master bath stays joint-largest); {} when ok.
    """
    bounds = _master_bounds(tribe, master_name)
    if not bounds:
        return {}
    kinds = {r["name"]: r["type"] for r in tribe}
    shrunk = {}
    master_rect = next((r for r in tribe if r["name"] == master_name),
                       None)
    master_w = master_rect["w"] if master_rect else 10.0
    need_others = 0.0
    for rect in tribe:
        if rect["type"] == "bedroom" and rect["name"] != master_name:
            need_others = max(need_others, 1.1 * 11.0 * rect["w"] / master_w)
    need_master = max(11.0, _ceil_half(need_others)) if need_others else 11.0
    for name in bounds:
        if name == master_name:
            shrunk[name] = (need_master, 15.0)
        elif kinds.get(name) == "bedroom":
            shrunk[name] = (10.0, 11.0)
        else:
            shrunk[name] = (6.0, 6.0)
    return shrunk


def _fatal_count(order, tribe, spans):
    """Door misses that flip the verdict (rules 4/5/7/16 proxy, pre-shell).

    order: side slot lists; tribe: placed side rects (same names). Side
    slots span the full strip width, so y-overlap with the spine spans
    is the touch. A bedroom slot with < 3.5 ft (a common slot with
    < 3 ft) of family/dining reach fails rule 5/7; a kitchen slot

    off dining (< 3.5 ft) fails rule 4; an untouched living slot
    is unreachable (rule 16).
    Attached baths sit stack-adjacent to their bedroom by construction,
    so their rule-7 touch always holds.
    """
    by_name = {r["name"]: r for r in tribe}
    fatal = 0
    for slots in order:
        for kind, room, _extra in slots:
            rect = by_name.get(room["name"])
            if rect is None:
                continue
            y0, y1 = rect["y"], rect["y"] + rect["d"]
            if kind in ("bedroom", "common", "pair", "compact_pair"):
                need = 3.5 if kind == "bedroom" else 3.0
                reach = 0.0
                for key in ("family", "dining"):
                    if key in spans:
                        span = spans[key]
                        reach = max(reach, min(y1, span[1])
                                    - max(y0, span[0]))
                if reach < need - EPS:
                    fatal += 1
            elif kind == "kitchen":
                # Rule 4 is verdict-hard: the kitchen must bear 3.5 ft
                # on dining (the nudge only bridges an already-placed 3.0).
                if "dining" in spans:
                    span = spans["dining"]
                    reach = min(y1, span[1]) - max(y0, span[0])
                    if reach < 3.5 - EPS:
                        fatal += 1
                else:
                    touch = 0.0
                    for span in spans.values():
                        touch = max(touch, min(y1, span[1])
                                    - max(y0, span[0]))
                    if touch < 0.5:
                        fatal += 1
            elif kind == "living":
                touch = 0.0
                for span in spans.values():
                    touch = max(touch, min(y1, span[1]) - max(y0, span[0]))
                if touch < 0.5:
                    fatal += 1
    return fatal


def _stack_variant(order, x0, side_w, center_w, build_d, spans, notes,
                   base_min, directives, depth_bounds=None, tops=(0.0,)):
    """Stack both sides of one variant order (one pass).

    Returns (tribe, satisfied, tried, garden_ok, living_side).
    """
    living_side = None
    for index, slots in enumerate(order):
        if any(kind == "living" for kind, _r, _e in slots):
            living_side = index
    tribe, satisfied, tried, garden_ok = [], 0, 0, True
    for index, slots in enumerate(order):
        strip_x = x0 if index == 0 else x0 + side_w + center_w
        stacked, side_garden, adds = _stack_with_garden(
            slots, strip_x, side_w, build_d, spans, notes,
            outer_east=(index == 1), base_min=base_min,
            want_garden=bool(directives["garden"])
            and index == living_side,
            depth_bounds=depth_bounds, tops=tops)
        garden_ok = garden_ok and side_garden
        placed, sat, _tot, _tried = stacked
        tribe.extend(placed)
        satisfied += sat
        tried += adds
    return tribe, satisfied, tried, garden_ok, living_side


def _three_strip(buckets, build_w, build_d, kitchen_strip, master_strip,
                 notes, directives, road, common_side=None,
                 north_angle=None):
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
    rooms = _spine_rooms(buckets, living_out)
    height = min(build_d - y0, _spine_cap(rooms, center_w))
    spine, relaxed, tried = _place_spine(
        rooms, x0 + side_w, center_w, y0, height, notes)
    spans = _spine_spans(spine)
    variants, valid_pairs, _merge_lk = _assign_three_strip(
        buckets, kitchen_strip, master_strip, notes, directives, living_out,
        road, common_side, north_angle)
    base_min = y0 + 1.0 \
        if _front_wish(directives, road, north_angle) else 0.0
    master_name = buckets["bedrooms"][0]["name"] \
        if buckets["bedrooms"] else ""
    best, tried_all = None, tried
    for order in variants:
        try:
            tribe, satisfied, adds, garden_ok, living_side = \
                _stack_variant(order, x0, side_w, center_w, build_d,
                               spans, notes, base_min, directives)
        except _Infeasible:
            continue  # this middle order cannot stack; try the next
        fatal = _fatal_count(order, tribe, spans)
        bounds = _master_bounds(tribe, master_name)
        upgraded = False
        if bounds:
            # Second pass: master largest, others shrink first; keep it
            # when rule 19 holds with no new fatal door miss (soft
            # kitchen/living misses may trade for the hard size rule,
            # and so may the wished garden: hard rules beat wishes).
            garden1 = garden_ok
            try:
                second = _stack_variant(
                    order, x0, side_w, center_w, build_d, spans, notes,
                    base_min, directives, depth_bounds=bounds,
                    tops=_PASS2_TOPS)
            except _Infeasible:
                second = None
            fatal2 = _fatal_count(order, second[0], spans) \
                if second is not None else None
            if second is not None and fatal2 <= fatal \
                    and not _master_bounds(second[0], master_name):
                tribe, satisfied, adds, garden_ok, fatal = \
                    second[0], second[1], adds + second[2], second[3], \
                    fatal2
                upgraded = True
                if garden1 and not garden_ok:
                    notes.append("Garden dropped: the master-size rule "
                                 "wins (hard rules beat wishes).")


        if not upgraded:
            shrunk_bounds = _master_bounds_shrunk(tribe, master_name)
            if shrunk_bounds:
                # Fallback: the master cannot grow here; shrink the
                # others to minimum and let the master take 11+ ft.
                garden1 = garden_ok
                try:
                    second = _stack_variant(
                        order, x0, side_w, center_w, build_d, spans,
                        notes, base_min, directives,
                        depth_bounds=shrunk_bounds, tops=_PASS2_TOPS)
                except _Infeasible:
                    second = None
                fatal2 = _fatal_count(order, second[0], spans) \
                    if second is not None else None
                if second is not None and fatal2 <= fatal \
                        and not _master_bounds(second[0], master_name):
                    tribe, satisfied, adds, garden_ok, fatal = \
                        second[0], second[1], adds + second[2], \
                        second[3], fatal2
                    upgraded = True
                    if garden1 and not garden_ok:
                        notes.append("Garden dropped: the master-size "
                                     "rule wins (hard rules beat wishes).")
        kitchen_native = 0
        span = spans.get("dining")
        if span is not None:
            for rect in tribe:
                if rect.get("type") == "kitchen":
                    top = rect["y"] + rect["d"]
                    if min(top, span[1]) - max(rect["y"], span[0]) \
                            >= 3.5 - EPS:
                        kitchen_native = 1
        # Fewest fatal misses, rule-19 fix, garden, a native kitchen
        # bearing (3.5 ft beats nudge-bridged 3.0), most satisfied.
        key = (-fatal, not _master_bounds(tribe, master_name), garden_ok,
               kitchen_native,
               satisfied)
        if best is None or key > best[0]:
            best = (key, tribe, tried_all + adds, garden_ok, living_side,
                    upgraded)
    if best is None:
        raise _Infeasible("side rooms need more depth than %.0f ft" % build_d)
    _key, sides, tried_all, garden_ok, living_side, upgraded = best
    if upgraded:
        notes.append("Master kept largest (other rooms shrunk first).")
        side_top = {}
        for rect in sides:
            side = 0 if rect["x"] + rect["w"] <= x0 + side_w + EPS else 1
            side_top[side] = max(side_top.get(side, 0.0),
                                 rect["y"] + rect["d"])
        notch = max([build_d - top for top in side_top.values()] or [0.0])
        if notch > 0.25:
            notes.append("%d-ft back notch keeps bedroom doors."
                         % round(notch))
    rects = spine + sides
    if directives["garden"] and garden_ok and living_side is not None:
        living = next(r for r in rects if r["type"] == "living room")
        strip_x = x0 if living_side == 0 else x0 + side_w + center_w
        _place_garden(rects, living, strip_x, side_w, notes)
    elif directives["garden"]:
        notes.append("No room for the wished garden; rooms kept.")
    _shell(rects, buckets, build_w, build_d, notes,
           _wish_walls(buckets["bedrooms"], directives["facing"], road,
                       north_angle))
    achieved = _verify_open_plan(rects, valid_pairs, notes)
    glass = _verify_glass(rects, buckets, directives, notes)
    house_w = 2 * side_w + center_w
    indoor = [r for r in rects
              if _room_type(r) not in ("porch", "veranda", "garden")]
    info = {"row_front_y": y0, "row_widths": [house_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried_all, "relaxed": relaxed,
                         "typology": "three-strip", "open_plan": achieved,
                         "glass": glass}


def _assign_two_strip(buckets, notes, kitchen_first, directives,
                      living_out, road, single_side, north_angle=None):
    """Single side-strip order, back to front (narrow plots).

    Returns (slots, valid_pairs, merge_lk). The living room (when out of
    the spine) goes front-most; merged with the kitchen it sits directly
    below it (kitchen second-to-last), one open space. Facing wishes
    move a bedroom to the front/back end; side wishes match or miss.
    """
    beds = list(buckets["bedrooms"])
    master_name = beds[0]["name"] if beds else ""
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    living = buckets["living"][0] if buckets["living"] else None
    bath_of, loose, common = _bath_map(buckets, notes)
    _face_sides, face_positions = _bed_facing_plan(
        beds, directives["facing"], road, notes, single_side,
        north_angle=north_angle)
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
    for index, end in face_positions.items():
        names = {b["name"] for b in bath_of.get(beds[index]["name"], [])}
        _relocate_block(slots, beds[index]["name"], names, end == "front")
        if end == "front":
            for pos, slot in enumerate(slots):
                if slot[0] == "bath" and slot[1]["name"] in names:
                    slots[pos] = ("bath", slot[1], (slot[2][0], False))
    return slots, valid_pairs, merge_lk




def _assign_two_compact(buckets, notes):
    """Fixed compact side order ([pair, bed, kitchen, bed]) + pairs.

    Round 2 item 2: the solid paired top (attached bath + common,
    8.5 ft wet, no dressing band) is the only way 2 beds + kitchen
    fit one 10 ft strip; the kitchen sits middle to reach dining.
    """
    beds = list(buckets["bedrooms"])
    master_name = beds[0]["name"] if beds else ""
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    bath_of, _loose, common = _bath_map(buckets, notes)
    valid_pairs = _valid_pairs(buckets, {"combine": [], "glass": [],
                                    "refused": []}, notes)
    bed1 = beds[0] if beds else None
    bed2 = beds[1] if len(beds) > 1 else None
    bath1 = (bath_of.get(bed1["name"], []) or [None])[0] \
        if bed1 is not None else None
    if bed1 is None or bed2 is None or kitchen is None \
            or bath1 is None or common is None:
        raise _Infeasible("compact two-strip needs 2 beds + kitchen + "
                          "attached bath + common")
    slots = [("compact_pair", common, bath1),
             ("bedroom", bed1, None),
             ("kitchen", kitchen, None),
             ("bedroom", bed2, None)]
    return slots, valid_pairs
def _two_strip(buckets, build_w, build_d, side_west, kitchen_first,
               notes, directives, road, north_angle=None,
               _compact=False, _compact_height=36.0):
    """One two-strip option in buildable coords (rects, info, meta).

    Raises _Infeasible (geometry is hard) instead of placing anything
    outside the buildable area.
    """
    if _compact:
        # Round 2 item 2: rooms start at the buildable edge (no
        # porch room inside; the entry porch is a light structure in
        # the front setback). The house narrows to 20 ft so the
        # kitchen side keeps a 3 ft veranda margin.
        center_w, side_w = 10.0, 10.0
        x0 = 3.0 if side_west else 1.0
        if side_west:
            side_x, spine_x = x0, x0 + side_w
        else:
            spine_x, side_x = x0, x0 + center_w
        y0 = 0.0
        notes.append("Compact two-strip: combined living+dining, small "
                     "foyer, side rooms at lower-end sizes.")
        living_out, reason = True, "compact (living shares dining)"
    else:
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
    rooms = _spine_rooms(buckets, living_out)
    height = _compact_height if _compact else min(
        build_d - y0, _spine_cap(rooms, center_w))
    spine, relaxed, tried = _place_spine(
        rooms, spine_x, center_w, y0, height, notes)
    spans = _spine_spans(spine)
    if _compact:
        for rect in spine:
            if rect["type"] == "dining":
                rect["name"] = "Living + Dining"
    if _compact:
        slots, valid_pairs = _assign_two_compact(buckets, notes)
        has_living = False
    else:
        slots, valid_pairs, _merge_lk = _assign_two_strip(
            buckets, notes, kitchen_first, directives, living_out, road,
            0 if side_west else 1, north_angle)
        has_living = any(kind == "living" for kind, _r, _e in slots)
    garden_ok = True
    base_min = y0 + 1.0 \
        if _front_wish(directives, road, north_angle) else 0.0
    stacked, garden_ok, count = _stack_with_garden(
        slots, side_x, side_w, build_d, spans, notes,
        outer_east=not side_west, base_min=base_min,
        want_garden=bool(directives["garden"]) and has_living)
    sides, _sat, _tot, _tried = stacked
    master_name = buckets["bedrooms"][0]["name"] \
        if buckets["bedrooms"] else ""
    fatal = _fatal_count([slots], sides, spans)
    bounds = _master_bounds(sides, master_name)
    if bounds:
        # Second pass: master largest, others shrink first; keep it
        # when rule 19 holds with no new fatal door miss (soft
        # kitchen/living misses may trade for the hard size rule,
        # and so may the wished garden: hard rules beat wishes).
        garden1 = garden_ok
        try:
            second, garden2, count2 = _stack_with_garden(
                slots, side_x, side_w, build_d, spans, notes,
                outer_east=not side_west, base_min=base_min,
                want_garden=bool(directives["garden"]) and has_living,
                depth_bounds=bounds, tops=_PASS2_TOPS)
        except _Infeasible:
            second = None
        fatal2 = _fatal_count([slots], second[0], spans) \
            if second is not None else None
        if second is not None and fatal2 <= fatal \
                and not _master_bounds(second[0], master_name):
            stacked, garden_ok, count = second, garden2, count + count2
            notes.append("Master kept largest (other rooms shrunk first).")
            if garden1 and not garden_ok:
                notes.append("Garden dropped: the master-size rule "
                             "wins (hard rules beat wishes).")
            notch = build_d - max(r["y"] + r["d"] for r in second[0])
            if notch > 0.25:
                notes.append("%d-ft back notch keeps bedroom doors."
                             % round(notch))
        if second is None or _master_bounds(second[0], master_name):
            # Grow pass failed or still tied: shrunk fallback (others to
            # minimum, master compact) - shared with three-strip.
            shrunk_bounds = _master_bounds_shrunk(sides, master_name)
            second = None
            if shrunk_bounds:
                try:
                    second, garden2, count2 = _stack_with_garden(
                        slots, side_x, side_w, build_d, spans, notes,
                        outer_east=not side_west, base_min=base_min,
                        want_garden=bool(directives["garden"])
                        and has_living,
                        depth_bounds=shrunk_bounds, tops=_PASS2_TOPS)
                except _Infeasible:
                    second = None
                fatal2 = _fatal_count([slots], second[0], spans) \
                    if second is not None else None
                if second is not None and fatal2 <= fatal \
                        and not _master_bounds(second[0], master_name):
                    stacked, garden_ok, count = second, garden2, \
                        count + count2
                    notes.append("Master kept largest (other rooms shrunk "
                                 "first).")
    sides, _sat, _tot, _tried = stacked
    rects = spine + sides
    if directives["garden"] and garden_ok and has_living:
        living = next(r for r in rects if r["type"] == "living room")
        _place_garden(rects, living, side_x, side_w, notes)
    elif directives["garden"]:
        notes.append("No room for the wished garden; rooms kept.")
    _shell(rects, buckets, build_w, build_d, notes,
           _wish_walls(buckets["bedrooms"], directives["facing"], road,
                       north_angle))
    achieved = _verify_open_plan(rects, valid_pairs, notes)
    glass = _verify_glass(rects, buckets, directives, notes)
    indoor = [r for r in rects
              if _room_type(r) not in ("porch", "veranda", "garden")]
    info = {"row_front_y": y0, "row_widths": [center_w + side_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried + count, "relaxed": relaxed,
                         "typology": "two-strip", "open_plan": achieved,
                         "glass": glass}


def _width_options(room, depth, kind):
    """0.5-ft widths in range, preferred-like first, never-square vs depth."""
    low, high = _type_range(kind)
    pref = _pref(room, "width_ft", kind)
    preferred, relaxed = [], []
    width = low
    while width <= high + EPS:
        if abs(width - depth) >= 1 - EPS:
            preferred.append(_half(width))
        width += 0.5
    limits = RELAXED_RANGES.get(kind)
    if limits is not None:
        width = limits[0]
        while width <= limits[1] + EPS:
            candidate = _half(width)
            if candidate not in preferred \
                    and abs(candidate - depth) >= 1 - EPS:
                relaxed.append(candidate)
            width += 0.5
    preferred.sort(key=lambda w: (abs(w - pref), w))
    relaxed.sort(key=lambda w: (abs(w - pref), w))
    return preferred + relaxed


def _relaxed_width(kind, width):
    """True when a width uses the relaxed (bend) range, not preferred."""
    low, high = _type_range(kind)
    if low - EPS <= width <= high + EPS:
        return False
    limits = RELAXED_RANGES.get(kind)
    return limits is not None and limits[0] - EPS <= width <= limits[1] + EPS


def _width_score(entries, combo):
    """Pref-closeness + 10 per relaxed width (preferred fill wins)."""
    score = 0.0
    for (room, kind, const), width in zip(entries, combo):
        if const is not None:
            continue
        score += abs(width - _pref(room, "width_ft", kind))
        if _relaxed_width(kind, width):
            score += 10.0
    return score


def _ranked_widths(entries, target, depth, limit=30):
    """Width combos: exact fills first, then garden-leftover fills.

    Returns ([(score, combo, leftover)], tried). Exact fills rank
    before partial fills, so rows that can fill the width behave
    exactly as before; a partial fill leaves leftover width for a
    garden (3 ft+ usable; slivers and overflows are rejected, so
    leftover width becomes landscape, never a failure).
    """
    option_lists = []
    for room, kind, const in entries:
        if const is not None:
            option_lists.append([const])
        else:
            option_lists.append(_width_options(room, depth, kind))
    tried = 1
    for options in option_lists:
        tried *= max(len(options), 1)
    exact, partial = [], []
    for combo in itertools.product(*option_lists):
        leftover = target - sum(combo)
        if abs(leftover) > 0.01 and leftover < 3 - EPS:
            continue
        if abs(leftover) <= 0.01:
            exact.append((_width_score(entries, combo), list(combo), 0.0))
        else:
            partial.append((_width_score(entries, combo), list(combo),
                            leftover))
    exact.sort(key=lambda item: (item[0], item[1]))
    partial.sort(key=lambda item: (item[0], item[2]))
    return (exact + partial)[:limit], tried


def _spans_for(kinds, widths, x0):
    """{kind: (x_start, x_end)} for one band row."""
    spans, cursor = {}, x0
    for kind, width in zip(kinds, widths):
        spans[kind] = (cursor, cursor + width)
        cursor += width
    return spans


def _overlap_len(first, second):
    """1D overlap length of two (start, end) spans."""
    return min(first[1], second[1]) - max(first[0], second[0])


def _back_widths(back_cells, total, back_d, spans, x0, mirror,
                 has_family, master_name, common, front_master=None,
                 master_area=0.0, touch_min=0.5):
    """(widths_or_None, store_residual, tried, fills) for the back band.

    Toilets keep fixed widths; the slack becomes a store slice (2 ft+,
    low end) or nothing when the row fills exactly. Validated per fill:
    the family overlaps a non-kitchen front room; the common toilet
    lands under dining or beside family; a front master's baths land
    under it; every
    bedroom touches family or dining (doors never open into the
    foyer/living); the master stays 10%+ bigger by area. fills tells
    whether any width-fill existed (for honest skip notes).
    """
    flex = [(room, kind) for room, kind, const in back_cells
            if const is None]
    fixed_sum = sum(const for _room, _kind, const in back_cells
                    if const is not None)
    bed_names = {room["name"] for room, kind in flex
                 if kind == "bedroom"}
    option_lists = [_width_options(room, back_d, kind)
                    for room, kind in flex]
    tried, best, fills = 0, None, False
    for combo in itertools.product(*option_lists):
        tried += 1
        residual = total - fixed_sum - sum(combo)
        if residual > 0.01 and residual < 2 - EPS:
            continue  # sliver no store can take; exact or useful only
        if residual < -0.01:
            continue
        fills = True
        widths, combo_iter = {}, iter(combo)
        for room, kind, const in back_cells:
            widths[room["name"]] = const if const is not None \
                else next(combo_iter)
        cursor, bounds = x0 + residual, {}
        for room, kind, _const in back_cells:
            width = widths[room["name"]]
            bounds[room["name"]] = (cursor, cursor + width)
            cursor += width
        if mirror:
            bounds = {name: (2 * x0 + total - end, 2 * x0 + total - start)
                      for name, (start, end) in bounds.items()}
        if has_family:
            fam_span = next(bounds[room["name"]] for room, kind in flex
                            if kind == "family living")
            touched = any(
                _overlap_len(fam_span, span) >= touch_min - EPS
                for kind, span in spans.items()
                if kind in ("dining", "living room", "foyer"))
            if not touched:
                continue  # family must reach a non-kitchen front room
        dining = spans.get("dining")
        if common is not None:
            under = dining is not None and _overlap_len(
                bounds[common["name"]], dining) >= 3 - EPS
            span_c = bounds[common["name"]]
            beside = has_family and (
                abs(span_c[0] - fam_span[1]) < 0.01
                or abs(span_c[1] - fam_span[0]) < 0.01)
            if not (under or beside):
                continue  # common toilet under dining or beside family
        if front_master is not None:
            master_span = spans.get("bedroom")
            if any(kind == "bathroom"
                   and room.get("attached_to") == front_master
                   and (master_span is None or _overlap_len(
                       bounds[room["name"]], master_span) < 3 - EPS)
                   for room, kind, _const in back_cells):
                continue  # master's bath must land under the front master
        for name in bed_names:
            span = bounds[name]
            by_family = False
            for room, kind, _const in back_cells:
                if kind == "family living" and (
                        abs(span[0] - bounds[room["name"]][1]) < 0.01
                        or abs(span[1] - bounds[room["name"]][0]) < 0.01):
                    by_family = True
            by_dining = dining is not None and \
                _overlap_len(span, dining) >= 3.5 - EPS
            if not (by_family or by_dining):
                break  # this bedroom could only open into foyer/living
        else:
            areas = {name: widths[name] * back_d for name in bed_names}
            if front_master is not None:
                areas[front_master] = master_area
            master_a = areas.get(master_name, 0.0)
            others = [area for name, area in areas.items()
                      if name != master_name]
            if any(master_a < 1.1 * other - 0.01 for other in others):
                continue  # master stays 10%+ bigger (area)
            key = _width_score([(room, kind, None) for room, kind in flex],
                               combo)
            # Shrink others first (width-equivalents, exact when same-depth).
            key += 0.1 * sum(others) / back_d - 0.3 * master_a / back_d
            if best is None or key < best[0] - EPS:
                best = (key, combo, residual)
    if best is None:
        return None, 0.0, tried, fills
    return best[1], best[2], tried, fills


def _front_wish_bed(beds, facing, angle):
    """First bedroom with a front-position wish (None: classic bands)."""
    for wish, index in _face_assign(beds, facing):
        if index is not None and index < len(beds) and \
                _facing_target(wish["side"], angle) == ("position", "front"):
            return beds[index]
    return None


def _bands_facing_notes(beds, low_beds, high_beds, directives, angle,
                        mirror, notes, front_bed=None):
    """Facing match/miss notes for one band option (fixed master ends).

    Each band variant fixes its master end, so a side wish is honored in
    the matching options and noted in the others; front/back wishes
    cannot leave the back row (noted, the wishes table reports them),
    except the front-corner bed in front-master options.
    """
    low_names = {bed["name"] for bed in low_beds}
    bearings = _side_bearings(angle)
    for wish in directives["facing"]:
        if wish["room"] != "bedroom":
            if wish["room"] == "kitchen":
                notes.append("Kitchen stays by the dining; facing wishes "
                             "are honored for bedrooms.")
            else:
                notes.append("%s stays in the front row; facing wishes "
                             "are honored for bedrooms."
                             % wish["phrase"].strip().capitalize())
    for wish, index in _face_assign(beds, directives["facing"]):
        if index is None or index >= len(beds):
            notes.append("No bedroom for '%s facing'; skipped."
                         % wish["phrase"].strip())
            continue
        bed = beds[index]
        kind, value = _facing_target(wish["side"], angle)
        if front_bed is not None and bed["name"] == front_bed["name"] \
                and kind == "position" and value == "front":
            notes.append("%s placed in the front corner (client wish: "
                         "%s facing)." % (bed["name"], wish["side"]))
            continue
        if kind != "strip":
            notes.append("%s stays in the back row (front/back ends "
                         "need a strip plan)." % bed["name"])
            continue
        end = 0 if bed["name"] in low_names else 1
        if mirror:
            end = 1 - end
        if end == value:
            notes.append("%s on the %s side (client wish)."
                         % (bed["name"], wish["side"]))
        else:
            here = _bearing_name(
                bearings["lowx" if end == 0 else "highx"]).lower()
            notes.append("%s faces %s in another option (here it is "
                         "%s-end)." % (bed["name"], wish["side"], here))


def _wide_bands(buckets, build_w, build_d, notes, directives, road,
                variant, north_angle=None, _classic=False,
                _fallback=False):
    """Shallow two-band option for wide plots (rects, info, meta).

    Front band (12 ft): kitchen always next to dining (hard rule 4),
    foyer/living after them (living sits by dining when a combine
    wish says so). Back band: low bedrooms, common toilet beside
    family in the middle with bedrooms around it, baths outer of
    their beds, store slice for the slack.
    Every bedroom touches family (or dining as fallback), so no bedroom
    door opens into the foyer/living; the master stays 10%+ biggest.
    A front-position bedroom wish (with family living) flips A/B into
    front-master mode: the wished bed takes a front corner beside the
    foyer, the kitchen moves to a back corner under dining, family sits
    under the master so every door still reaches it; C stays classic
    for comparison. Front-master mode caps the back band at 12 ft (the
    slack stays a front terrace) so back bedrooms cannot outgrow the
    12 ft master; without that cap the master-size rule cannot hold.
    Raises _Infeasible instead of breaking geometry (G).
    """
    beds = list(buckets["bedrooms"])
    if not beds:
        raise _Infeasible("shallow bands need at least one bedroom")
    angle = _resolve_angle(road, north_angle)
    front_bed = _front_wish_bed(beds, directives["facing"], angle)
    front_mode = front_bed is not None and buckets["family"] \
        and variant != "cross" and not _classic and not _fallback
    front_name = front_bed["name"] if front_mode else None
    y0 = _y0_porch(buckets)
    front_d = 12.0
    if front_mode:
        back_d = min(12.0, build_d - y0 - front_d)
        y0 = build_d - front_d - back_d
    else:
        back_d = build_d - y0 - front_d
    if back_d < 10 - EPS:
        raise _Infeasible("shallow bands need %.0f ft depth, have %.0f ft"
                          % (y0 + 22, build_d))
    if back_d > 15 + EPS:
        raise _Infeasible("too deep for shallow bands (%.0f ft)" % build_d)
    x0, total = 3.0, build_w - 6.0
    if total < 36 - EPS:
        raise _Infeasible("shallow bands need %.0f ft frontage, have %.0f ft"
                          % (42, build_w))
    master_name = beds[0]["name"]
    bath_of, loose, common = _bath_map(buckets, notes)
    valid_pairs = _valid_pairs(buckets, directives, notes)
    first = {"kitchen": buckets["kitchen"][:1],
             "dining": buckets["dining"][:1],
             "living room": buckets["living"][:1],
             "foyer": buckets["foyer"][:1],
             "bedroom": [front_bed] if front_mode else []}
    pair_set = {frozenset(pair) for pair in valid_pairs}
    live_dine = frozenset(("living room", "dining")) in pair_set
    live_kit = frozenset(("living room", "kitchen")) in pair_set
    dine_kit = frozenset(("dining", "kitchen")) in pair_set
    if common is not None:
        # Round 2: kitchen always sits next to dining (hard rule
        # 4); the common sits beside family. The first-wished living
        # pair picks the rest order (living stays by dining).
        first_pair = next((frozenset(pair) for pair in valid_pairs
                           if "living room" in pair), None)
        if first_pair == frozenset(("living room", "dining")):
            base = ["kitchen", "dining", "living room", "foyer"]
        else:
            base = ["kitchen", "dining", "foyer", "living room"]
        if False:  # round 2: kitchen always sits next to dining
            notes.append("Dining + kitchen cannot touch in shallow bands "
                         "(opposite ends for the common toilet); separate.")
    elif False:  # round 2: kitchen never leaves dining
        base = ["kitchen", "living room", "dining", "foyer"]
    else:
        base = ["kitchen", "dining", "living room", "foyer"]
    if front_mode:
        low_beds = [front_bed]
        high_beds = [bed for bed in beds
                     if bed["name"] != front_bed["name"]]
        order_front = ["bedroom", "foyer", "living room", "dining"]
    elif variant == "cross":
        # Master at the opposite end from A (front rerun below).
        low_beds, high_beds = list(beds[1:]), [beds[0]]
        if front_bed is not None:
            notes.append("Option C keeps %s in the back row (compare with "
                         "the front corner)." % front_bed["name"])
        if common is not None:
            order_front = [base[0], base[1], base[3], base[2]]
        else:
            order_front = [base[0], base[1], base[3], base[2]]
    else:
        low_beds, high_beds = [beds[0]], list(beds[1:])
        order_front = list(base)
    if variant == "cross":
        # C runs living + foyer west, dining + kitchen east (the
        # kitchen ends the row, so no path crosses it); the small
        # low bedroom keeps family beside it, the master reaches
        # dining.
        notes.append("Option C runs living + foyer west, dining "
                     "+ kitchen east (compare); the kitchen ends "
                     "the row, so no path crosses it.")
        order_front = ["living room", "foyer", "dining", "kitchen"]
    if _fallback:
        # Dining-second retry for very wide plots: dining sits
        # between the kitchen (hard rule 4) and the foyer, so it
        # joins the open spaces while the middle back bedrooms land
        # under it and keep their doors.
        order_front = ["kitchen", "dining", "foyer", "living room"]
    if front_bed is not None and not buckets["family"] \
            and variant != "cross":
        notes.append("No family living to anchor a front corner; %s stays "
                     "in the back row." % front_bed["name"])
    mirror = variant == "high"
    kinds = [kind for kind in order_front if first[kind]]
    if not kinds:
        raise _Infeasible("no common rooms for the front band")
    if variant == "cross":
        kinds_a = [kind for kind in base if first[kind]]
        for pair in valid_pairs:
            fst, snd = pair
            if fst in kinds_a and snd in kinds_a \
                    and fst in kinds and snd in kinds:
                adj_a = abs(kinds_a.index(fst) - kinds_a.index(snd)) == 1
                adj_c = abs(kinds.index(fst) - kinds.index(snd)) == 1
                if adj_a and not adj_c:
                    notes.append("Option C keeps %s + %s separate "
                                 "(compare with the open plan)."
                                 % tuple(sorted(pair)))
    entries = [(first[kind][0], kind, None) for kind in kinds]
    ranked, tried_front = _ranked_widths(entries, total, front_d)
    if not ranked:
        raise _Infeasible("front rooms cannot fill %.0f ft width" % total)
    _bands_facing_notes(beds, low_beds, high_beds, directives, angle,
                        mirror, notes, front_bed if front_mode else None)
    back_cells = []
    if front_mode:
        for bath in bath_of.get(front_bed["name"], []):
            back_cells.append((bath, "bathroom",
                               _bath_extra(bath, master_name)[0]))
        back_cells.append((buckets["family"][0], "family living", None))
        if common is not None:
            back_cells.append((common, "bathroom",
                               _bath_extra(common, master_name)[0]))
        for bath in loose:
            back_cells.append((bath, "bathroom",
                               _bath_extra(bath, master_name)[0]))
        for bed in high_beds:
            back_cells.append((bed, "bedroom", None))
            for bath in bath_of.get(bed["name"], []):
                back_cells.append((bath, "bathroom",
                                   _bath_extra(bath, master_name)[0]))
        if buckets["kitchen"]:
            back_cells.append((buckets["kitchen"][0], "kitchen", None))
    else:
        for bed in reversed(low_beds):
            for bath in bath_of.get(bed["name"], []):
                back_cells.append((bath, "bathroom",
                                   _bath_extra(bath, master_name)[0]))
            back_cells.append((bed, "bedroom", None))
        if buckets["family"]:
            back_cells.append((buckets["family"][0], "family living", None))
        for bed in high_beds:
            back_cells.append((bed, "bedroom", None))
            for bath in bath_of.get(bed["name"], []):
                back_cells.append((bath, "bathroom",
                                   _bath_extra(bath, master_name)[0]))
        if common is not None:
            back_cells.append((common, "bathroom",
                               _bath_extra(common, master_name)[0]))
        for bath in loose:
            back_cells.append((bath, "bathroom",
                               _bath_extra(bath, master_name)[0]))
    if front_mode:
        # Family stays under the front corner (its door bearing); back
        # bedrooms flank family, toilets + kitchen follow: every bedroom
        # bedroom door keeps a 3.5 ft bearing (T returns, round 2).
        def _cell_key(cell):  # baths, family, beds, toilets, kitchen
            room, kind, _const = cell
            if room in bath_of.get(front_bed["name"], []):
                return 0
            if room is common or room in loose:
                return 4
            if kind == "family living":
                return 1
            if room in high_beds:
                return 2  # bedrooms flank family
            if room is common or room in loose:
                return 4
            if kind == "bathroom":
                return 2  # highbeds' baths stay with their bedroom

            return 5  # kitchen last (under dining, keeps its door)
        back_cells.sort(key=_cell_key)
    if _fallback and common is not None and not front_mode \
            and buckets["family"]:
        # Dining-second retry: the last bedroom (+ its bath) moves
        # ahead of family under dining, the common sits beside
        # family, the other bedrooms flank family - every bedroom
        # keeps a family/dining door on very wide rows.
        _beds = [i for i, cell in enumerate(back_cells)
                 if cell[1] == "bedroom"]
        if len(_beds) >= 2:
            _last = _beds[-1]
            _mv = [back_cells.pop(_last)]
            if _last < len(back_cells) \
                    and back_cells[_last][1] == "bathroom" \
                    and back_cells[_last][0].get("attached_to") == \
                    _mv[0][0]["name"]:
                _mv.append(back_cells.pop(_last))
            _fam = next(i for i, cell in enumerate(back_cells)
                        if cell[1] == "family living")
            for _k, _cell in enumerate(_mv):
                back_cells.insert(_fam + _k, _cell)
        _ci = next(i for i, cell in enumerate(back_cells)
                   if cell[0] is common)
        _fam = next(i for i, cell in enumerate(back_cells)
                    if cell[1] == "family living")
        _mover = back_cells.pop(_ci)
        if _ci < _fam:
            _fam -= 1
        back_cells.insert(_fam, _mover)
    if not front_mode and common is not None and not _fallback:
        # Round 2: the common toilet sits right after the low-end
        # bedrooms (beside family when there is one); dining now sits
        # by the kitchen, so the common no longer lands under it.
        _low = {id(bed) for bed in low_beds}
        _low.update(id(bath) for bed in low_beds
                    for bath in bath_of.get(bed["name"], []))
        _ci = next(i for i, cell in enumerate(back_cells)
                   if cell[0] is common)
        _ii = next(i for i, cell in enumerate(back_cells)
                   if id(cell[0]) not in _low and cell[0] is not common)
        if variant == "cross" and buckets["family"]:
            _ii = next(i for i, cell in enumerate(back_cells)
                       if cell[1] == "family living") + 1
        elif variant == "cross":
            _high = {id(bed) for bed in high_beds}
            _ii = next(i for i, cell in enumerate(back_cells)
                       if id(cell[0]) in _high) + 1
        back_cells.insert(_ii, back_cells.pop(_ci))
    front_w, chosen, residual, tried_back = None, None, 0.0, 0
    front_left = 0.0
    saw_fills = False
    bed_pos = kinds.index("bedroom") if front_mode else None
    for _score, combo, left in ranked:
        spans = _spans_for(kinds, combo, x0)
        if mirror:  # checks run in final (mirrored) coordinates
            spans = {kind: (2 * x0 + total - end, 2 * x0 + total - start)
                     for kind, (start, end) in spans.items()}
        master_area = combo[bed_pos] * front_d if front_mode else 0.0
        _touch = 6.0 if _fallback else 0.5
        found = _back_widths(back_cells, total, back_d, spans, x0, mirror,
                             bool(buckets["family"]), master_name, common,
                             front_name, master_area, _touch)
        tried_back += found[2]
        saw_fills = saw_fills or found[3]
        if found[0] is not None:
            front_w, chosen, residual = combo, found[0], found[1]
            front_left = left
            break
    if front_w is None and not _fallback:
        # One retry with dining-last bands before giving up (very
        # wide plots strand the far bedroom under the old orders).
        notes.append("Retrying with dining-second bands (wide plot).")
        return _wide_bands(buckets, build_w, build_d, notes, directives,
                           road, variant, north_angle, _classic,
                           _fallback=True)
    if front_w is None:
        if saw_fills:
            raise _Infeasible("bedrooms cannot all reach family/dining "
                              "within %.0f ft width" % total)
        raise _Infeasible("back rooms cannot fill %.0f ft width" % total)
    rects, cursor = [], x0
    for kind, width in zip(kinds, front_w):
        rects.append(_as_rect(first[kind][0], cursor, y0, width, front_d))
        cursor += width
    if front_left > 0.01:
        # Wide plot: the front row cannot usefully fill the full
        # width, so the leftover end becomes a court garden
        # (landscape, never a failure). No garden_for flag: this is
        # leftover landscape, not the wished living-room garden.
        rects.append(_as_rect({"name": "Garden", "type": "garden"},
                              cursor, y0, front_left, front_d))
        notes.append("Garden fills the leftover %.0f ft at the end of "
                     "the front row." % front_left)
    back_y = y0 + front_d
    cursor = x0
    flex_widths = iter(chosen)
    flex = [(cell, kind) for cell, kind, const in back_cells
            if const is None]
    bed_widths = [width for (cell, kind), width in zip(flex, chosen)
                  if kind == "bedroom"]
    if residual > 6.0:
        # Wide plot, short back row: the open corner becomes a court
        # garden, so the built footprint reads as an L (public wing +
        # private wing joined at the corner). No garden_for (above).
        rects.append(_as_rect({"name": "Court", "type": "garden"},
                              cursor, back_y, residual, back_d))
        cursor += residual
        notes.append("Court garden fills the open %.0f ft corner "
                     "(L plan)." % residual)
    elif residual > 0.01:
        rects.append(_as_rect({"name": "Store", "type": "storage"},
                              cursor, back_y, residual, back_d))
        cursor += residual
    for room, kind, const in back_cells:
        width = const if const is not None else next(flex_widths)
        if kind == "bathroom":
            # Rule 18 calls the largest placed bedroom the master: the
            # long master bath only when its host stays the widest (all
            # back beds share one depth, so width decides area).
            host = next((bed["name"] for bed in beds
                         if room in bath_of.get(bed["name"], [])), "")
            host_w = next((width for (cell, kind), width in
                           zip(flex, chosen)
                           if kind == "bedroom" and cell["name"] == host),
                          0.0)
            is_master = _bath_extra(room, master_name)[1] and host_w and \
                all(host_w >= other - EPS for other in bed_widths)
            depth = min(9.0 if is_master else 8.0, back_d - 2.0)
            front_anchored = front_name is not None \
                and room.get("attached_to") == front_name
            if room is common:
                dine = next((r for r in rects if r["type"] == "dining"),
                            None)
                front_anchored = dine is not None and min(
                    cursor + width, dine["x"] + dine["w"]) \
                    - max(cursor, dine["x"]) >= 3 - EPS
            if front_anchored:
                # At the front of its slice: the common opens onto
                # dining below (the side margin keeps its exterior
                # wall); the front master's baths open onto the master
                # above them. A middle common sits back-anchored (its
                # north wall stays exterior, family beside it).
                rects.append(_as_rect(room, cursor, back_y, width, depth))
                rects.append(_as_rect(
                    {"name": "Wardrobe (%s)" % room["name"],
                     "type": "wardrobe"},
                    cursor, back_y + depth, width, back_d - depth))
                if room is common:
                    # Open notch behind a front-anchored common toilet:
                    # drop its back wardrobe so the north wall stays
                    # exterior (strip plans notch the same way).
                    rects.pop()
            else:
                rects.append(_as_rect(room, cursor, back_y + back_d - depth,
                                      width, depth))
                rects.append(_as_rect(
                    {"name": "Wardrobe (%s)" % room["name"],
                     "type": "wardrobe"},
                    cursor, back_y, width, back_d - depth))
        else:
            rects.append(_as_rect(room, cursor, back_y, width, back_d))
        cursor += width
    if mirror:
        for rect in rects:
            rect["x"] = 2 * x0 + total - rect["x"] - rect["w"]
    if back_d < 12 - EPS and buckets["family"]:
        notes.append("Family Living %.1f ft deep (relaxed) in the shallow "
                     "plan." % back_d)
    if directives["garden"]:
        notes.append("No room for the wished garden in the shallow plan; "
                     "rooms kept.")
    _shell(rects, buckets, build_w, build_d, notes,
           _wish_walls(buckets["bedrooms"], directives["facing"], road,
                       north_angle))
    achieved = _verify_open_plan(rects, _valid_pairs(buckets, directives,
                                                     notes), notes)
    glass = _verify_glass(rects, buckets, directives, notes)
    indoor = [r for r in rects
              if _room_type(r) not in ("porch", "veranda", "garden")]
    relaxed = [buckets["family"][0]["name"]] if back_d < 12 - EPS \
        and buckets["family"] else []
    info = {"row_front_y": y0, "row_widths": [total],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried_front + tried_back,
                         "relaxed": relaxed, "typology": "shallow-band",
                         "open_plan": achieved, "glass": glass}


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
    two sit adjacent (full wall between: the kitchen never opens to the
    living room, it takes glass to dining instead).
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
                glass = _verify_glass(rects, buckets, directives, notes)
                return rects, info, {"tried": tried, "relaxed": relaxed,
                                     "typology": "l-shape",
                                     "open_plan": achieved,
                                     "glass": glass}
    return None


def _door_bearing_nudge(rects, build_w, build_d, notes):
    """Slide the kitchen along the dining wall to a 3.5 ft door bearing.

    Strip stacking sometimes lands the kitchen on dining with only 1-2
    ft of shared wall, which cannot take the 3 ft kitchen door. Sliding
    the kitchen (with its verandas) along the wall by the deficit keeps
    every size and adjacency; the move is re-verified (inside
    buildable, no overlaps, bearing reached) and reverted otherwise.
    """
    kitchens = [r for r in rects if r["type"] == "kitchen"]
    dinings = [r for r in rects if r["type"] == "dining"]
    if not kitchens or not dinings:
        return
    kitchen, dining = kitchens[0], dinings[0]
    runs = _wall_runs(kitchen, dining)
    if not runs or len({run[0] for run in runs}) > 1:
        return
    overlap = sum(run[2] - run[1] for run in runs)
    # T-junction returns eat ~0.5 ft: a 3 ft door needs 3.5 ft of wall.
    overlap -= 0.5
    if overlap < EPS or overlap >= ROOM_W_FT - EPS:
        return
    side = runs[0][0]
    if side in ("E", "W"):
        delta = ROOM_W_FT - overlap
        shift = (0.0, delta if kitchen["y"] + kitchen["d"] / 2.0
                 < dining["y"] + dining["d"] / 2.0 else -delta)
    else:
        delta = ROOM_W_FT - overlap
        shift = (delta if kitchen["x"] + kitchen["w"] / 2.0
                 < dining["x"] + dining["w"] / 2.0 else -delta, 0.0)
    movers = [kitchen] + [r for r in rects
                           if r.get("veranda_for") == kitchen["name"]]
    for rect in movers:
        rect["x"] += shift[0]
        rect["y"] += shift[1]
    ok = True
    for rect in movers:
        if rect["x"] < -0.01 or rect["y"] < -0.01 \
                or rect["x"] + rect["w"] > build_w + 0.01 \
                or rect["y"] + rect["d"] > build_d + 0.01:
            ok = False
    if ok:
        for rect in movers:
            for other in rects:
                if other in movers:
                    continue
                if _area_overlap(rect, other) > 0.01:
                    ok = False
    if ok:
        bearing = sum(run[2] - run[1]
                      for run in _wall_runs(kitchen, dining))
        ok = bearing >= ROOM_W_FT + 0.5 - EPS
    if ok:
        notes.append("Kitchen nudged %.1f ft for a 3.5 ft door bearing on "
                     "dining." % max(abs(shift[0]), abs(shift[1])))
    else:
        for rect in movers:
            rect["x"] -= shift[0]
            rect["y"] -= shift[1]


def _kitchen_veranda_variant(rects, label, build_w, build_d, notes):
    """Night task 1: per-option answer for a road-facing kitchen veranda.

    Runs when the placed kitchen veranda sits on wall S (the road),
    i.e. no side/back wall had space. A keeps it with a jali/screen
    wall; B re-seats it on a side/back wall (shifting the whole house
    rigidly to free a 3 ft side margin when slack allows); C drops it
    (the kitchen window ventilates instead). No-ops otherwise.
    Returns a title suffix describing the choice.
    """
    kitchens = [r for r in rects if r["type"] == "kitchen"]
    if not kitchens:
        return ""
    kitchen = kitchens[0]
    verandas = [r for r in rects if r["type"] == "veranda"
                and r.get("veranda_for") == kitchen["name"]]
    if not verandas:
        return ""
    veranda = verandas[0]
    side, _start, _end = _shared_wall_and_span(kitchen, veranda)
    if side != "S":
        return ""
    if label == "A":
        veranda["screened_jali"] = True
        veranda["name"] = "%s (jali)" % veranda["name"]
        notes.append("Kitchen veranda faces the road: kept with a "
                     "jali/screen wall for privacy (option A choice).")
        return "; kitchen veranda jali-screened"
    if label == "C":
        rects.remove(veranda)
        walls = _exterior_walls(kitchen, rects)
        win_wall = max(("W", "E", "N"), key=lambda w: walls[w])
        if walls[win_wall] >= 3.0 - EPS:
            notes.append("No kitchen veranda (option C choice): the "
                         "kitchen window ventilates from the %s wall."
                         % win_wall)
        else:
            notes.append("No kitchen veranda (option C choice), but no "
                         "non-road window wall fits either.")
        return "; no kitchen veranda (windowed)"
    rects.remove(veranda)
    east = kitchen["x"] + kitchen["w"] / 2.0 > build_w / 2.0
    margin = build_w - max(r["x"] + r["w"] for r in rects) \
        if east else min(r["x"] for r in rects)
    shift = 0.0
    if margin < 3.0 - EPS:
        slack = min(r["x"] for r in rects) if east \
            else build_w - max(r["x"] + r["w"] for r in rects)
        shift = max(0.0, min(3.0 - margin, slack))
        for rect in rects:
            rect["x"] += -shift if east else shift
    order = ["E", "N", "W"] if east else ["W", "N", "E"]
    _add_verandas(rects, [(kitchen, order)], build_w, build_d, notes)
    placed = [r for r in rects if r["type"] == "veranda"
              and r.get("veranda_for") == kitchen["name"]]
    if not placed:
        notes.append("Side/back kitchen veranda did not fit (option B "
                     "choice unmet); the kitchen keeps its window.")
        return "; kitchen veranda off-road (unmet)"
    new_wall, _s, _e = _shared_wall_and_span(kitchen, placed[0])
    notes.append("Kitchen veranda moved off the road onto the %s wall "
                 "(option B choice)%s."
                 % (new_wall, "; house shifted %.1f ft to free a side "
                    "margin" % shift if shift > EPS else ""))
    return "; kitchen veranda on %s wall" % new_wall


def _finish_option(rects, info, meta, label, title, build_w, build_d, road,
                   num_toilets, notes, buckets, directives,
                   north_angle=None):
    """Check, score and shift one option to plot-local coordinates."""
    _door_bearing_nudge(rects, build_w, build_d, notes)
    title += _kitchen_veranda_variant(rects, label, build_w, build_d,
                                      notes)
    rules, goals, quality = _check_all(rects, info, build_w, build_d, road,
                                       num_toilets, north_angle,
                                       meta.get("open_plan", []),
                                       meta.get("glass", []))
    wish_rows, met, total = _wishes_table(rects, meta, buckets, directives,
                                          road, north_angle)
    quality["wishes_met"] = met
    quality["wishes_total"] = total
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
            "open_plan": list(meta.get("open_plan", [])),
            "glass_partitions": list(meta.get("glass", [])),
            "wishes": [{"wish": wish, "status": status}
                       for wish, status in wish_rows]}




def _two_strip_fallback(buckets, build_w, build_d, side_west,
                        kitchen_first, notes, directives, road, angle,
                        height=36.0):
    """Standard two-strip, else the compact retry (round 2 item 2)."""
    try:
        return _two_strip(buckets, build_w, build_d, side_west,
                          kitchen_first, notes, directives, road, angle)
    except _Infeasible as exc:
        notes.append("Standard two-strip does not fit (%s); compact "
                     "retry (combined living+dining, lower-end sizes)."
                     % exc)
        return _two_strip(buckets, build_w, build_d, side_west,
                          kitchen_first, notes, directives, road, angle,
                          _compact=True, _compact_height=height)
def _option_specs(buckets, build_w, build_d, road, directives,
                  north_angle=None):
    """(label, title, builder) for A/B/C (builders take a notes list)."""
    angle = _resolve_angle(road, north_angle)
    bearings = _side_bearings(angle)
    if build_w < 30 - EPS:
        low_word = _bearing_name(bearings["lowx"]).lower()
        high_word = _bearing_name(bearings["highx"]).lower()

        def _build_c_two(notes):
            if directives["combine"]:
                notes.append("Option C keeps rooms separate (compare with "
                             "the open plan).")
            plain = dict(directives, combine=[], glass=[])
            return _two_strip_fallback(buckets, build_w, build_d, True, False,
                                       notes,
                              plain, road, angle, height=35.0)

        return [
            ("A", "Two-strip, rooms %s" % low_word,
             lambda n: _two_strip_fallback(buckets, build_w, build_d, True, True,
                                           n,
                                  directives, road, angle)),
            ("B", "Two-strip, rooms %s" % high_word,
             lambda n: _two_strip_fallback(buckets, build_w, build_d, False, True,
                                           n,
                                  directives, road, angle)),
            ("C", "Two-strip, rooms %s (alt order)" % low_word,
             _build_c_two),
        ]
    west = _west_strip_index(angle)
    kitchen_a = west if west is not None else 0
    west_word = "west" if west is not None else "road-left"
    east_word = "east" if west is not None else "road-right"

    def _build_c(notes):
        found = _try_l_shape(buckets, build_w, build_d, notes, directives)
        if found is not None:
            if directives["facing"]:
                notes.append("Facing wishes are honored in the strip "
                             "options; the L-shape keeps its wings.")
            return found
        notes.append("L-shape does not fit this brief; "
                     "third three-strip variant instead.")
        strip_wish = any(
            wish["room"] == "bedroom"
            and _facing_target(wish["side"], angle)[0] == "strip"
            for wish in directives["facing"])
        if strip_wish:
            # A strip wish can collapse A/C to the same strips; C puts
            # the common toilet on the kitchen side instead.
            try:
                return _three_strip(buckets, build_w, build_d, kitchen_a,
                                    kitchen_a, notes, directives, road,
                                    0 if kitchen_a == 0 else 1, angle)
            except _Infeasible:
                notes.append("Common-side variant does not fit; closest "
                             "variant kept.")
        return _three_strip(buckets, build_w, build_d, kitchen_a, kitchen_a,
                            notes, directives, road, None, angle)

    return [
        ("A", "Three-strip, kitchen %s" % west_word,
         lambda n: _three_strip(buckets, build_w, build_d, kitchen_a,
                                2 - kitchen_a, n, directives, road,
                                None, angle)),
        ("B", "Three-strip, kitchen %s" % east_word,
         lambda n: _three_strip(buckets, build_w, build_d, 2 - kitchen_a,
                                kitchen_a, n, directives, road,
                                None, angle)),
        ("C", "L-shape with court" if build_w >= 45 - EPS
         else "Three-strip, kitchen + master %s" % west_word,
         _build_c),
    ]


def build_options(program_rooms, frontage_ft, depth_ft, road_side,
                  num_toilets, wishes="", north_angle=None):
    """Three typology options (A/B/C) for the brief, checked and scored.

    Frontage/depth are road-relative (frontage = road side). Wishes shape
    the layout (combined spaces, wished garden, room facing). Geometry
    is a hard constraint: an option that cannot fit inside the buildable
    area is skipped with a clear reason, never drawn broken. Orientation
    (kitchen west, facing wishes) uses the real north angle when given,
    else the road side's cardinal angle.
    """
    road = (road_side or "south").lower()
    angle = _resolve_angle(road, north_angle)
    plot_w, plot_d, build_w, build_d = _local_dims(frontage_ft, depth_ft)
    result = {"plot": {"width": plot_w, "depth": plot_d, "road": road,
                       "north_angle": angle},
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
    if build_w >= 30 - EPS and _west_strip_index(angle) is None:
        west_side = _closest_side(angle, 270.0)
        toward = "toward the road" if west_side == "front" \
            else "away from the road"
        result["notes"].append("Compass west points %s (north %g deg): "
                               "Option A uses the road-left strip."
                               % (toward, angle))
    for label, title, builder in _option_specs(buckets, build_w, build_d,
                                               road, directives, angle):
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
            num_toilets, notes, buckets, directives, angle))
    if not result["options"]:
        _try_wide_fallback(result, buckets, build_w, build_d, road,
                           num_toilets, directives, angle)
    _variety_glass(result["options"])
    return result


def _variety_glass(options):
    """Glass partition + sliding door between dining and family living
    in one option (C first) for variety. Only where the two share a
    6 ft+ run that is not already one open space; best-effort, silent
    when no option qualifies. Drawing + note only: the run already
    joins the spaces, so checked rules are unaffected.
    """
    for opt in reversed(options):
        names = {r["name"]: r for r in opt["placements"]}
        dining, family = names.get("Dining"), names.get("Family Living")
        if dining is None or family is None:
            continue
        if ("Dining", "Family Living") in opt["open_plan"] \
                or ("Family Living", "Dining") in opt["open_plan"]:
            continue
        if any("Dining" in pair and "Family Living" in pair
               for pair in opt["glass_partitions"]):
            return
        if shared_wall(dining, family) >= 6 - EPS:
            opt["glass_partitions"].append(("Dining", "Family Living"))
            opt["notes"].append("Glass partition with a sliding glass "
                                "door between Dining and Family Living "
                                "(variety).")
            return


def _try_wide_fallback(result, buckets, build_w, build_d, road,
                       num_toilets, directives, north_angle=None):
    """Shallow two-band options when no strip plan fits (wide plots)."""
    angle = _resolve_angle(road, north_angle)
    depths_ok = 10 - EPS <= build_d - _y0_porch(buckets) - 12.0 <= 15 + EPS
    if build_w < 42 - EPS or not depths_ok:
        return
    result["notes"].append("Standard strips need more depth; trying the "
                           "shallow two-band plan.")
    bearings = _side_bearings(angle)
    low_word = _bearing_name(bearings["lowx"]).lower()
    high_word = _bearing_name(bearings["highx"]).lower()
    front_possible = _front_wish_bed(
        buckets["bedrooms"], directives["facing"], angle) is not None \
        and buckets["family"]
    if front_possible:
        specs = (("A", "Shallow bands, master front %s" % low_word, "low"),
                 ("B", "Shallow bands, master front %s" % high_word, "high"),
                 ("C", "Shallow bands, master %s" % high_word, "cross"))
    else:
        specs = (("A", "Shallow bands, kitchen %s" % low_word, "low"),
                 ("B", "Shallow bands, kitchen %s" % high_word, "high"),
                 ("C", "Shallow bands, master %s" % high_word, "cross"))
    for label, title, variant in specs:
        notes = []
        try:
            rects, info, meta = _wide_bands(buckets, build_w, build_d,
                                            notes, directives, road,
                                            variant, angle)
        except _Infeasible as exc:
            if front_possible and variant != "cross":
                notes.append("Front corner does not fit; master stays back.")
                try:
                    rects, info, meta = _wide_bands(
                        buckets, build_w, build_d, notes, directives, road,
                        variant, angle, _classic=True)
                except _Infeasible as exc2:
                    result["notes"].append("Option %s skipped: %s."
                                          % (label, exc2))
                    continue
            else:
                result["notes"].append("Option %s skipped: %s." % (label, exc))
                continue
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            notes.append("Option %s failed to build (%s)." % (label, exc))
            continue
        result["options"].append(_finish_option(
            rects, info, meta, label, title, build_w, build_d, road,
            num_toilets, notes, buckets, directives, angle))
