# draw.py
# Step 2 of House Planner: layout -> SVG plan drawing (plain Python, no CAD lib).
#
# What this file does: turns placed room rectangles into a clean, dimensioned
# 2D plan in SVG format: plot boundary, dashed setback line, rooms with names,
# sizes (feet-inches) and areas, overall dimensions, north arrow, road label,
# scale bar, and a concept-only note. Black lines on white, no bright colors.
#
# Orientation: the drawing is always NORTH-UP (standard architectural
# convention). The local layout frame (x parallel to road, y from the road
# inward) is rotated so the road lands on its real side:
#   road South -> road edge at the bottom, rooms upright;
#   road North -> road edge at the top;
#   road East  -> road edge on the right, plan rotated;
#   road West  -> road edge on the left, plan rotated.
# The road side is a compass direction, so it already implies where north is
# (no separate north input needed); the arrow always points up.

from xml.sax.saxutils import escape

from ai_program import (
    SETBACK_BACK_FT,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    format_ft_in,
)
from layout import SHORT_NAMES


def svg_plan(result):
    """Render one plan option as a standalone SVG plan string."""
    plot = result.get("plot", {})
    road = str(plot.get("road", "south")).strip().lower()
    if road not in ("north", "south", "east", "west"):
        road = "south"
    plot_w = float(plot.get("w", 40))
    plot_d = float(plot.get("d", 60))
    rooms = result.get("placements", []) if result.get("ok") else []

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
    parts.append('<text x="%d" y="46" font-size="12">%s</text>'
                 % (left, escape("Plot %s x %s, road %s (north up). "
                                 "Concept only - not for construction."
                                 % (format_ft_in(plot_w), format_ft_in(plot_d),
                                    road.capitalize()))))

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

    # Rooms: white fill, black outline, name + size + area.
    for room in rooms:
        parts.append(_room_group(room, point, scale))
    if not rooms:
        cx = left + draw_w * scale / 2
        cy = top + draw_d * scale / 2
        parts.append('<text x="%.1f" y="%.1f" font-size="14" text-anchor="middle">'
                     '%s</text>' % (cx, cy, escape("No rooms placed - see notes.")))

    # Overall dimensions (plot width at bottom; depth on the side
    # opposite the road label so the two never collide).
    parts.append(_dimension(point(0, 0), point(plot_w, 0), "below",
                            format_ft_in(plot_w), scale))
    parts.append(_dimension(point(0, 0), point(0, plot_d),
                            "right" if road == "west" else "left",
                            format_ft_in(plot_d), scale))

    # North arrow (top-right) + 10 ft scale bar (bottom-right). The arrow
    # shifts further right when the depth dimension also uses that side.
    arrow_x = left + draw_w * scale + (80 if road == "west" else 52)
    parts.append(_north_arrow(arrow_x, top + 34))
    parts.append(_scale_bar(left + draw_w * scale - 10 * scale,
                            top + draw_d * scale + 62, scale))
    parts.append('<text x="%.1f" y="%.1f" font-size="10">%s</text>'
                 % (left, top + draw_d * scale + 62,
                    escape("Figured dimensions govern.")))
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
    out = ['<g><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
           'fill="#fff" stroke="#000" stroke-width="1.6"/>' % (x, y, width, height)]
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


def _north_arrow(x, y):
    """Circle + up triangle + N (the drawing is always north-up)."""
    return ('<g><circle cx="%.1f" cy="%.1f" r="17" fill="none" stroke="#000" '
            'stroke-width="1.4"/>'
            '<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="#000"/>'
            '<text x="%.1f" y="%.1f" font-size="11" font-weight="bold" '
            'text-anchor="middle">N</text></g>'
            % (x, y, x, y - 13, x - 5.5, y + 2, x + 5.5, y + 2, x, y + 14))


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
