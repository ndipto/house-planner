# openings.py
# Day 3 of House Planner: doors + windows from placed room rectangles.
#
# What this file does: given the placed rects (local frame, road at the
# bottom), it positions every door and window as a wall gap with exact
# local coordinates. draw.py renders these gaps (wall breaks + swing arcs +
# window lines) and layout.py checks them, so the drawing and the checker
# always agree: one placement, two readers.
#
# Door table (widths in ft, 4 in off true corners, never clashing;
# a T-junction partition is not a corner, so no clearance is owed it):
#   entry 3.5: porch -> foyer (swings into the foyer);
#   room 3.0: hub rooms (foyer, living, dining, family) join over the
#     shared walls they really have, spine order first; skipped between
#     open-plan pairs, whose wall stays open;
#   bedroom 3.0: bedroom -> family living, else dining, NEVER living/foyer;
#   kitchen 3.0: kitchen -> dining (unless open-merged with a hub room:
#     one space needs no door), plus 2.5 to its own veranda;
#   toilet 2.5: attached bath -> its own bedroom only; common bath ->
#     dining or family living; storage -> nearest hub room;
#   veranda 2.5: each veranda gets one door from its own room.
# Window table (exterior walls, or walls facing the room's own veranda):
#   bedroom 4.0 (two preferred, opposite walls when possible), living 5.0,
#   dining/family 4.0, kitchen 3.0, toilet 2.0 high, NEVER on the road side
#   (the local S wall faces the road). South/southeast preferred, west
#   avoided; bearings are plot-relative (0 = plot north = the north angle).

EPS = 1e-6

EXT_WALL_FT = 10.0 / 12.0
INT_WALL_FT = 5.0 / 12.0
CORNER_CLR_FT = 4.0 / 12.0

ENTRY_W_FT = 3.5
ROOM_W_FT = 3.0
TOILET_W_FT = 2.5
VERANDA_W_FT = 2.5

BED_WIN_FT = 4.0
LIVING_WIN_FT = 5.0
COMMON_WIN_FT = 4.0
KITCHEN_WIN_FT = 3.0
BATH_WIN_FT = 2.0

HUB_TYPES = ("foyer", "living room", "dining", "family living")
OPEN_TYPES = ("garden", "veranda", "porch")

# Rect types drawn with thin outlines instead of solid walls (open air).
UNWALLED_TYPES = ("garden", "veranda", "porch")


def _overlap_1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _wall_length(rect, side):
    if side in ("N", "S"):
        return rect["w"]
    return rect["d"]


def _wall_ends(rect, side):
    """Gap endpoints for interval [c0, c1] along a wall, local coords."""
    x, y, w, d = rect["x"], rect["y"], rect["w"], rect["d"]
    if side == "S":
        return (x, y, x + w, y)
    if side == "N":
        return (x, y + d, x + w, y + d)
    if side == "W":
        return (x, y, x, y + d)
    return (x + w, y, x + w, y + d)


def _point_on_wall(rect, side, center):
    x0, y0, x1, y1 = _wall_ends(rect, side)
    length = _wall_length(rect, side)
    if length < EPS:
        return (x0, y0)
    frac = min(max(center / length, 0.0), 1.0)
    return (x0 + (x1 - x0) * frac, y0 + (y1 - y0) * frac)


def _shared_with(rect, other):
    """Shared-wall runs vs one other rect: [(side, start, end)]."""
    runs = []
    x, y, w, d = rect["x"], rect["y"], rect["w"], rect["d"]
    ox, oy, ow, od = other["x"], other["y"], other["w"], other["d"]
    if abs(y - (oy + od)) < 0.02:  # other is below: my S wall
        start = max(x, ox) - x
        end = min(x + w, ox + ow) - x
        if end - start > EPS:
            runs.append(("S", start, end))
    if abs(y + d - oy) < 0.02:  # other is above: my N wall
        start = max(x, ox) - x
        end = min(x + w, ox + ow) - x
        if end - start > EPS:
            runs.append(("N", start, end))
    if abs(x - (ox + ow)) < 0.02:  # other is left: my W wall
        start = max(y, oy) - y
        end = min(y + d, oy + od) - y
        if end - start > EPS:
            runs.append(("W", start, end))
    if abs(x + w - ox) < 0.02:  # other is right: my E wall
        start = max(y, oy) - y
        end = min(y + d, oy + od) - y
        if end - start > EPS:
            runs.append(("E", start, end))
    return runs


