# draw.py
# Step 2 of House Planner: layout -> SVG plan drawing (plain Python, no CAD lib).
#
# What this file does: turns placed room rectangles into a clean, dimensioned
# 2D plan in SVG format: plot boundary, dashed setback line, rooms with names,
# sizes (feet-inches) and areas, solid walls (10 in exterior, 5 in
# interior), doors (wall gap + leaf + swing arc), windows (wall gap +
# double lines), overall dimensions, north arrow, road label, scale bar,
# and a concept-only note. Black lines on white, no bright colors.
# Open-plan pairs share no wall (one open space). The gaps drawn are the
# same ones openings.py places and layout.py checks.
#
# Orientation: the drawing is rotated so the road lands on its real side
# (closest cardinal for angled plots):
#   road South -> road edge at the bottom, rooms upright;
#   road North -> road edge at the top;
#   road East  -> road edge on the right, plan rotated;
#   road West  -> road edge on the left, plan rotated.
# The north arrow shows the real north angle (0 = north away from the road,
# clockwise); it points straight up only when north is due up.
# svg_plot_preview draws the bare plot (road at the bottom) for the live
# preview beside the inputs.

import math
from xml.sax.saxutils import escape

from ai_program import (
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    format_ft_in,
)
from layout import SHORT_NAMES
from openings import UNWALLED_TYPES, place_openings, wall_segments


