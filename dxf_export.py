# dxf_export.py
# House Planner: plan option -> DXF (AutoCAD) download (plain Python, no CAD lib).
#
# What this file does: turns one placed plan option into a minimal DXF R12
# ASCII string with the same geometry draw.py renders as SVG: plot boundary,
# dashed setback line, rooms with names/sizes/areas, walls with the real
# door/window gaps (the same openings.py placement the SVG draws and
# layout.py checks, so the two drawings cannot disagree), door leafs +
# swing arcs, windows, glass partitions, overall dimensions, north arrow
# and ROAD label. One drawing unit is one inch ($INSUNITS = 1), y-up,
# the road on its real side - the DXF matches the on-screen plan
# orientation, and dimensions read correctly under AutoCAD's
# architectural units. Only LINE, ARC, CIRCLE and TEXT entities are
# used, so every CAD reader (AutoCAD, LibreCAD, DWG TrueView, ...)
# opens it. No third-party package is needed, so the Streamlit Cloud
# deploy is unaffected. All geometry is computed in feet (like the
# placer) and converted to inches once, inside the entity writers.
#
# Layers (each with its own color): PLOT gray, SETBACK magenta dashed,
# ROAD gray, WALLS white, DOORS yellow, WINDOWS cyan, GLASS blue,
# VERANDA orange (porch + veranda outlines), LANDSCAPE light green
# (garden + court outlines, dashed), TEXT green, DIMS red, NORTH white.
# There is deliberately no wall hatch: the HATCH entity does not exist
# in DXF R12 (it arrived with R13), so walls stay clean outlines.
# DXF R12 text is ASCII-only, so non-ASCII room features (e.g. Bengali
# wishes) render as "?" - names, sizes and areas always come from our
# own ASCII code.
#
# Orientation: same road rotation as draw.svg_plan (closest cardinal for
# angled plots); the north arrow turns with the residual angle.

import math

from ai_program import (
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    format_ft_in,
)
from layout import SHORT_NAMES
from openings import UNWALLED_TYPES, place_openings, wall_segments