def _exterior_runs(rect, rects):
    """Exterior runs per wall: {side: [(start, end)]}.

    Walls facing another indoor room are blocked; walls facing a garden,
    veranda or porch (open air) stay window-able.
    """
    runs = {}
    for side in ("N", "S", "E", "W"):
        blocked = []
        for other in rects:
            if other is rect or other["type"] in OPEN_TYPES:
                continue
            for run_side, start, end in _shared_with(rect, other):
                if run_side == side:
                    blocked.append((start, end))
        blocked.sort()
        free, cursor = [], 0.0
        for start, end in blocked:
            if start > cursor + EPS:
                free.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < _wall_length(rect, side) - EPS:
            free.append((cursor, _wall_length(rect, side)))
        runs[side] = free
    return runs


def wall_compass(side, north_angle=0.0):
    """Plot-relative compass bearing of a local wall's outward normal.

    0 = plot north (the north angle), clockwise; road-ward is always the
    local S wall (180 from plot north).
    """
    try:
        angle = float(north_angle) % 360.0
    except (TypeError, ValueError):
        angle = 0.0
    offset = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}[side]
    return (angle + offset) % 360.0


def _window_rank(side, north_angle):
    """Lower ranks first: south/southeast preferred, west avoided."""
    bearing = wall_compass(side, north_angle)
    target = abs((bearing - 157.5 + 180.0) % 360.0 - 180.0)
    west = abs((bearing - 270.0 + 180.0) % 360.0 - 180.0)
    if west < 45.0:
        target += 1000.0
    return target


def _wall_end_clearance(rect, side, end, rects):
    """Corner clearance (ft) at one wall end: 4 in at a true corner, 0
    where another indoor room continues the same wall plane past the
    end (a T-junction partition, not a corner)."""
    x, y, w, d = rect["x"], rect["y"], rect["w"], rect["d"]
    if side == "S":
        line, fixed, span = (x, x + w), y, "h"
    elif side == "N":
        line, fixed, span = (x, x + w), y + d, "h"
    elif side == "W":
        line, fixed, span = (y, y + d), x, "v"
    else:
        line, fixed, span = (y, y + d), x + w, "v"
    edge = line[end]
    for other in rects:
        if other is rect or other["type"] in OPEN_TYPES:
            continue
        ox, oy, ow, od = other["x"], other["y"], other["w"], other["d"]
        if span == "h":
            for ofixed, ospan in ((oy, (ox, ox + ow)),
                                  (oy + od, (ox, ox + ow))):
                if abs(ofixed - fixed) > 0.02:
                    continue
                if ospan[0] < edge - 0.02 and ospan[1] > edge + 0.02:
                    return 0.0
                if end == 0 and ospan[1] >= edge - 0.02 \
                        and ospan[0] < edge - 0.02:
                    return 0.0
                if end == 1 and ospan[0] <= edge + 0.02 \
                        and ospan[1] > edge + 0.02:
                    return 0.0
        else:
            for ofixed, ospan in ((ox, (oy, oy + od)),
                                  (ox + ow, (oy, oy + od))):
                if abs(ofixed - fixed) > 0.02:
                    continue
                if ospan[0] < edge - 0.02 and ospan[1] > edge + 0.02:
                    return 0.0
                if end == 0 and ospan[1] >= edge - 0.02 \
                        and ospan[0] < edge - 0.02:
                    return 0.0
                if end == 1 and ospan[0] <= edge + 0.02 \
                        and ospan[1] > edge + 0.02:
                    return 0.0
    return CORNER_CLR_FT


