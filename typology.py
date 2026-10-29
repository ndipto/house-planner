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
# Rooms that cannot reach their door-zone are still placed: the strict
# checker reports them honestly (bend/fail), never silently dropped.

import itertools

from ai_program import (
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
)
from layout import (
    EPS,
    RELAXED_RANGES,
    _add_porch,
    _add_verandas,
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
)

# Spine order, front to back. The hub has no corridor by construction.
SPINE_ORDER = ["foyer", "living room", "dining", "family living"]


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


def _needs_narrow(buckets):
    """Side strips narrow to 10 ft when a bath needs a spine door.

    Common/loose baths span the strip full-width (10 ft is the bathroom
    max); wider strips would park a wardrobe between bath and spine.
    """
    by_name = {bed["name"] for bed in buckets["bedrooms"]}
    for bath in buckets["bathrooms"]:
        if bath.get("attached_to") not in by_name:
            return True
    return False


def _strip_widths_three(build_w, narrow):
    """(west_w, center_w, east_w, x0, note): 10-15 ft strips, house centered.

    Center prefers 12 ft (fits foyer 6-12 and family/living 12+). Houses
    over 42 ft wide stop growing: the leftover stays side landscape.
    Narrow sides (10 ft) let common baths span full-width to the spine.
    """
    if narrow:
        total = min(build_w, 32.0)
        side = 10.0
        center = total - 20.0
    else:
        total = min(build_w, 42.0)
        center = 12.0 if total >= 32 else max(10.0, total - 20.0)
        side = _half((total - center) / 2)
        center = total - 2 * side  # exact (no rounding drift)
    x0 = _half((build_w - total) / 2)
    note = ""
    if build_w - total > 0.01:
        note = "House %.0f ft wide in %.0f ft buildable; sides stay landscape." % (
            total, build_w)
    return side, center, side, x0, note


def _strip_widths_two(build_w, narrow):
    """(center_w, side_w, x0, total) for narrow plots (one side strip)."""
    total = min(build_w, 27.0)
    if narrow:
        side = min(10.0, total - 6.0)
        center = min(12.0, total - side)
        total = side + center
    else:
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
        depths = {room["name"]: d for room, (d, _) in zip(spine_rooms, combo)}
        key = (relaxed, -depths.get("Dining", 0), -depths.get("Family Living", 0))
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


def _bath_width(strip_w):
    """(bath_w, filler_w): bath against the outer wall, leftover wardrobe."""
    if strip_w <= 10 + EPS:
        return strip_w, 0.0  # full-width: common baths keep a spine door
    for width in (8, 7):
        if strip_w - width >= 3 - EPS:
            return float(width), strip_w - width
    return strip_w, 0.0


def _assign_three_strip(buckets, kitchen_strip, master_strip, notes):
    """Back-to-front slot lists ((west, east)): (kind, room, extra).

    Master takes its back corner, second bedroom the other back corner,
    attached baths pin below their bedroom, kitchen goes mid-strip on
    its side, the common toilet mid-strip opposite. Extra bedrooms stack
    front-ward (often blocked: placed, reported honestly).
    """
    kitchen_side = 0 if kitchen_strip == 0 else 1
    master_side = 0 if master_strip == 0 else 1
    other_side = 1 - kitchen_side
    beds = list(buckets["bedrooms"])
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    bath_of, loose_baths, common = _bath_map(buckets, notes)
    sides = [[], []]

    def _bed_with_bath(bed, strip):
        sides[strip].append(("bedroom", bed, None))
        for bath in bath_of.get(bed["name"], []):
            sides[strip].append(("bath", bath, bed["name"]))

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
                order[other_side].append(("bath", bath, first["name"]))
        if common is not None:
            order[other_side].append(("common", common, None))
        for bed in middle:
            order[other_side].append(("bedroom", bed, None))
            for bath in bath_of.get(bed["name"], []):
                order[other_side].append(("bath", bath, bed["name"]))
        for bath in loose_baths:
            order[other_side].append(("common", bath, None))
        variants.append(order)
    return variants