def svg_plan(result):
    """Render one plan option as a standalone SVG plan string."""
    plot = result.get("plot", {})
    road = str(plot.get("road", "south")).strip().lower()
    if road not in ("north", "south", "east", "west"):
        road = "south"
    plot_w = float(plot.get("w", 40))
    plot_d = float(plot.get("d", 60))
    rooms = result.get("placements", []) if result.get("ok") else []
    base = {"south": 0.0, "east": 90.0, "north": 180.0, "west": 270.0}[road]
    explicit_angle = "north_angle" in plot
    try:
        angle = float(plot.get("north_angle", base)) % 360.0
    except (TypeError, ValueError):
        angle = base
    residual = ((angle - base + 180.0) % 360.0) - 180.0

    # Drawing size: fit the plot in ~800 px, margins for dims + labels.
    # The road side gets extra room for its ROAD label.
    draw_w = plot_w if road in ("north", "south") else plot_d
    draw_d = plot_d if road in ("north", "south") else plot_w
    scale = 800.0 / max(draw_w, 1.0)
    left, top, right, bottom = 80, 78, 110, 104
    if road == "north":
        top = 104
    if road == "south":
        bottom = 122
    width = left + draw_w * scale + right
    height = top + draw_d * scale + bottom

    def point(x, y):
        """Local plot coords -> SVG coords (north-up, margins applied)."""
        if road == "south":
            u, v = x, plot_d - y
        elif road == "north":
            u, v = x, y
        elif road == "east":
            u, v = plot_d - y, plot_w - x
        else:  # west
            u, v = y, x
        return left + u * scale, top + v * scale

    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" '
        'style="width:100%%;height:auto;max-width:960px;background:#fff" '
        'font-family="sans-serif">' % (width, height))

    # Title block (text only, top-left).
    parts.append('<text x="%d" y="26" font-size="20" font-weight="bold">%s</text>'
                 % (left, escape("House Planner - concept floor plan")))
    if explicit_angle:
        subtitle = "Plot %s x %s, road %s, north %g deg. " % (
            format_ft_in(plot_w), format_ft_in(plot_d),
            road.capitalize(), angle)
    else:
        subtitle = "Plot %s x %s, road %s (north up). " % (
            format_ft_in(plot_w), format_ft_in(plot_d), road.capitalize())
    parts.append('<text x="%d" y="46" font-size="12">%s</text>'
                 % (left, escape(subtitle + "Concept only - not for "
                                 "construction.")))

    # Plot boundary (thick) + setback line (dashed).
    x0, y0 = point(0, 0)
    x1, y1 = point(plot_w, plot_d)
    parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                 'fill="none" stroke="#000" stroke-width="3"/>'
                 % (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))
    s0 = point(SETBACK_SIDE_FT, SETBACK_FRONT_FT)
    s1 = point(plot_w - SETBACK_SIDE_FT, plot_d - SETBACK_BACK_FT)
    parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                 'fill="none" stroke="#000" stroke-width="1.2" '
                 'stroke-dasharray="7 4"/>'
                 % (min(s0[0], s1[0]), min(s0[1], s1[1]),
                    abs(s1[0] - s0[0]), abs(s1[1] - s0[1])))
    parts.append('<text x="%.1f" y="%.1f" font-size="10">%s</text>'
                 % (min(s0[0], s1[0]) + 4, min(s0[1], s1[1]) + 14,
                    escape("setback line")))

    # Road edge (extra-thick black line) + ROAD label outside it.
    parts.append(_road_edge(point, plot_w, plot_d, road, scale))

    # Landscape: every plot cell outside a room rect reads green, so
    # leftover space (setbacks, front corners) is never a void.
    parts.append(_landscape(rooms, plot_w, plot_d, point))
    # Rooms: white fill, name + size + area (walled rooms lose their
    # outline; the solid wall bands drawn next replace it).
    for room in rooms:
        parts.append(_room_group(room, point, scale))
    glass = result.get("glass_partitions", [])
    placed = place_openings(rooms, result.get("open_plan", []), angle,
                            glass)
    for segment in wall_segments(rooms, placed["doors"],
                                 placed["windows"],
                                 result.get("open_plan", []), glass):
        if segment["kind"] == "glass":
            parts.append(_glass_symbol(segment, point, scale))
        else:
            parts.append(_wall_band(segment, point))
    by_name = {r.get("name", ""): r for r in rooms}
    for door in placed["doors"]:
        parts.append(_door_symbol(door, by_name, point, scale))
    for win in placed["windows"]:
        parts.append(_window_symbol(win, point, scale))
    if not rooms:
        cx = left + draw_w * scale / 2
        cy = top + draw_d * scale / 2
        parts.append('<text x="%.1f" y="%.1f" font-size="14" text-anchor="middle">'
                     '%s</text>' % (cx, cy, escape("No rooms placed - see notes.")))

    # Overall dimensions: frontage on its natural side, depth opposite
    # the road label so the two never collide. Rotated plans (road
    # east/west) map the road edge to a vertical line, so frontage
    # stands on the side and depth lies below; north/south plans keep
    # frontage below and depth on the left.
    if road == "south":
        width_edge = (point(0, 0), point(plot_w, 0))
        depth_edge = (point(0, 0), point(0, plot_d))
        width_side, depth_side = "below", "left"
    elif road == "north":
        width_edge = (point(0, plot_d), point(plot_w, plot_d))
        depth_edge = (point(0, 0), point(0, plot_d))
        width_side, depth_side = "below", "left"
    elif road == "east":
        width_edge = (point(0, plot_d), point(plot_w, plot_d))
        depth_edge = (point(0, 0), point(0, plot_d))
        width_side, depth_side = "left", "below"
    else:  # west
        width_edge = (point(0, plot_d), point(plot_w, plot_d))
        depth_edge = (point(plot_w, 0), point(plot_w, plot_d))
        width_side, depth_side = "right", "below"


    parts.append(_dimension(width_edge[0], width_edge[1], width_side,
                            format_ft_in(plot_w), scale))
    parts.append(_dimension(depth_edge[0], depth_edge[1], depth_side,

                            format_ft_in(plot_d), scale))

    # North arrow (top-right) + 10 ft scale bar (bottom-right). The arrow
    # shifts further right when the depth dimension also uses that side.
    arrow_x = left + draw_w * scale + (80 if road == "west" else 52)
    parts.append(_north_arrow(arrow_x, top + 34, residual))
    parts.append(_scale_bar(left + draw_w * scale - 10 * scale,
                            top + draw_d * scale + 62, scale))
    parts.append('<text x="%.1f" y="%.1f" font-size="10">%s</text>'
                 % (left, top + draw_d * scale + 62,
                    escape("Figured dimensions govern.")))
    parts.append("</svg>")
    return "\n".join(parts)