def _gap_center(length, width, prefer, keepouts, low_clr=None,
                high_clr=None):
    """Center for a width-long gap: corners cleared, keepouts avoided."""
    if low_clr is None:
        low_clr = CORNER_CLR_FT
    if high_clr is None:
        high_clr = CORNER_CLR_FT
    low = low_clr + width / 2.0
    high = length - high_clr - width / 2.0
    if high < low - EPS:
        return None
    center = min(max(prefer, low), high)
    for _ in range(12):
        clash = None
        for start, end in keepouts:
            if center + width / 2.0 > start + EPS \
                    and center - width / 2.0 < end - EPS:
                clash = (start, end)
                break
        if clash is None:
            return center
        start, end = clash
        left = start - width / 2.0 - EPS
        right = end + width / 2.0 + EPS
        if abs(left - prefer) < abs(right - prefer) and left >= low - EPS:
            center = max(left, low)
        elif right <= high + EPS:
            center = min(right, high)
        elif left >= low - EPS:
            center = max(left, low)
        else:
            return None
    for start, end in keepouts:
        if center + width / 2.0 > start + EPS \
                and center - width / 2.0 < end - EPS:
            return None
    return center


class _Placer:
    """Positions door/window gaps wall by wall, clash-free."""

    def __init__(self, rects, open_pairs=None):
        self.rects = rects
        self.by_name = {r["name"]: r for r in rects}
        self.open_pairs = open_pairs or set()
        self.doors = []
        self.windows = []
        self.problems = []  # door misses: rule 12 fails on these
        self.window_notes = []  # window misses: rule 20 bends on these
        self.gaps = {}  # (room, side) -> [(start, end)]

    def _keepouts(self, name, side):
        return self.gaps.setdefault((name, side), [])

    def _record(self, name, side, center, width):
        self._keepouts(name, side).append((center - width / 2.0,
                                           center + width / 2.0))

    def _locate_gap(self, rect, x0, y0, x1, y1):
        """(side, center) of a gap on one room's walls, None if absent."""
        for side in ("N", "S", "E", "W"):
            ex0, ey0, ex1, ey1 = _wall_ends(rect, side)
            if side in ("N", "S"):
                if abs(y0 - ey0) > 0.02 or abs(y1 - ey1) > 0.02:
                    continue
                lo, hi = sorted((x0, x1))
                if lo < ex0 - 0.02 or hi > ex1 + 0.02:
                    continue
                return (side, (lo + hi) / 2.0 - ex0)
            if abs(x0 - ex0) > 0.02 or abs(x1 - ex1) > 0.02:
                continue
            lo, hi = sorted((y0, y1))
            if lo < ey0 - 0.02 or hi > ey1 + 0.02:
                continue
            return (side, (lo + hi) / 2.0 - ey0)
        return None

    def _fit_side(self, host_name, other_name, width, prefer="mid"):
        """(side, center) for a door on one room's wall, None if none."""
        host = self.by_name[host_name]
        other = self.by_name[other_name]
        runs = _shared_with(host, other)
        runs.sort(key=lambda run: -(run[2] - run[1]))
        for side, start, end in runs:
            if end - start < width - EPS:
                continue
            low_clr = _wall_end_clearance(host, side, 0, self.rects)
            high_clr = _wall_end_clearance(host, side, 1, self.rects)
            if prefer == "start":
                wish = start + width / 2.0
            else:
                wish = (start + end) / 2.0
            center = _gap_center(_wall_length(host, side), width, wish,
                                 self._keepouts(host_name, side), low_clr,
                                 high_clr)
            if center is None:
                continue
            if center - width / 2.0 < start - EPS \
                    or center + width / 2.0 > end + EPS:
                continue
            return (side, center)
        return None

    def _add_door(self, kind, width, room, into, swing,
                  prefer="mid"):
        host = self.by_name.get(room)
        other = self.by_name.get(into)
        if host is None or other is None:
            self.problems.append("no %s door: %s or %s missing"
                                 % (kind, room, into))
            return False
        # Either room's wall can carry the gap (same physical wall); the
        # overlap often sits mid-wall on one side, at a corner other.
        fit = self._fit_side(room, into, width, prefer)
        wall_room = room
        if fit is None:
            fit = self._fit_side(into, room, width, prefer)
            wall_room = into
        if fit is None:
            self.problems.append("%s door %s -> %s does not fit"
                                 % (kind, room, into))
            return False
        side, center = fit
        wall_host = self.by_name[wall_room]
        x0, y0 = _point_on_wall(wall_host, side, center - width / 2.0)
        x1, y1 = _point_on_wall(wall_host, side, center + width / 2.0)
        # The gap occupies both rooms' walls: reserve it on each.
        sides = {}
        for name in (room, into):
            located = self._locate_gap(self.by_name[name], x0, y0, x1, y1)
            if located is not None:
                sides[name] = located[0]
                self._record(name, located[0], located[1], width)
        self.doors.append({"kind": kind, "width": width, "room": room,
                           "into": into, "wall": side,
                           "wall_room": wall_room, "swing": swing,
                           "sides": sides,
                           "x0": x0, "y0": y0, "x1": x1, "y1": y1})
        return True

    def _try_silent(self, kind, width, room, into, swing):
        """Best-effort door: no problem recorded on a miss."""
        before = len(self.problems)
        placed = self._add_door(kind, width, room, into, swing)
        if not placed:
            del self.problems[before:]
        return placed

    def _add_window(self, room, width, north_angle, ban_sides=()):
        host = self.by_name.get(room)
        if host is None:
            return False
        runs = _exterior_runs(host, self.rects)
        sides = sorted(("N", "S", "E", "W"),
                       key=lambda s: _window_rank(s, north_angle))
        for side in sides:
            if side in ban_sides:
                continue
            for start, end in runs[side]:
                if end - start < width - EPS:
                    continue
                low_clr = _wall_end_clearance(host, side, 0, self.rects)
                high_clr = _wall_end_clearance(host, side, 1, self.rects)
                center = _gap_center(_wall_length(host, side), width,
                                     (start + end) / 2.0,
                                     self._keepouts(room, side), low_clr,
                                     high_clr)
                if center is None:
                    continue
                if center - width / 2.0 < start - EPS \
                        or center + width / 2.0 > end + EPS:
                    continue
                self._record(room, side, center, width)
                x0, y0 = _point_on_wall(host, side, center - width / 2.0)
                x1, y1 = _point_on_wall(host, side, center + width / 2.0)
                self.windows.append({"room": room, "wall": side,
                                     "width": width, "x0": x0, "y0": y0,
                                     "x1": x1, "y1": y1,
                                     "compass": wall_compass(side,
                                                             north_angle)})
                return True
        return False