def _num(value):
    """Compact DXF number: up to 4 decimals, never an exponent."""
    text = "%.4f" % float(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", "", "-"):
        text = "0"
    return text


def _inch(feet):
    """Feet (placer units) -> drawing units (inches)."""
    return float(feet) * 12.0


def _clean(text):
    """DXF R12 text: one line, ASCII-only, literal % escaped."""
    out = str(text).replace("\r", " ").replace("\n", " ")
    out = out.encode("ascii", errors="replace").decode("ascii")
    return out.replace("%", "%%%")


def _line(layer, x0, y0, x1, y1, ltype=None):
    """One LINE entity on a layer (takes feet, writes inches)."""
    out = ["0", "LINE", "8", layer]
    if ltype:
        out += ["6", ltype]
    out += ["10", _num(_inch(x0)), "20", _num(_inch(y0)), "30", "0.0",
            "11", _num(_inch(x1)), "21", _num(_inch(y1)), "31", "0.0"]
    return "\n".join(out)


def _rect(layer, x0, y0, x1, y1, ltype=None):
    """Closed rectangle outline as four LINEs."""
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    return "\n".join([
        _line(layer, xa, ya, xb, ya, ltype),
        _line(layer, xb, ya, xb, yb, ltype),
        _line(layer, xb, yb, xa, yb, ltype),
        _line(layer, xa, yb, xa, ya, ltype),
    ])


def _arc(layer, cx, cy, radius, start_deg, end_deg):
    """One ARC entity (takes feet, writes inches; CCW degrees)."""
    return "\n".join([
        "0", "ARC", "8", layer,
        "10", _num(_inch(cx)), "20", _num(_inch(cy)), "30", "0.0",
        "40", _num(_inch(radius)),
        "50", _num(start_deg % 360.0), "51", _num(end_deg % 360.0),
    ])


def _circle(layer, cx, cy, radius):
    """One CIRCLE entity (takes feet, writes inches)."""
    return "\n".join([
        "0", "CIRCLE", "8", layer,
        "10", _num(_inch(cx)), "20", _num(_inch(cy)), "30", "0.0",
        "40", _num(_inch(radius)),
    ])


def _text(layer, x, y, height, string, rotation=0.0, centered=True):
    """One TEXT entity (takes feet, writes inches; centered by default)."""
    out = ["0", "TEXT", "8", layer,
           "10", _num(_inch(x)), "20", _num(_inch(y)), "30", "0.0",
           "40", _num(_inch(height)), "1", _clean(string)]
    if abs(rotation) > 0.001:
        out += ["50", _num(rotation % 360.0)]
    if centered:
        out += ["72", "1", "11", _num(_inch(x)), "21", _num(_inch(y)),
                "31", "0.0"]
    return "\n".join(out)


def dxf_plan(result):
    """Render one plan option as a DXF R12 string.

    Takes the same dict as draw.svg_plan: {"ok", "placements",
    "open_plan", "glass_partitions", "plot": {"w", "d", "road",
    "north_angle"}}.
    """
    plot = result.get("plot", {})
    road = str(plot.get("road", "south")).strip().lower()
    if road not in ("north", "south", "east", "west"):
        road = "south"
    plot_w = float(plot.get("w", 40))
    plot_d = float(plot.get("d", 60))
    rooms = result.get("placements", []) if result.get("ok") else []
    base = {"south": 0.0, "east": 90.0, "north": 180.0, "west": 270.0}[road]
    try:
        angle = float(plot.get("north_angle", base)) % 360.0
    except (TypeError, ValueError):
        angle = base
    residual = ((angle - base + 180.0) % 360.0) - 180.0

    draw_w = plot_w if road in ("north", "south") else plot_d
    draw_d = plot_d if road in ("north", "south") else plot_w

    def point(x, y):
        """Local plot coords -> drawing coords (feet, y-up, road on side).

        Same orientation as the SVG plan: the road edge (local y = 0)
        lands at the bottom (south), top (north), right (east) or left
        (west) of the drawn rectangle. The entity writers convert
        these feet to inches ($INSUNITS = 1).
        """
        if road == "south":
            return x, y
        if road == "north":
            return x, plot_d - y
        if road == "east":
            return plot_d - y, x
        return y, plot_w - x  # west

    ent = []
    # Plot boundary + dashed setback line.
    ent.append(_rect("PLOT", 0, 0, draw_w, draw_d))
    sx0, sy0 = point(SETBACK_SIDE_FT, SETBACK_FRONT_FT)
    sx1, sy1 = point(plot_w - SETBACK_SIDE_FT, plot_d - SETBACK_BACK_FT)
    ent.append(_rect("SETBACK", sx0, sy0, sx1, sy1))
    ent.append(_text("TEXT", min(sx0, sx1) + 0.3, max(sy0, sy1) - 0.6,
                     0.55, "setback line", centered=False))

    # Road edge + ROAD label outside it.
    rx0, ry0 = point(0, 0)
    rx1, ry1 = point(plot_w, 0)
    ent.append(_line("ROAD", rx0, ry0, rx1, ry1))
    if road == "south":
        road_xy = (draw_w / 2, -3.6)
    elif road == "north":
        road_xy = (draw_w / 2, draw_d + 1.3)
    elif road == "east":
        road_xy = (draw_w + 2.2, draw_d / 2)
    else:
        road_xy = (-2.2, draw_d / 2)
    ent.append(_text("ROAD", road_xy[0], road_xy[1], 1.0, "ROAD"))

    # Rooms: thin outlines for open-air rooms (walled rooms are
    # outlined by their wall bands) + centered labels for all.
    for room in rooms:
        ax, ay = point(room["x"], room["y"])
        bx, by = point(room["x"] + room["w"], room["y"] + room["d"])
        room_type = str(room.get("type", ""))
        if room_type in UNWALLED_TYPES:
            if room_type == "garden":
                # Gardens + courts (courts are type "garden").
                ent.append(_rect("LANDSCAPE", ax, ay, bx, by, "DASHED"))
            else:  # porch, veranda
                ent.append(_rect("VERANDA", ax, ay, bx, by))
        ent.append(_room_text(room, point))
        if room.get("screened_jali"):
            # Jali/screen wall: a line just outside the road edge.
            jx0, jy0 = point(room["x"], room["y"] - 0.3)
            jx1, jy1 = point(room["x"] + room["w"], room["y"] - 0.3)
            ent.append(_line("VERANDA", jx0, jy0, jx1, jy1))

    # Walls (same placement the SVG draws), doors, windows.
    glass = result.get("glass_partitions", [])
    placed = place_openings(rooms, result.get("open_plan", []), angle,
                            glass)
    for segment in wall_segments(rooms, placed["doors"],
                                 placed["windows"],
                                 result.get("open_plan", []), glass):
        if segment["kind"] == "glass":
            ent.append(_window_lines(segment, point, "GLASS"))
        else:
            ax, ay = point(segment["x0"], segment["y0"])
            bx, by = point(segment["x1"], segment["y1"])
            ent.append(_rect("WALLS", ax, ay, bx, by))
    by_name = {r.get("name", ""): r for r in rooms}
    for door in placed["doors"]:
        ent.append(_door_dxf(door, by_name, point))
    for win in placed["windows"]:
        ent.append(_window_lines(win, point, "WINDOWS"))
    if not rooms:
        ent.append(_text("TEXT", draw_w / 2, draw_d / 2, 0.9,
                         "No rooms placed - see notes."))

    # Overall dimensions: frontage + depth, outside the plot rect
    # (mirror of draw.svg_plan, converted to y-up feet).
    if road == "south":
        width_edge = ((0, 0), (draw_w, 0))
        depth_edge = ((0, 0), (0, draw_d))
        width_side, depth_side = "below", "left"
    elif road == "north":
        width_edge = ((0, 0), (draw_w, 0))
        depth_edge = ((0, 0), (0, draw_d))
        width_side, depth_side = "below", "left"
    elif road == "east":
        width_edge = ((0, 0), (0, draw_d))
        depth_edge = ((0, 0), (draw_w, 0))
        width_side, depth_side = "left", "below"
    else:  # west
        width_edge = ((draw_w, 0), (draw_w, draw_d))
        depth_edge = ((0, 0), (draw_w, 0))
        width_side, depth_side = "right", "below"
    ent.append(_dim_dxf(width_edge[0], width_edge[1], width_side,
                        format_ft_in(plot_w)))
    ent.append(_dim_dxf(depth_edge[0], depth_edge[1], depth_side,
                        format_ft_in(plot_d)))

    # North arrow (right of the plan) + title lines above it.
    arrow_x = draw_w + (5.0 if road == "west" else 3.8)
    ent.append(_north_dxf(arrow_x, draw_d - 1.8, residual))
    ent.append(_text("TEXT", 0, draw_d + 3.6, 1.1,
                     "House Planner - concept floor plan",
                     centered=False))
    ent.append(_text("TEXT", 0, draw_d + 2.5, 0.7,
                     _subtitle(plot_w, plot_d, road, angle,
                               "north_angle" in plot),
                     centered=False))
    return _assemble([e for e in ent if e])


def _subtitle(plot_w, plot_d, road, angle, explicit_angle):
    """Same subtitle line as the SVG plan title block."""
    if explicit_angle:
        head = "Plot %s x %s, road %s, north %g deg. " % (
            format_ft_in(plot_w), format_ft_in(plot_d),
            road.capitalize(), angle)
    else:
        head = "Plot %s x %s, road %s (north up). " % (
            format_ft_in(plot_w), format_ft_in(plot_d),
            road.capitalize())
    return head + "Concept only - not for construction."


def _room_text(room, point):
    """Centered label lines for one room (name, size, area, features)."""
    ax, ay = point(room["x"], room["y"])
    bx, by = point(room["x"] + room["w"], room["y"] + room["d"])
    x, y = min(ax, bx), min(ay, by)
    w, h = abs(bx - ax), abs(by - ay)
    cx, cy = x + w / 2, y + h / 2
    name = str(room.get("name", "?"))
    short = SHORT_NAMES.get(str(room.get("type", "")), name.split(" ")[0])
    label = name if len(name) * 0.56 < w - 0.4 else short
    if str(room.get("type", "")) == "foyer":
        # Rule 34: the foyer is a labeled zone, not a room.
        return _text("TEXT", cx, cy, 0.7 if h >= 2.0 else 0.55, "Foyer")
    if h < 1.2:
        return _text("TEXT", cx, cy, 0.55, label)
    out = [_text("TEXT", cx, cy + 0.55, 0.7, label),
           _text("TEXT", cx, cy - 0.35, 0.55,
                 "%s x %s" % (format_ft_in(room["w"]),
                               format_ft_in(room["d"])))]
    if h < 2.2:
        return "\n".join(out)
    try:
        area = "%d sq ft" % round(float(room["w"]) * float(room["d"]))
    except (TypeError, ValueError):
        area = ""
    if area:
        out.append(_text("TEXT", cx, cy - 1.1, 0.55, area))
    for pos, feat in enumerate(list(room.get("features") or [])[:2]):
        yy = cy - 1.8 - pos * 0.55
        if yy < y + 0.3:
            break
        out.append(_text("TEXT", cx, yy, 0.45, str(feat)[:28]))
    return "\n".join(out)


def _door_dxf(door, by_name, point):
    """Door leaf (open 90 deg, against the wall) + swing arc."""
    ends = [point(door["x0"], door["y0"]),
            point(door["x1"], door["y1"])]
    hx, hy = ends[door.get("hinge", 0)]  # hinge on the corner side
    ex, ey = ends[1 - door.get("hinge", 0)]  # gap end
    swing = by_name.get(door.get("swing", ""), {})
    try:
        cx = float(swing["x"]) + float(swing["w"]) / 2.0
        cy = float(swing["y"]) + float(swing["d"]) / 2.0
    except (TypeError, ValueError, KeyError):
        cx, cy = door["x0"], door["y0"]
    scx, scy = point(cx, cy)
    dx, dy = ex - hx, ey - hy
    gap = math.hypot(dx, dy)
    if gap < 0.01:
        return ""
    nx, ny = -dy / gap, dx / gap  # wall normal, flipped into the room
    if nx * (scx - hx) + ny * (scy - hy) < 0:
        nx, ny = -nx, -ny
    radius = float(door["width"])
    lx, ly = hx + nx * radius, hy + ny * radius  # leaf end
    start = math.degrees(math.atan2(ly - hy, lx - hx)) % 360.0
    end = math.degrees(math.atan2(ey - hy, ex - hx)) % 360.0
    if (end - start) % 360.0 > 180.0:
        # DXF arcs run counter-clockwise: keep the 90-degree minor arc
        # no matter which way the road rotation mirrors the plan.
        start, end = end, start
    return _line("DOORS", hx, hy, lx, ly) + "\n" + \
        _arc("DOORS", hx, hy, radius, start, end)


def _window_lines(win, point, layer):
    """Window/glass: two thin lines across the gap, 3 in apart."""
    ax, ay = point(win["x0"], win["y0"])
    bx, by = point(win["x1"], win["y1"])
    dx, dy = bx - ax, by - ay
    gap = math.hypot(dx, dy)
    if gap < 0.01:
        return ""
    nx, ny = -dy / gap * 0.125, dx / gap * 0.125  # 1.5 in each side
    return "\n".join([
        _line(layer, ax + nx, ay + ny, bx + nx, by + ny),
        _line(layer, ax - nx, ay - ny, bx - nx, by - ny),
    ])


def _dim_dxf(edge_a, edge_b, side, label):
    """One overall dimension: extension lines + ticked line + label."""
    (ax, ay), (bx, by) = edge_a, edge_b
    if side == "below":
        line_y = -2.2
        out = [_line("DIMS", ax, -0.2, ax, line_y - 0.3),
               _line("DIMS", bx, -0.2, bx, line_y - 0.3),
               _line("DIMS", ax, line_y, bx, line_y),
               _tick_dxf(ax, line_y), _tick_dxf(bx, line_y),
               _text("DIMS", (ax + bx) / 2, line_y + 0.55, 0.9,
                     label)]
    elif side == "left":
        line_x = -2.2
        out = [_line("DIMS", -0.2, ay, line_x - 0.3, ay),
               _line("DIMS", -0.2, by, line_x - 0.3, by),
               _line("DIMS", line_x, ay, line_x, by),
               _tick_dxf(line_x, ay), _tick_dxf(line_x, by),
               _text("DIMS", line_x - 1.0, (ay + by) / 2, 0.9, label,
                     rotation=90.0)]
    else:  # "right": mirror of left, used when labels fill the left.
        line_x = max(ax, bx) + 2.2
        out = [_line("DIMS", max(ax, bx) + 0.2, ay, line_x + 0.3, ay),
               _line("DIMS", max(ax, bx) + 0.2, by, line_x + 0.3, by),
               _line("DIMS", line_x, ay, line_x, by),
               _tick_dxf(line_x, ay), _tick_dxf(line_x, by),
               _text("DIMS", line_x + 1.0, (ay + by) / 2, 0.9, label,
                     rotation=90.0)]
    return "\n".join(out)


def _tick_dxf(x, y):
    """Small 45-degree architectural tick across a dimension line."""
    return _line("DIMS", x - 0.35, y - 0.35, x + 0.35, y + 0.35)


def _north_dxf(x, y, residual):
    """Circle + needle + N, needle turned clockwise by residual degrees."""
    radians = math.radians(residual)
    cos_r, sin_r = math.cos(radians), math.sin(radians)

    def spin(px, py):
        return (x + px * cos_r + py * sin_r,
                y - px * sin_r + py * cos_r)

    tip = spin(0.0, 0.8)
    left = spin(-0.35, -0.1)
    right = spin(0.35, -0.1)
    return "\n".join([
        _circle("NORTH", x, y, 1.0),
        _line("NORTH", tip[0], tip[1], left[0], left[1]),
        _line("NORTH", left[0], left[1], right[0], right[1]),
        _line("NORTH", right[0], right[1], tip[0], tip[1]),
        _text("NORTH", x - 0.8 * sin_r, y - 0.8 * cos_r, 0.9, "N"),
    ])


def _assemble(entities):
    """HEADER + TABLES (linetypes, layers) + ENTITIES + EOF."""
    # (name, ACI color, linetype): 1 red, 2 yellow, 3 green, 4 cyan,
    # 5 blue, 6 magenta, 7 white, 8 gray, 30 orange, 94 light green.
    layers = [("0", 7, "CONTINUOUS"), ("PLOT", 8, "CONTINUOUS"),
              ("SETBACK", 6, "DASHED"), ("ROAD", 8, "CONTINUOUS"),
              ("WALLS", 7, "CONTINUOUS"), ("DOORS", 2, "CONTINUOUS"),
              ("WINDOWS", 4, "CONTINUOUS"), ("GLASS", 5, "CONTINUOUS"),
              ("VERANDA", 30, "CONTINUOUS"),
              ("LANDSCAPE", 94, "CONTINUOUS"),
              ("TEXT", 3, "CONTINUOUS"), ("DIMS", 1, "CONTINUOUS"),
              ("NORTH", 7, "CONTINUOUS")]
    parts = ["999", "House Planner concept plan - units: inches",
             "0", "SECTION", "2", "HEADER",
             "9", "$ACADVER", "1", "AC1009",
             "9", "$INSUNITS", "70", "1",
             "9", "$LTSCALE", "40", "1.0",
             "9", "$DWGCODEPAGE", "3", "ANSI_1252",
             "0", "ENDSEC",
             "0", "SECTION", "2", "TABLES",
             "0", "TABLE", "2", "LTYPE", "70", "2",
             "0", "LTYPE", "2", "CONTINUOUS", "70", "0",
             "3", "Solid line", "72", "65", "73", "0", "40", "0.0",
             "0", "LTYPE", "2", "DASHED", "70", "0",
             "3", "Dashed __ __ __", "72", "65", "73", "2",
             "40", "1.0", "49", "0.6", "49", "-0.4",
             "0", "ENDTAB",
             "0", "TABLE", "2", "LAYER", "70", str(len(layers))]
    for name, color, ltype in layers:
        parts += ["0", "LAYER", "2", name, "70", "0", "62", str(color),
                  "6", ltype]
    parts += ["0", "ENDTAB", "0", "ENDSEC",
              "0", "SECTION", "2", "ENTITIES"]
    parts += entities
    parts += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(parts) + "\n"