def svg_plot_preview(frontage_ft, depth_ft, north_angle=0.0):
    """Bare plot preview: to-scale rectangle, road band, dims, north arrow.

    Local frame (road at the bottom); the arrow turns with the real
    north angle (0 = north away from the road, clockwise).
    """
    plot_w = max(float(frontage_ft), 1.0)
    plot_d = max(float(depth_ft), 1.0)
    try:
        angle = float(north_angle) % 360.0
    except (TypeError, ValueError):
        angle = 0.0
    scale = min(380.0 / plot_w, 330.0 / plot_d)
    left, top = 95, 40
    width = left + plot_w * scale + 110
    height = top + plot_d * scale + 92

    def pt(x, y):
        """Local plot coords -> SVG coords (road edge at the bottom)."""
        return left + x * scale, top + (plot_d - y) * scale

    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" '
        'style="width:100%%;height:auto;max-width:520px;background:#fff" '
        'font-family="sans-serif">' % (width, height))
    parts.append('<text x="%d" y="22" font-size="14" font-weight="bold">%s'
                 "</text>" % (left, escape("Plot preview (to scale)")))
    x0, y0 = pt(0, 0)
    x1, y1 = pt(plot_w, plot_d)
    parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                 'fill="none" stroke="#000" stroke-width="3"/>'
                 % (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))
    band_top = top + plot_d * scale
    parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="30" '
                 'fill="#eee" stroke="#000" stroke-width="1.2"/>'
                 % (left, band_top, plot_w * scale))
    parts.append('<text x="%.1f" y="%.1f" font-size="13" font-weight="bold" '
                 'text-anchor="middle">ROAD</text>'
                 % (left + plot_w * scale / 2, band_top + 21))
    parts.append(_dimension(pt(0, 0), pt(plot_w, 0), "below",
                            "%s frontage" % format_ft_in(plot_w), scale))
    parts.append(_dimension(pt(0, 0), pt(0, plot_d), "left",
                            "%s deep" % format_ft_in(plot_d), scale))
    arrow_x = left + plot_w * scale + 52
    parts.append(_north_arrow(arrow_x, top + 30, angle))
    parts.append('<text x="%.1f" y="%.1f" font-size="10" text-anchor="middle">'
                 "%s</text>" % (arrow_x, top + 62,
                                escape("north %g deg" % angle)))
    parts.append("</svg>")
    return "\n".join(parts)


def _room_group(room, point, scale):
    """One room: rectangle + centered label lines (name, size, area)."""
    ax, ay = point(room["x"], room["y"])
    bx, by = point(room["x"] + room["w"], room["y"] + room["d"])
    x, y = min(ax, bx), min(ay, by)
    width, height = abs(bx - ax), abs(by - ay)
    name = str(room.get("name", "?"))
    short = SHORT_NAMES.get(str(room.get("type", "")), name.split(" ")[0])
    label = name if len(name) * 6.2 < width - 8 else short
    dims = "%s x %s" % (format_ft_in(room["w"]), format_ft_in(room["d"]))
    try:
        area = "%d sq ft" % round(float(room["w"]) * float(room["d"]))
    except (TypeError, ValueError):
        area = ""
    cx = x + width / 2
    dash = ' stroke-dasharray="7 4"' if room.get("type") == "garden" else ""
    fill = "#d5e5cf" if str(room.get("type", "")) == "garden" else "#fff"
    if str(room.get("type", "")) in UNWALLED_TYPES:
        box = ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
               'fill="%s" stroke="#000" stroke-width="1.6"%s/>'
               % (x, y, width, height, fill, dash))
    else:  # solid wall bands outline walled rooms; no stroke here
        box = ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
               'fill="#fff" stroke="none"/>'
               % (x, y, width, height))
    out = ['<g>' + box]
    if height < 24:
        out.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle">%s'
                   "</text>" % (cx, y + height / 2 + 3, escape(label)))
    elif height < 44:
        out.append('<text x="%.1f" y="%.1f" font-size="10" font-weight="bold" '
                   'text-anchor="middle">%s</text>' % (cx, y + 15, escape(label)))
        out.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle">%s'
                   "</text>" % (cx, y + 28, escape(dims)))
    else:
        if str(room.get("type", "")) in ("porch", "veranda"):
            size = 10
        else:
            size = 12 if len(label) * 6.6 < width - 8 else 10
        out.append('<text x="%.1f" y="%.1f" font-size="%d" font-weight="bold" '
                   'text-anchor="middle">%s</text>'
                   % (cx, y + height / 2 - 8, size, escape(label)))
        out.append('<text x="%.1f" y="%.1f" font-size="10" text-anchor="middle">%s'
                   "</text>" % (cx, y + height / 2 + 8, escape(dims)))
        if area:
            out.append('<text x="%.1f" y="%.1f" font-size="10" '
                       'text-anchor="middle">%s</text>'
                       % (cx, y + height / 2 + 23, escape(area)))
    out.append("</g>")
    return "".join(out)