def _slot_options(kind, room, strip_w, is_outer_bath):
    """Depth options (0.5 ft) for one side-stack slot (valid only)."""
    if kind in ("bath", "common"):
        width = _bath_width(strip_w)[0] if is_outer_bath else strip_w
    else:
        width = strip_w
    kind_key = "bathroom" if kind in ("bath", "common") else _room_type(room)
    low, high = _type_range(kind_key)
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
                outer_east=False):
    """Stack slots back-anchored (top at build_d); maximize door-zone touch.

    spans = {"dining": (y0, y1), "family": (y0, y1)} spine door-zones.
    Baths sit against the outer wall (east edge when outer_east), the
    leftover strip width becoming a wardrobe/store beside them.
    Returns (rects, satisfied, total_targets, tried): every slot placed
    even when its door-zone is missed (reported, never dropped).
    """
    option_lists = [_slot_options(kind, room, strip_w, True)
                    for kind, room, _extra in slots]
    tried = 1
    for options in option_lists:
        tried *= len(options)
    best = None
    bath_w, filler_w = _bath_width(strip_w)
    for combo in itertools.product(*option_lists):
        heights = sum(combo)
        bottom = build_d - heights
        score, satisfied, total = 0.0, 0, 0
        top = build_d
        for (kind, room, extra), depth in zip(slots, combo):
            keys = []
            if kind == "kitchen":
                keys = ["dining", "family"]
            elif kind in ("bedroom", "common"):
                keys = ["family", "dining"]
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
        overflow = max(0.0, -bottom)
        score -= overflow * 50.0 + max(0.0, bottom) * 0.05
        key = (satisfied, score)
        if best is None or key > best[0]:
            best = (key, combo, satisfied, total)
    _key, combo, satisfied, total = best
    rects = []
    top = build_d
    for (kind, room, extra), depth in zip(slots, combo):
        bottom = top - depth
        if kind in ("bath", "common") and filler_w > 0:
            kitchen_side = any(s_kind == "kitchen"
                               for s_kind, _r, _e in slots)
            label = "Store" if kitchen_side else "Wardrobe"
            if outer_east:
                bath_x, filler_x = strip_x0 + filler_w, strip_x0
            else:
                bath_x, filler_x = strip_x0, strip_x0 + bath_w
            rects.append(_as_rect(room, bath_x, bottom, bath_w, depth))
            rects.append(_as_rect({"name": "%s (%s)" % (label, room["name"]),
                                   "type": "wardrobe",
                                   "width_range": [filler_w, filler_w],
                                   "depth_range": [depth, depth]},
                                  filler_x, bottom, filler_w, depth))
        else:
            rects.append(_as_rect(room, strip_x0, bottom, strip_w, depth))
        top = bottom
    return rects, satisfied, total, tried