def _first_of(rects, *names):
    by_name = {r["name"]: r for r in rects}
    for name in names:
        if name in by_name:
            return name
    return ""


def _subtract_spans(runs, cuts):
    """runs minus cuts: [(start, end)] with the cuts removed."""
    out = []
    for start, end in runs:
        cursor = start
        for cut0, cut1 in sorted(cuts):
            if cut1 <= cursor + EPS or cut0 >= end - EPS:
                continue
            if cut0 > cursor + EPS:
                out.append((cursor, min(cut0, end)))
            cursor = max(cursor, cut1)
        if cursor < end - EPS:
            out.append((cursor, end))
    return out


def wall_segments(rects, doors, windows, open_plan=None):
    """Solid wall bands for the drawing: [{"x0".."y1", "kind"}].

    Local plot coordinates (feet), already thickened: 10 in exterior,
    5 in interior, centered on each room edge. Door/window gaps are
    subtracted; open-plan pairs share no wall at all. Porch, verandas
    and gardens are open air (their rooms' walls still stand).
    """
    open_pairs = set()
    for pair in open_plan or []:
        names = list(pair)
        if len(names) >= 2:
            open_pairs.add(frozenset(names[:2]))
    by_name = {r["name"]: r for r in rects}
    gaps = {}
    for door in doors:
        for name, side in door.get("sides", {}).items():
            rect = by_name.get(name)
            if rect is None:
                continue
            span = _interval_on_wall(rect, side, door["x0"], door["y0"],
                                     door["x1"], door["y1"])
            if span is not None:
                gaps.setdefault((name, side), []).append(span)
    for win in windows:
        rect = by_name.get(win["room"])
        if rect is None:
            continue
        span = _interval_on_wall(rect, win["wall"], win["x0"], win["y0"],
                                 win["x1"], win["y1"])
        if span is not None:
            gaps.setdefault((win["room"], win["wall"]), []).append(span)
    segments = []
    for rect in rects:
        if rect["type"] in UNWALLED_TYPES:
            continue
        for side in ("N", "S", "E", "W"):
            length = _wall_length(rect, side)
            shared, open_run = [], []
            for other in rects:
                if other is rect \
                        or other["type"] in UNWALLED_TYPES:
                    continue
                pair = frozenset((rect["name"], other["name"]))
                for run_side, start, end in _shared_with(rect, other):
                    if run_side == side:
                        (open_run if pair in open_pairs
                         else shared).append((start, end))
            blocked = sorted(shared + open_run)
            covered = []
            for start, end in blocked:
                if covered and start <= covered[-1][1] + EPS:
                    covered[-1][1] = max(covered[-1][1], end)
                else:
                    covered.append([start, end])
            exterior, cursor = [], 0.0
            for start, end in covered:
                if start > cursor + EPS:
                    exterior.append((cursor, start))
                cursor = max(cursor, end)
            if cursor < length - EPS:
                exterior.append((cursor, length))
            cuts = gaps.get((rect["name"], side), [])
            for start, end in _subtract_spans(exterior, cuts):
                segments.append(_thick_rect(rect, side, start, end,
                                            EXT_WALL_FT, "ext"))
            for start, end in _subtract_spans(shared, cuts):
                segments.append(_thick_rect(rect, side, start, end,
                                            INT_WALL_FT, "int"))
    return segments