def _wall_band(segment, point):
    """One solid wall band: filled black rect between mapped corners."""
    ax, ay = point(segment["x0"], segment["y0"])
    bx, by = point(segment["x1"], segment["y1"])
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
            'fill="#000" stroke="none"/>'
            % (min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay)))


def _landscape(rooms, plot_w, plot_d, point):

    """Light-green fill over plot cells no room covers (never a void).

    Cells are drawn 1 unit oversized so neighbours overlap: abutting
    rects leave faint hairline seams on rotated plans otherwise."""
    xs = sorted({0.0, plot_w} | {r["x"] for r in rooms}
                | {r["x"] + r["w"] for r in rooms})
    ys = sorted({0.0, plot_d} | {r["y"] for r in rooms}
                | {r["y"] + r["d"] for r in rooms})
    xs = [v for v in xs if 0.0 <= v <= plot_w]
    ys = [v for v in ys if 0.0 <= v <= plot_d]
    out = []
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            if x1 - x0 < 0.01 or y1 - y0 < 0.01:
                continue
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            covered = any(r["x"] - 0.01 <= cx <= r["x"] + r["w"] + 0.01
                          and r["y"] - 0.01 <= cy <= r["y"] + r["d"] + 0.01
                          for r in rooms)
            if covered:
                continue
            ax, ay = point(x0, y0)
            bx, by = point(x1, y1)
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                       'fill="#d5e5cf" stroke="none"/>'
                       % (min(ax, bx) - 0.5, min(ay, by) - 0.5,
                          abs(bx - ax) + 1.0, abs(by - ay) + 1.0))
    return "".join(out)


def _door_symbol(door, by_name, point, scale):
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
    radius = float(door["width"]) * scale
    lx, ly = hx + nx * radius, hy + ny * radius  # leaf end
    start = math.degrees(math.atan2(ly - hy, lx - hx))
    end = math.degrees(math.atan2(ey - hy, ex - hx))
    delta = (end - start) % 360.0
    if delta > 180.0:
        delta -= 360.0
    sweep = 1 if delta > 0 else 0
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
            'stroke-width="1.4"/>'
            '<path d="M %.1f %.1f A %.1f %.1f 0 0 %d %.1f %.1f" '
            'fill="none" stroke="#000" stroke-width="1"/>'
            % (hx, hy, lx, ly, lx, ly, radius, radius, sweep, ex, ey))


def _window_symbol(win, point, scale):
    """Window: two thin lines across the wall gap, 3 in apart."""
    ax, ay = point(win["x0"], win["y0"])
    bx, by = point(win["x1"], win["y1"])
    dx, dy = bx - ax, by - ay
    gap = math.hypot(dx, dy)
    if gap < 0.01:
        return ""
    off = 0.125 * scale  # 1.5 in each side of the wall centerline
    nx, ny = -dy / gap * off, dx / gap * off
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
            'stroke-width="1"/>'
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
            'stroke-width="1"/>'
            % (ax + nx, ay + ny, bx + nx, by + ny,
               ax - nx, ay - ny, bx - nx, by - ny))


def _glass_symbol(segment, point, scale):
    """Glass partition: thin double lines along the run (slider noted)."""
    return _window_symbol({"x0": segment["x0"], "y0": segment["y0"],
                           "x1": segment["x1"], "y1": segment["y1"]},
                          point, scale)