def _spine_spans(rects):
    """Door-zone y-spans of the placed spine rooms (dining/family)."""
    spans = {}
    for rect in rects:
        if rect["name"] in ("Dining", "Family Living"):
            key = "dining" if rect["name"] == "Dining" else "family"
            spans[key] = (rect["y"], rect["y"] + rect["d"])
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
    """Spine rooms front-to-back; returns (rects, relaxed, tried)."""
    depths, relaxed, tried = _spine_depths(spine_rooms, width, height, notes)
    if depths is None:  # best attempt: preferred middles + open back lobby
        depths = []
        for room in spine_rooms:
            preferred, _relaxed = _depth_options(room, width)
            if preferred:
                depths.append((room, preferred[len(preferred) // 2]))
            else:
                low, high = _type_range(_room_type(room))
                depths.append((room, _half((low + high) / 2)))
        used = sum(d for _room, d in depths)
        if used <= height + EPS:
            notes.append("Spine rooms fill %.0f of %.0f ft; %.0f ft open "
                         "lobby at the back." % (used, height, height - used))
        else:
            notes.append("Spine needs %.0f ft but has %.0f ft; back rooms "
                         "overflow the plot (reported)."
                         % (used, height))
    rects, cursor = [], y0
    for room, depth in depths:
        rects.append(_as_rect(room, x0, cursor, width, depth))
        cursor += depth
    return rects, relaxed, tried


def _spine_rooms(buckets):
    """Spine rooms present, front-to-back (foyer, living, dining, family)."""
    rooms = buckets["foyer"] + buckets["living"] + buckets["dining"] + \
        buckets["family"]
    return sorted(rooms, key=lambda r: SPINE_ORDER.index(_room_type(r)))


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


def _three_strip(buckets, build_w, build_d, kitchen_strip, master_strip,
                 notes):
    """One three-strip option in buildable coords (rects, info, meta)."""
    narrow = _needs_narrow(buckets)
    side_w, center_w, _east, x0, house_note = _strip_widths_three(
        build_w, narrow)
    if narrow:
        notes.append("Side strips 10 ft so baths reach the spine full-width.")
    if house_note:
        notes.append(house_note)
    y0 = _y0_porch(buckets)
    spine, relaxed, tried = _place_spine(
        _spine_rooms(buckets), x0 + side_w, center_w, y0, build_d - y0, notes)
    spans = _spine_spans(spine)
    variants = _assign_three_strip(buckets, kitchen_strip, master_strip, notes)
    best, tried_all = None, tried
    for order in variants:
        tribe, satisfied = [], 0
        for index, slots in enumerate(order):
            strip_x = x0 if index == 0 else x0 + side_w + center_w
            placed, sat, _tot, count = _stack_side(
                slots, strip_x, side_w, build_d, spans, notes,
                outer_east=(index == 1))
            tribe.extend(placed)
            satisfied += sat
            tried_all += count
        if best is None or satisfied > best[0]:
            best = (satisfied, tribe)
    sides = best[1]
    rects = spine + sides
    _shell(rects, buckets, build_w, build_d, notes)
    house_w = 2 * side_w + center_w
    indoor = [r for r in rects if _room_type(r) not in ("porch", "veranda")]
    info = {"row_front_y": y0, "row_widths": [house_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried_all, "relaxed": relaxed,
                         "typology": "three-strip"}


def _assign_two_strip(buckets, notes, kitchen_first):
    """Single side-strip order, back to front (narrow plots)."""
    beds = list(buckets["bedrooms"])
    kitchen = buckets["kitchen"][0] if buckets["kitchen"] else None
    bath_of, loose, common = _bath_map(buckets, notes)
    slots = []

    def _bed_with_bath(bed):
        slots.append(("bedroom", bed, None))
        for bath in bath_of.get(bed["name"], []):
            slots.append(("bath", bath, bed["name"]))

    if beds:
        _bed_with_bath(beds[0])
    if len(beds) > 1:
        _bed_with_bath(beds[1])
    middle = []
    if kitchen_first:
        if kitchen is not None:
            middle.append(("kitchen", kitchen, None))
        if common is not None:
            middle.append(("common", common, None))
    else:
        if common is not None:
            middle.append(("common", common, None))
        if kitchen is not None:
            middle.append(("kitchen", kitchen, None))
    slots.extend(middle)
    for bed in beds[2:]:
        _bed_with_bath(bed)
    for bath in loose:
        slots.append(("common", bath, None))
    return slots


def _two_strip(buckets, build_w, build_d, side_west, kitchen_first, notes):
    """One two-strip option in buildable coords (rects, info, meta)."""
    narrow = _needs_narrow(buckets)
    center_w, side_w, x0, _total = _strip_widths_two(build_w, narrow)
    if narrow:
        notes.append("Side strip 10 ft so baths reach the spine full-width.")
    if side_west:
        side_x, spine_x = x0, x0 + side_w
    else:
        spine_x, side_x = x0, x0 + center_w
    y0 = _y0_porch(buckets)
    spine, relaxed, tried = _place_spine(
        _spine_rooms(buckets), spine_x, center_w, y0, build_d - y0, notes)
    spans = _spine_spans(spine)
    slots = _assign_two_strip(buckets, notes, kitchen_first)
    sides, _sat, _tot, count = _stack_side(
        slots, side_x, side_w, build_d, spans, notes,
        outer_east=not side_west)
    rects = spine + sides
    _shell(rects, buckets, build_w, build_d, notes)
    indoor = [r for r in rects if _room_type(r) not in ("porch", "veranda")]
    info = {"row_front_y": y0, "row_widths": [center_w + side_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, {"tried": tried + count, "relaxed": relaxed,
                         "typology": "two-strip"}


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
                 notes):
    """One L wing-size combo; (rects, info, relaxed) or None."""
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
    above = []
    for bed in buckets["bedrooms"]:
        above.append(bed)
        above.extend(bath_of.get(bed["name"], []))
    above.extend(loose)
    options_list = []
    for room in above:
        kind = "bathroom" if room in buckets["bathrooms"] else _room_type(room)
        low, high = _type_range(kind)
        options = [d / 2 for d in range(int(low * 2), int(high * 2) + 1)
                   if abs(d / 2 - wing_b_w) >= 1 - EPS]
        if not options:
            return None
        options_list.append(options)
    avail = build_d - (y0 + fam_d)
    depths = _grow_stack(options_list, avail) if options_list else []
    if depths is None:
        return None
    cursor = y0 + fam_d
    for room, depth in zip(above, depths):
        rects.append(_as_rect(room, 0.0, cursor, wing_b_w, depth))
        cursor += depth
    if common is not None:
        placed = None
        for cw, cd in ((8, 7), (7, 8), (8, 8), (7, 7)):
            if wing_b_w + cw <= build_w + EPS and \
                    y0 + wing_a_d + cd <= build_d + EPS:
                placed = (cw, cd)
                break
        if placed is None:
            return None
        cw, cd = placed
        rects.append(_as_rect(common, wing_b_w, y0 + wing_a_d, cw, cd))
    _shell(rects, buckets, build_w, build_d, notes)
    indoor = [r for r in rects if _room_type(r) not in ("porch", "veranda")]
    info = {"row_front_y": y0, "row_widths": [build_w, wing_b_w],
            "house_back": max(r["y"] + r["d"] for r in indoor)}
    return rects, info, relaxed


def _try_l_shape(buckets, build_w, build_d, notes):
    """L-shape with court; (rects, info, meta) or None when nothing fits.

    Failed combos leave no notes behind (scratch list, kept on success).
    """
    if build_w < 45 - EPS:
        return None
    y0 = _y0_porch(buckets)
    wing_a = buckets["foyer"] + buckets["living"] + buckets["dining"] + \
        buckets["kitchen"][:1]
    wing_a = sorted(
        wing_a, key=lambda r: ("foyer", "living room", "dining", "kitchen")
        .index(_room_type(r)))
    tried = 0
    for wing_b_w in (12, 13, 14, 11, 10):
        for wing_a_d in (12, 13, 14):
            tried += 1
            scratch = []
            result = _try_l_combo(buckets, wing_a, build_w, build_d,
                                  float(wing_b_w), float(wing_a_d), y0,
                                  scratch)
            if result is not None:
                rects, info, relaxed = result
                notes.extend(scratch)
                notes.append("Open court fills the L's back-east corner.")
                return rects, info, {"tried": tried, "relaxed": relaxed,
                                     "typology": "l-shape"}
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
            "relaxed": list(meta.get("relaxed", []))}


def _option_specs(buckets, build_w, build_d, road):
    """(label, title, builder) for A/B/C (builders take a notes list)."""
    if build_w < 30 - EPS:
        return [
            ("A", "Two-strip, rooms west",
             lambda n: _two_strip(buckets, build_w, build_d, True, True, n)),
            ("B", "Two-strip, rooms east",
             lambda n: _two_strip(buckets, build_w, build_d, False, True, n)),
            ("C", "Two-strip, rooms west (alt order)",
             lambda n: _two_strip(buckets, build_w, build_d, True, False, n)),
        ]
    west = _west_strip_index(road)
    kitchen_a = west if west is not None else 0
    west_word = "west" if west is not None else "road-left"
    east_word = "east" if west is not None else "road-right"

    def _build_c(notes):
        found = _try_l_shape(buckets, build_w, build_d, notes)
        if found is not None:
            return found
        notes.append("L-shape does not fit this brief; "
                     "third three-strip variant instead.")
        return _three_strip(buckets, build_w, build_d, kitchen_a, kitchen_a,
                            notes)

    return [
        ("A", "Three-strip, kitchen %s" % west_word,
         lambda n: _three_strip(buckets, build_w, build_d, kitchen_a,
                                2 - kitchen_a, n)),
        ("B", "Three-strip, kitchen %s" % east_word,
         lambda n: _three_strip(buckets, build_w, build_d, 2 - kitchen_a,
                                kitchen_a, n)),
        ("C", "L-shape with court" if build_w >= 45 - EPS
         else "Three-strip, kitchen + master %s" % west_word,
         _build_c),
    ]


def build_options(program_rooms, plot_width, plot_depth, road_side,
                  num_toilets):
    """Three typology options (A/B/C) for the brief, checked and scored."""
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
    if build_w >= 30 - EPS and _west_strip_index(road) is None:
        result["notes"].append("Compass west points front/back on east/west "
                               "roads: Option A uses the road-left strip.")
    for label, title, builder in _option_specs(buckets, build_w, build_d,
                                               road):
        notes = []
        try:
            rects, info, meta = builder(notes)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            notes.append("Option %s failed to build (%s)." % (label, exc))
            continue
        result["options"].append(_finish_option(
            rects, info, meta, label, title, build_w, build_d, road,
            num_toilets, notes))
    return result