def _thick_rect(rect, side, start, end, thick, kind):
    """Axis-aligned wall band over one wall run, local coords."""
    half = thick / 2.0
    x, y, w, d = rect["x"], rect["y"], rect["w"], rect["d"]
    if side == "S":
        box = (x + start, y - half, x + end, y + half)
    elif side == "N":
        box = (x + start, y + d - half, x + end, y + d + half)
    elif side == "W":
        box = (x - half, y + start, x + half, y + end)
    else:
        box = (x + w - half, y + start, x + w + half, y + end)
    return {"x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3],
            "kind": kind}


def _interval_on_wall(rect, side, x0, y0, x1, y1):
    """(start, end) of a gap's endpoints along one wall, None if off it."""
    ex0, ey0, ex1, ey1 = _wall_ends(rect, side)
    if side in ("N", "S"):
        if abs(y0 - ey0) > 0.02 or abs(y1 - ey1) > 0.02:
            return None
        lo, hi = sorted((x0, x1))
        if lo < ex0 - 0.02 or hi > ex1 + 0.02:
            return None
        return (lo - ex0, hi - ex0)
    if abs(x0 - ex0) > 0.02 or abs(x1 - ex1) > 0.02:
        return None
    lo, hi = sorted((y0, y1))
    if lo < ey0 - 0.02 or hi > ey1 + 0.02:
        return None
    return (lo - ey0, hi - ey0)


def audit_gaps(rects, doors, windows):
    """Re-verify every gap: corner clearance + no clashes on a wall.

    Independent of the placer (works from endpoints, not placement
    records): a gap too close to a true corner, or two gaps
    overlapping on one wall, is a violation string. [] means clean.
    """
    by_name = {r["name"]: r for r in rects}
    on_wall = {}  # (name, side) -> [(start, end, label)]
    for door in doors:
        label = "%s door %s -> %s" % (door["kind"], door["room"],
                                      door["into"])
        for name, side in door.get("sides", {}).items():
            rect = by_name.get(name)
            if rect is None:
                continue
            span = _interval_on_wall(rect, side, door["x0"], door["y0"],
                                     door["x1"], door["y1"])
            if span is None:
                continue
            on_wall.setdefault((name, side), []).append(
                (span[0], span[1], label))
    for win in windows:
        rect = by_name.get(win["room"])
        if rect is None:
            continue
        span = _interval_on_wall(rect, win["wall"], win["x0"], win["y0"],
                                 win["x1"], win["y1"])
        if span is None:
            continue
        on_wall.setdefault((win["room"], win["wall"]), []).append(
            (span[0], span[1], "window in %s" % win["room"]))
    violations = []
    for (name, side), spans in sorted(on_wall.items()):
        rect = by_name[name]
        length = _wall_length(rect, side)
        low_clr = _wall_end_clearance(rect, side, 0, rects)
        high_clr = _wall_end_clearance(rect, side, 1, rects)
        for start, end, label in spans:
            if start < low_clr - 0.02 \
                    or end > length - high_clr + 0.02:
                violations.append("%s too close to the %s corner"
                                  % (label, side))
        ordered = sorted(spans)
        for first, second in zip(ordered, ordered[1:]):
            if first[1] > second[0] + EPS:
                violations.append("%s clashes %s on %s %s"
                                  % (first[2], second[2], name, side))
    return violations