def _road_edge(point, plot_w, plot_d, road, scale):
    """Thick road line + ROAD label on the real road side.

    The road is always the local y=0 edge; the north-up transform moves it
    to the correct side. The label sits just outside that edge.
    """
    ends = (point(0, 0), point(plot_w, 0))
    mid_x = (ends[0][0] + ends[1][0]) / 2
    mid_y = (ends[0][1] + ends[1][1]) / 2
    if road == "south":
        lx, ly = mid_x, mid_y + 64
    elif road == "north":
        lx, ly = mid_x, mid_y - 30
    elif road == "east":
        lx, ly = mid_x + 40, mid_y
    else:
        lx, ly = mid_x - 40, mid_y
    _ = scale
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
            'stroke-width="6"/>'
            '<text x="%.1f" y="%.1f" font-size="13" font-weight="bold" '
            'text-anchor="middle">ROAD</text>' % (ends[0][0], ends[0][1],
                                                 ends[1][0], ends[1][1], lx, ly))


def _dimension(point_a, point_b, side, label, scale):
    """One overall dimension: extension lines + ticked line + label."""
    (ax, ay), (bx, by) = point_a, point_b
    _ = scale
    if side == "below":
        line_y = max(ay, by) + 44
        out = ['<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (ax, max(ay, by) + 6, ax, line_y + 4),
               '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (bx, max(ay, by) + 6, bx, line_y + 4),
               '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (ax, line_y, bx, line_y),
               _tick(ax, line_y), _tick(bx, line_y),
               '<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle">%s'
               "</text>" % ((ax + bx) / 2, line_y - 6, escape(label))]
    elif side == "left":
        line_x = min(ax, bx) - 40
        out = ['<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (min(ax, bx) - 6, ay, line_x - 4, ay),
               '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (min(ax, bx) - 6, by, line_x - 4, by),
               '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (line_x, ay, line_x, by),
               _tick(line_x, ay), _tick(line_x, by),
               '<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle" '
               'transform="rotate(-90 %.1f %.1f)">%s</text>'
               % (line_x - 8, (ay + by) / 2, line_x - 8, (ay + by) / 2,
                  escape(label))]
    else:  # "right": mirror of left, used when the road labels the left.
        line_x = max(ax, bx) + 40
        out = ['<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (max(ax, bx) + 6, ay, line_x + 4, ay),
               '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (max(ax, bx) + 6, by, line_x + 4, by),
               '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="1"/>' % (line_x, ay, line_x, by),
               _tick(line_x, ay), _tick(line_x, by),
               '<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle" '
               'transform="rotate(-90 %.1f %.1f)">%s</text>'
               % (line_x + 10, (ay + by) / 2, line_x + 10, (ay + by) / 2,
                  escape(label))]
    return "".join(out)


def _tick(x, y):
    """Small 45-degree architectural tick across a dimension line."""
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
            'stroke-width="1.4"/>' % (x - 4, y + 4, x + 4, y - 4))


def _north_arrow(x, y, angle=0.0):
    """Circle + needle + N, needle rotated clockwise by angle degrees."""
    spin = "" if abs(angle) < 0.001 else \
        ' transform="rotate(%g %.1f %.1f)"' % (angle, x, y)
    radians = math.radians(angle)
    nx = x - 14 * math.sin(radians)
    ny = y + 14 * math.cos(radians)
    return ('<g><circle cx="%.1f" cy="%.1f" r="17" fill="none" stroke="#000" '
            'stroke-width="1.4"/>'
            '<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="#000"%s/>'
            '<text x="%.1f" y="%.1f" font-size="11" font-weight="bold" '
            'text-anchor="middle">N</text></g>'
            % (x, y, x, y - 13, x - 5.5, y + 2, x + 5.5, y + 2, spin,
               nx, ny))


def _scale_bar(x, y, scale):
    """Honest 10 ft scale bar (two 5 ft blocks) drawn from the true scale."""
    five = 5 * scale
    return ('<g><rect x="%.1f" y="%.1f" width="%.1f" height="6" fill="#000"/>'
            '<rect x="%.1f" y="%.1f" width="%.1f" height="6" fill="none" '
            'stroke="#000" stroke-width="1"/>'
            '<text x="%.1f" y="%.1f" font-size="10">0</text>'
            '<text x="%.1f" y="%.1f" font-size="10" text-anchor="middle">5</text>'
            '<text x="%.1f" y="%.1f" font-size="10" text-anchor="end">10 ft</text>'
            "</g>" % (x, y, five, x + five, y, five, x, y + 20, x + five, y + 20,
                      x + 2 * five, y + 20))