def place_openings(rects, open_plan=None, north_angle=0.0):
    """Place every door and window. Returns {"doors", "windows",
    "problems"} in local plot coordinates (feet).

    open_plan: [(name_a, name_b)] pairs whose shared wall stays open (no
    wall, no door between them). problems: human-readable misses the
    checker reports (missing doors, clashes, walls too short).
    """
    open_pairs = set()
    for pair in open_plan or []:
        names = list(pair)
        if len(names) >= 2:
            open_pairs.add(frozenset(names[:2]))
    placer = _Placer(rects, open_pairs)
    by_type = {}
    for rect in rects:
        by_type.setdefault(rect["type"], []).append(rect)

    def is_open(first, second):
        return frozenset((first, second)) in open_pairs

    # Entry: porch -> foyer, swings into the foyer.
    porches = by_type.get("porch", [])
    foyers = by_type.get("foyer", [])
    if porches and foyers:
        placer._add_door("entry", ENTRY_W_FT, porches[0]["name"],
                         foyers[0]["name"], foyers[0]["name"])
    elif foyers:
        placer.problems.append("no entry door: porch missing")

    # Hub rooms (foyer, living, dining, family) join over the shared
    # walls they really have: the spine order first, then every other
    # hub pair. Open-plan pairs share one space (no door, no wall).
    # Single links are best-effort; only a disconnected hub is a miss.
    living = _first_of(rects, "Living Room")
    dining = _first_of(rects, "Dining")
    family = _first_of(rects, "Family Living")
    foyer = foyers[0]["name"] if foyers else ""
    hubs = [name for name in (foyer, living, dining, family) if name]
    for first, second in ((foyer, living), (living, dining),
                          (dining, family), (foyer, dining),
                          (foyer, family), (living, family)):
        if first and second and not is_open(first, second):
            placer._try_silent("room", ROOM_W_FT, first, second, second)
    if hubs:
        seen, queue = {hubs[0]}, [hubs[0]]
        links = {}
        for door in placer.doors:
            links.setdefault(door["room"], []).append(door["into"])
            links.setdefault(door["into"], []).append(door["room"])
        for pair in open_pairs:  # one open space joins better than a door
            names = list(pair)
            links.setdefault(names[0], []).append(names[1])
            links.setdefault(names[1], []).append(names[0])
        while queue:
            for nxt in links.get(queue.pop(0), []):
                if nxt in hubs and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        for name in hubs:
            if name not in seen:
                placer.problems.append(
                    "%s has no door into the hub rooms" % name)

    # Bedrooms -> family, else dining (never living/foyer).
    fams = [r["name"] for r in by_type.get("family living", [])]
    dins = [r["name"] for r in by_type.get("dining", [])]
    for bed in by_type.get("bedroom", []):
        placed = False
        for target in fams + dins:
            if placer._add_door("room", ROOM_W_FT, bed["name"], target,
                                bed["name"]):
                placed = True
                break
            placer.problems.pop()
        if not placed:
            placer.problems.append("bedroom door %s -> family/dining "
                                   "does not fit" % bed["name"])

    # Kitchen -> dining (unless open-merged with a hub room: one
    # space needs no door), plus one to its own veranda. Veranda doors
    # hug the run's start so the room's window still fits beside them.
    for kitchen in by_type.get("kitchen", []):
        merged = any(is_open(kitchen["name"], hub) for hub in hubs)
        if dins and not merged:
            placer._add_door("room", ROOM_W_FT, kitchen["name"], dins[0],
                             kitchen["name"])
        elif not dins and not merged:
            placer.problems.append("no room door: %s or Dining missing"
                                   % kitchen["name"])
        for veranda in by_type.get("veranda", []):
            if veranda.get("veranda_for") == kitchen["name"]:
                placer._add_door("veranda", VERANDA_W_FT, kitchen["name"],
                                 veranda["name"], kitchen["name"],
                                 prefer="start")

    # Bathrooms: attached -> own bedroom only; common -> dining/family.
    for bath in by_type.get("bathroom", []):
        if bath.get("bathroom_kind") == "attached" and bath.get(
                "attached_to"):
            placer._add_door("toilet", TOILET_W_FT, bath["name"],
                             bath["attached_to"], bath["name"])
        else:
            placed = False
            for target in dins + fams:
                if placer._add_door("toilet", TOILET_W_FT, bath["name"],
                                    target, bath["name"]):
                    placed = True
                    break
                placer.problems.pop()
            if not placed:
                placer.problems.append(
                    "common toilet door %s -> dining/family does not fit"
                    % bath["name"])

    # Storage -> nearest hub room.
    for store in by_type.get("storage", []):
        placed = False
        hubs = [r["name"] for kind in
                ("kitchen", "dining", "family living", "living room",
                 "foyer") for r in by_type.get(kind, [])]
        for target in hubs:
            if placer._add_door("room", ROOM_W_FT, store["name"], target,
                                store["name"]):
                placed = True
                break
            placer.problems.pop()
        if not placed:
            placer.problems.append("storage door %s has no hub wall"
                                   % store["name"])

    # Each veranda: one door from its own room.
    for veranda in by_type.get("veranda", []):
        host = veranda.get("veranda_for", "")
        if not host or host == veranda["name"]:
            continue
        if placer.by_name.get(host, {}).get("type") == "kitchen":
            continue  # placed with the kitchen above
        if any(d["room"] == host and d["into"] == veranda["name"]
               for d in placer.doors):
            continue
        placer._add_door("veranda", VERANDA_W_FT, host, veranda["name"],
                         host, prefer="start")

    # Windows: bedrooms two preferred (opposite wall first).
    for bed in by_type.get("bedroom", []):
        first = placer._add_window(bed["name"], BED_WIN_FT, north_angle)
        if not first:
            placer.window_notes.append("no window wall for %s"
                                       % bed["name"])
            continue
        used = [w["wall"] for w in placer.windows
                if w["room"] == bed["name"]][0]
        opposite = {"N": "S", "S": "N", "E": "W", "W": "E"}[used]
        others = tuple(s for s in ("N", "S", "E", "W") if s != opposite)
        if not placer._add_window(bed["name"], BED_WIN_FT, north_angle,
                                  ban_sides=others):
            placer._add_window(bed["name"], BED_WIN_FT, north_angle,
                               ban_sides=(used,))
    for room in by_type.get("living room", []):
        if not placer._add_window(room["name"], LIVING_WIN_FT,
                                  north_angle):
            placer.window_notes.append("no window wall for %s"
                                       % room["name"])
    for room in by_type.get("dining", []) + by_type.get("family living",
                                                        []):
        if not placer._add_window(room["name"], COMMON_WIN_FT,
                                  north_angle):
            placer.window_notes.append("no window wall for %s"
                                       % room["name"])
    for room in by_type.get("kitchen", []):
        if not placer._add_window(room["name"], KITCHEN_WIN_FT,
                                  north_angle):
            placer.window_notes.append("no window wall for %s"
                                       % room["name"])
    for bath in by_type.get("bathroom", []):
        if not placer._add_window(bath["name"], BATH_WIN_FT, north_angle,
                                  ban_sides=("S",)):
            placer.window_notes.append("no window wall for %s"
                                       % bath["name"])

    return {"doors": placer.doors, "windows": placer.windows,
            "problems": placer.problems,
            "window_notes": placer.window_notes}
