# exp_render_plan.py
# RENDER EXPERIMENT (not wired into the app): rendered floor plans.
#
# What this script does (T1 options A/B/C only):
#   1. Exports each option as a PNG plan (walls, doors, windows,
#      verandas/porch outlines, plot boundary; no text, no dims) using
#      the SAME scale/margins/transform as draw.svg_plan. Round 2
#      also draws simple furniture outlines per room type (beds,
#      kitchen counter, toilet fixtures, sofas, dining set) so the
#      AI furnishes the right rooms, kept clear of door swings.
#   2. Sends it to Muse Image EDIT mode (POST /v1/images/edits,
#      model muse-image-1.0) asking for a flat orthographic colored
#      top-down render that keeps every wall and furniture piece
#      where it is.
#   3. Overlays room-name labels only (round 1 overlaid walls too,
#      which doubled the AI's 3D walls).
#   4. Saves input/raw/overlaid PNGs to review/renders/ for review.
#
# Docs: dev.meta.ai/docs/image-generation ("Edit an image"):
# client.images.edit(model, prompt, image, size, n) - OpenAI-compatible.
# Pillow is pure pip (no system package), so this path also works on
# Streamlit Cloud. Cost: 3 image calls per round for T1 A/B/C.
#
# Run: .venv\Scripts\python.exe exp_render_plan.py
#      .venv\Scripts\python.exe exp_render_plan.py export-only
# (export-only redraws the input PNGs without calling the API).

import base64
import io
import math
import os

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from ai_program import BASE_URL
from draw import svg_plan  # noqa: F401 (kept: same geometry source)
from layout import SHORT_NAMES
from openings import UNWALLED_TYPES, place_openings, wall_segments
from test_layout import PROGRAM_3BED
from typology import build_options

CANVAS = (1024, 1536)  # portrait; matches T1's plan aspect
IMAGE_MODEL = "muse-image-1.0"

RENDER_PROMPT = (
    "Strictly flat orthographic top-down floor plan view, no "
    "perspective, no wall height, no 3D cutaway. Render the "
    "furniture shown in the input realistically in the same "
    "positions; do not add or move furniture. Warm wood floors in "
    "bedrooms and living spaces, light tiles in kitchen and "
    "toilets. Lawn and plants in all open areas, minimal paving "
    "(only a short path to the porch). Soft light shadows. "
    "No text."
)


def _read_key():
    """META_API_KEY from the environment or the local .env file."""
    key = (os.environ.get("META_API_KEY") or "").strip()
    if key:
        return key
    try:
        with open(".env", "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("META_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def _frame(plot_w, plot_d, road):
    """Same scale/margins/transform as draw.svg_plan (T1: road North)."""
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
    ox = (CANVAS[0] - width) / 2.0
    oy = (CANVAS[1] - height) / 2.0

    def point(x, y):
        if road == "south":
            u, v = x, plot_d - y
        elif road == "north":
            u, v = x, y
        elif road == "east":
            u, v = plot_d - y, plot_w - x
        else:  # west
            u, v = y, x
        return ox + left + u * scale, oy + top + v * scale

    return point, scale


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: bitmap font, fixed size
        return ImageFont.load_default()


def _room_label(room, width_px):
    name = str(room.get("name", "?"))
    short = SHORT_NAMES.get(str(room.get("type", "")),
                            name.split(" ")[0])
    label = name if len(name) * 6.2 < width_px - 8 else short
    if room.get("screened_jali"):
        label = "Ver (jali)"
    return label


FURN = "#3f3f3f"  # furniture gray: reads apart from black walls


def _norm(box):
    """(x0, y0, x1, y1) with ordered corners."""
    x0, y0, x1, y1 = box
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _hits(box_a, box_b, pad=0.0):
    """True when two boxes overlap (pad grows both)."""
    ax0, ay0, ax1, ay1 = _norm(box_a)
    bx0, by0, bx1, by1 = _norm(box_b)
    return (ax0 < bx1 + pad and ax1 + pad > bx0
            and ay0 < by1 + pad and ay1 + pad > by0)


def _keepouts(rooms, doors):
    """Per-room keep-out boxes in plan feet: door swings (full door
    width into the swing room) plus a 2.5 ft approach box on every
    room the doorway opens from."""
    boxes = {}
    for door in doors:
        try:
            width = float(door.get("width", 3.0))
        except (TypeError, ValueError):
            width = 3.0
        gx0 = float(door["x0"])
        gy0 = float(door["y0"])
        gx1 = float(door["x1"])
        gy1 = float(door["y1"])
        mx, my = (gx0 + gx1) / 2.0, (gy0 + gy1) / 2.0
        horiz = abs(gx1 - gx0) >= abs(gy1 - gy0)
        swing = str(door.get("swing", ""))
        for room in rooms:
            name = room.get("name", "")
            rx, ry = float(room["x"]), float(room["y"])
            rw, rd = float(room["w"]), float(room["d"])
            inside = (rx - 0.7 <= mx <= rx + rw + 0.7
                      and ry - 0.7 <= my <= ry + rd + 0.7)
            on_edge = (abs(mx - rx) < 0.7
                       or abs(mx - (rx + rw)) < 0.7
                       or abs(my - ry) < 0.7
                       or abs(my - (ry + rd)) < 0.7)
            if not (inside and on_edge):
                continue
            depth = width if name == swing else 2.5
            cx, cy = rx + rw / 2.0, ry + rd / 2.0
            if horiz:
                step = 1.0 if cy >= my else -1.0
                box = (min(gx0, gx1), my, max(gx0, gx1),
                       my + step * depth)
            else:
                step = 1.0 if cx >= mx else -1.0
                box = (mx, min(gy0, gy1), mx + step * depth,
                       max(gy0, gy1))
            boxes.setdefault(name, []).append(_norm(box))
    return boxes


def _free_spans(lo, hi, blocked, pad=0.35):
    """Complement of blocked 1D intervals inside [lo, hi]. Blocked
    ends grow by pad, so a returned span places as-is (the fits()
    check pads again, which used to reject edge-exact spans)."""
    cuts = sorted((min(b0, b1) - pad, max(b0, b1) + pad)
                  for b0, b1 in blocked)
    spans, at = [], lo
    for b0, b1 in cuts:
        if b0 > at:
            spans.append((at, min(b0, hi)))
        at = max(at, b1)
    if at < hi:
        spans.append((at, hi))
    return [(a, b) for a, b in spans if b - a > 0.05]


class _Placer:
    """Try furniture candidates inside one room rect; keep the
    ones fully inside that clear every keep-out and each other."""

    def __init__(self, room, keep):
        self.rx = float(room["x"])
        self.ry = float(room["y"])
        self.rw = float(room["w"])
        self.rd = float(room["d"])
        self.keep = list(keep)
        self.taken = []
        self.shapes = []

    def fits(self, x, y, w, d):
        if x < self.rx + 0.25 or y < self.ry + 0.25 \
                or x + w > self.rx + self.rw - 0.25 \
                or y + d > self.ry + self.rd - 0.25:
            return False
        cand = (x, y, x + w, y + d)
        for other in self.keep + self.taken:
            if _hits(cand, other, pad=0.3):
                return False
        return True

    def add(self, x, y, w, d, extras=()):
        """Place a rect + optional extra shapes; return it or None."""
        if not self.fits(x, y, w, d):
            return None
        self.taken.append((x, y, x + w, y + d))
        self.shapes.append(("rect", x, y, w, d))
        self.shapes.extend(extras)
        return (x, y, w, d)

    def first(self, cands, w, d, extras_fn=None):
        for x, y in cands:
            if self.fits(x, y, w, d):
                extras = extras_fn(x, y, w, d) if extras_fn else ()
                return self.add(x, y, w, d, extras)
        return None

    def wall_strip_blocked(self, wall, depth):
        """Blocked 1D intervals along one wall's strip (feet)."""
        rx, ry, rw, rd = self.rx, self.ry, self.rw, self.rd
        if wall == "top":
            strip = (rx, ry, rx + rw, ry + depth)
            proj = lambda b: (b[0], b[2])
            lo, hi = rx + 0.3, rx + rw - 0.3
        elif wall == "bottom":
            strip = (rx, ry + rd - depth, rx + rw, ry + rd)
            proj = lambda b: (b[0], b[2])
            lo, hi = rx + 0.3, rx + rw - 0.3
        elif wall == "left":
            strip = (rx, ry, rx + depth, ry + rd)
            proj = lambda b: (b[1], b[3])
            lo, hi = ry + 0.3, ry + rd - 0.3
        else:  # right
            strip = (rx + rw - depth, ry, rx + rw, ry + rd)
            proj = lambda b: (b[1], b[3])
            lo, hi = ry + 0.3, ry + rd - 0.3
        blocked = [proj(b) for b in self.keep + self.taken
                   if _hits(strip, b, pad=0.3)]
        return lo, hi, blocked


def _bed_extras(head):
    def fn(x, y, w, d):
        if head == "top":
            return [("line", x, y + 1.5, x + w, y + 1.5)]
        if head == "bottom":
            return [("line", x, y + d - 1.5, x + w, y + d - 1.5)]
        if head == "left":
            return [("line", x + 1.5, y, x + 1.5, y + d)]
        return [("line", x + w - 1.5, y, x + w - 1.5, y + d)]
    return fn


def _bedroom(plc):
    short = min(plc.rw, plc.rd)
    bed_w = 5.0 if short >= 10.5 else (4.0 if short >= 9.5 else 3.0)
    bed_l = 6.5 if max(plc.rw, plc.rd) >= 11.0 else 6.0
    rx, ry, rw, rd = plc.rx, plc.ry, plc.rw, plc.rd
    walls = [("top", bed_w, bed_l), ("bottom", bed_w, bed_l),
             ("left", bed_l, bed_w), ("right", bed_l, bed_w)]
    walls.sort(key=lambda item: -(rw if item[0] in ("top", "bottom")
                                  else rd))
    for wall, w, d in walls:
        if wall == "top":
            cands = [(rx + rw / 2 - w / 2, ry + 0.3),
                     (rx + 0.4, ry + 0.3),
                     (rx + rw - w - 0.4, ry + 0.3)]
        elif wall == "bottom":
            cands = [(rx + rw / 2 - w / 2, ry + rd - d - 0.3),
                     (rx + 0.4, ry + rd - d - 0.3),
                     (rx + rw - w - 0.4, ry + rd - d - 0.3)]
        elif wall == "left":
            cands = [(rx + 0.3, ry + rd / 2 - d / 2),
                     (rx + 0.3, ry + 0.4),
                     (rx + 0.3, ry + rd - d - 0.4)]
        else:
            cands = [(rx + rw - w - 0.3, ry + rd / 2 - d / 2),
                     (rx + rw - w - 0.3, ry + 0.4),
                     (rx + rw - w - 0.3, ry + rd - d - 0.4)]
        bed = plc.first(cands, w, d, _bed_extras(wall))
        if bed is None:
            continue
        bx, by = bed[0], bed[1]
        if wall in ("top", "bottom"):
            hy = ry + 0.3 if wall == "top" else ry + rd - 1.8
            plc.first([(bx - 1.8, hy), (bx + w + 0.3, hy)],
                      1.5, 1.5)
            plc.first([(bx + w + 0.3, hy), (bx - 1.8, hy)],
                      1.5, 1.5)
        else:
            hx = rx + 0.3 if wall == "left" else rx + rw - 1.8
            plc.first([(hx, by - 1.8), (hx, by + d + 0.3)],
                      1.5, 1.5)
            plc.first([(hx, by + d + 0.3), (hx, by - 1.8)],
                      1.5, 1.5)
        break
    ward_w = 4.0 if rw >= 12 or rd >= 12 else 3.0
    plc.first([(rx + 0.4, ry + rd - 2.3),
               (rx + rw - ward_w - 0.4, ry + 0.4),
               (rx + 0.4, ry + 0.4)], ward_w, 2.0)


def _counter_wall(plc, depth=2.0):
    """Wall whose strip has the longest keep-out-free span."""
    best, best_len = "top", -1.0
    for wall in ("top", "bottom", "left", "right"):
        lo, hi, blocked = plc.wall_strip_blocked(wall, depth)
        for a, b in _free_spans(lo, hi, blocked):
            if b - a > best_len:
                best, best_len = wall, b - a
    return best


def _kitchen(plc):
    wall = _counter_wall(plc)
    lo, hi, blocked = plc.wall_strip_blocked(wall, 2.0)
    rx, ry, rw, rd = plc.rx, plc.ry, plc.rw, plc.rd
    longest = None
    for a, b in _free_spans(lo, hi, blocked):
        if b - a < 3.0:
            continue
        if wall == "top":
            seg = plc.add(a, ry + 0.3, b - a, 2.0)
        elif wall == "bottom":
            seg = plc.add(a, ry + rd - 2.3, b - a, 2.0)
        elif wall == "left":
            seg = plc.add(rx + 0.3, a, 2.0, b - a)
        else:
            seg = plc.add(rx + rw - 2.3, a, 2.0, b - a)
        if seg and (longest is None or b - a > longest[2]):
            longest = (seg, b - a, b - a)
    if longest is None:
        return
    (sx, sy, sw, sd), _span, _ = longest
    if wall in ("top", "bottom"):
        plc.shapes.append(("rect", sx + 0.2, sy + 0.2, 1.8, 1.6))
        plc.shapes.append(("rect", sx + sw - 2.0, sy + 0.2, 1.8,
                           1.6))
    else:
        plc.shapes.append(("rect", sx + 0.2, sy + 0.2, 1.6, 1.8))
        plc.shapes.append(("rect", sx + 0.2, sy + sd - 2.0, 1.6,
                           1.8))


def _bathroom(plc):
    rx, ry, rw, rd = plc.rx, plc.ry, plc.rw, plc.rd
    corners = [(rx + 0.3, ry + 0.3),
               (rx + rw - 2.5, ry + 0.3),
               (rx + 0.3, ry + rd - 2.7),
               (rx + rw - 2.5, ry + rd - 2.7)]
    corners.sort(key=lambda c: -min(
        [abs(c[0] + 1.1 - (b[0] + b[2]) / 2.0)
         + abs(c[1] + 1.2 - (b[1] + b[3]) / 2.0)
         for b in plc.keep] or [0]))
    wc = plc.first(corners, 2.2, 2.4)
    if wc is not None:
        wx, wy = wc[0], wc[1]
        plc.first([(wx + 2.5, wy), (wx - 2.1, wy),
                   (wx, wy + 2.7), (wx, wy - 1.9)], 1.8, 1.6)
    if min(rw, rd) >= 6.0:
        plc.first([(rx + rw - 3.3, ry + rd - 3.3),
                   (rx + 0.3, ry + 0.3),
                   (rx + rw - 3.3, ry + 0.3),
                   (rx + 0.3, ry + rd - 3.3)], 3.0, 3.0)


def _seating(plc, sofa_w, table_w):
    """Sofa along the clearest wall + coffee table + 2 chairs."""
    wall = _counter_wall(plc, depth=3.0)
    rx, ry, rw, rd = plc.rx, plc.ry, plc.rw, plc.rd
    if wall == "top":
        cands = [(rx + rw / 2 - sofa_w / 2, ry + 0.3),
                 (rx + 0.4, ry + 0.3),
                 (rx + rw - sofa_w - 0.4, ry + 0.3)]
        sofa = plc.first(cands, sofa_w, 3.0)
        spots = [(rx + rw / 2 - table_w / 2, ry + rd / 2 - 1.0),
                 (rx + rw / 2 - table_w / 2, ry + 4.2)]
    elif wall == "bottom":
        cands = [(rx + rw / 2 - sofa_w / 2, ry + rd - 3.3),
                 (rx + 0.4, ry + rd - 3.3),
                 (rx + rw - sofa_w - 0.4, ry + rd - 3.3)]
        sofa = plc.first(cands, sofa_w, 3.0)
        spots = [(rx + rw / 2 - table_w / 2, ry + rd / 2 - 1.0),
                 (rx + rw / 2 - table_w / 2, ry + rd - 6.2)]
    elif wall == "left":
        cands = [(rx + 0.3, ry + rd / 2 - sofa_w / 2),
                 (rx + 0.3, ry + 0.4),
                 (rx + 0.3, ry + rd - sofa_w - 0.4)]
        sofa = plc.first(cands, 3.0, sofa_w)
        spots = [(rx + rw / 2 - 1.0, ry + rd / 2 - table_w / 2),
                 (rx + 4.2, ry + rd / 2 - table_w / 2)]
    else:
        cands = [(rx + rw - 3.3, ry + rd / 2 - sofa_w / 2),
                 (rx + rw - 3.3, ry + 0.4),
                 (rx + rw - 3.3, ry + rd - sofa_w - 0.4)]
        sofa = plc.first(cands, 3.0, sofa_w)
        spots = [(rx + rw / 2 - 1.0, ry + rd / 2 - table_w / 2),
                 (rx + rw - 6.2, ry + rd / 2 - table_w / 2)]
    if sofa is None:
        return
    if wall in ("top", "bottom"):
        table = plc.first(spots, table_w, 2.0)
        if table is not None:
            tx, ty = table[0], table[1]
            plc.first([(tx - 2.3, ty), (tx + table_w + 0.3, ty)],
                      2.0, 2.0)
            plc.first([(tx + table_w + 0.3, ty), (tx - 2.3, ty)],
                      2.0, 2.0)
    else:
        table = plc.first(spots, 2.0, table_w)
        if table is not None:
            tx, ty = table[0], table[1]
            plc.first([(tx, ty - 2.3), (tx, ty + table_w + 0.3)],
                      2.0, 2.0)
            plc.first([(tx, ty + table_w + 0.3), (tx, ty - 2.3)],
                      2.0, 2.0)


def _dining(plc):
    rx, ry, rw, rd = plc.rx, plc.ry, plc.rw, plc.rd
    if min(rw, rd) >= 10.0:
        tw, td = 5.0, 3.2
    elif min(rw, rd) >= 8.5:
        tw, td = 4.5, 3.0
    else:
        tw, td = 4.0, 2.8
    table = plc.first([(rx + rw / 2 - tw / 2, ry + rd / 2 - td / 2),
                       (rx + rw / 2 - tw / 2, ry + 2.6),
                       (rx + rw / 2 - tw / 2, ry + rd - td - 2.6)],
                      tw, td)
    if table is None:
        return
    tx, ty = table[0], table[1]
    plc.first([(tx + 0.3, ty - 2.1), (tx + tw - 2.1, ty - 2.1)],
              1.8, 1.8)
    plc.first([(tx + tw - 2.1, ty - 2.1), (tx + 0.3, ty - 2.1)],
              1.8, 1.8)
    plc.first([(tx + 0.3, ty + td + 0.3),
               (tx + tw - 2.1, ty + td + 0.3)], 1.8, 1.8)
    plc.first([(tx + tw - 2.1, ty + td + 0.3),
               (tx + 0.3, ty + td + 0.3)], 1.8, 1.8)


def _veranda(plc):
    rx, ry, rw, rd = plc.rx, plc.ry, plc.rw, plc.rd
    chair = plc.first([(rx + 0.4, ry + 0.4),
                       (rx + rw - 2.1, ry + rd - 2.1),
                       (rx + rw - 2.1, ry + 0.4),
                       (rx + 0.4, ry + rd - 2.1)], 1.7, 1.7)
    spots = [(rx + rw - 1.9, ry + rd - 1.9),
             (rx + 0.4, ry + 0.4),
             (rx + 0.4, ry + rd - 1.9),
             (rx + rw - 1.9, ry + 0.4)]
    for sx, sy in spots:
        if plc.fits(sx, sy, 1.5, 1.5):
            plc.taken.append((sx, sy, sx + 1.5, sy + 1.5))
            plc.shapes.append(("circle", sx + 0.75, sy + 0.75,
                               0.75))
            break
    if chair is not None and max(rw, rd) >= 9.0:
        plc.first([(rx + rw - 2.1, ry + 0.4),
                   (rx + 0.4, ry + rd - 2.1)], 1.7, 1.7)


def _furniture_shapes(room, keep):
    """Simple line-drawing furniture per room type (plan feet)."""
    kind = str(room.get("type", "")).strip().lower()
    plc = _Placer(room, keep)
    if kind == "bedroom":
        _bedroom(plc)
    elif kind == "kitchen":
        _kitchen(plc)
    elif kind in ("bathroom", "toilet", "bath"):
        _bathroom(plc)
    elif kind == "living room":
        _seating(plc, 6.5, 3.5)
    elif kind == "dining":
        _dining(plc)
    elif kind == "family living":
        _seating(plc, 6.0, 3.0)
    elif kind in ("veranda", "porch"):
        _veranda(plc)
    return plc.shapes


def _draw_shape(ink, shape, point):
    """One furniture shape (gray outline) onto the plan."""
    if shape[0] == "circle":
        _, cx, cy, rad = shape
        ax, ay = point(cx - rad, cy - rad)
        bx, by = point(cx + rad, cy + rad)
        ink.ellipse([min(ax, bx), min(ay, by), max(ax, bx),
                     max(ay, by)], outline=FURN, width=2)
        return
    if shape[0] == "line":
        _, x0, y0, x1, y1 = shape
        ax, ay = point(x0, y0)
        bx, by = point(x1, y1)
        ink.line([ax, ay, bx, by], fill=FURN, width=2)
        return
    _, x, y, w, d = shape
    ax, ay = point(x, y)
    bx, by = point(x + w, y + d)
    ink.rectangle([min(ax, bx), min(ay, by), max(ax, bx),
                   max(ay, by)], outline=FURN, width=2)


def draw_plan_png(rooms, open_plan, glass, angle, plot_w, plot_d,
                  road):
    """Clean line-plan PNG: walls/doors/windows/verandas/plot, no text."""
    img = Image.new("RGB", CANVAS, "#ffffff")
    ink = ImageDraw.Draw(img)
    point, scale = _frame(plot_w, plot_d, road)

    # Plot boundary (thick).
    x0, y0 = point(0, 0)
    x1, y1 = point(plot_w, plot_d)
    ink.rectangle([min(x0, x1), min(y0, y1), max(x0, x1),
                   max(y0, y1)], outline="#000000", width=3)

    # Unwalled rooms (veranda/porch/garden): thin outline, no fill.
    for room in rooms:
        if str(room.get("type", "")) not in UNWALLED_TYPES:
            continue
        ax, ay = point(room["x"], room["y"])
        bx, by = point(room["x"] + room["w"],
                       room["y"] + room["d"])
        ink.rectangle([min(ax, bx), min(ay, by), max(ax, bx),
                       max(ay, by)], outline="#000000", width=2)

    # Solid wall bands (same segments the SVG draws).
    placed = place_openings(rooms, open_plan, angle, glass)
    for seg in wall_segments(rooms, placed["doors"],
                             placed["windows"], open_plan, glass):
        ax, ay = point(seg["x0"], seg["y0"])
        bx, by = point(seg["x1"], seg["y1"])
        if seg["kind"] == "glass":
            _window_lines(ink, point, scale, seg)
        else:
            ink.rectangle([min(ax, bx), min(ay, by), max(ax, bx),
                           max(ay, by)], fill="#000000")

    # Furniture outlines per room type (gray, clear of door
    # swings) so the AI furnishes the right rooms.
    keep = _keepouts(rooms, placed["doors"])
    for room in rooms:
        for shape in _furniture_shapes(
                room, keep.get(room.get("name", ""), [])):
            _draw_shape(ink, shape, point)

    # Doors (leaf + swing arc) and windows (double lines).
    by_name = {r.get("name", ""): r for r in rooms}
    for door in placed["doors"]:
        _door_symbol(ink, door, by_name, point, scale)
    for win in placed["windows"]:
        _window_lines(ink, point, scale, win)
    return img


def _door_symbol(ink, door, by_name, point, scale):
    ends = [point(door["x0"], door["y0"]),
            point(door["x1"], door["y1"])]
    hinge = door.get("hinge", 0)
    hx, hy = ends[hinge]
    ex, ey = ends[1 - hinge]
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
        return
    nx, ny = -dy / gap, dx / gap
    if nx * (scx - hx) + ny * (scy - hy) < 0:
        nx, ny = -nx, -ny
    radius = float(door["width"]) * scale
    lx, ly = hx + nx * radius, hy + ny * radius
    ink.line([hx, hy, lx, ly], fill="#000000", width=2)
    a_leaf = math.degrees(math.atan2(ly - hy, lx - hx))
    a_gap = math.degrees(math.atan2(ey - hy, ex - hx))
    delta = (a_gap - a_leaf) % 360.0
    if delta > 180.0:
        delta -= 360.0
    lo = a_leaf + min(0.0, delta)
    ink.arc([hx - radius, hy - radius, hx + radius, hy + radius],
            start=lo, end=lo + abs(delta), fill="#000000", width=1)


def _window_lines(ink, point, scale, win):
    ax, ay = point(win["x0"], win["y0"])
    bx, by = point(win["x1"], win["y1"])
    dx, dy = bx - ax, by - ay
    gap = math.hypot(dx, dy)
    if gap < 0.01:
        return
    off = 0.125 * scale
    nx, ny = -dy / gap * off, dx / gap * off
    ink.line([ax + nx, ay + ny, bx + nx, by + ny], fill="#000000",
             width=1)
    ink.line([ax - nx, ay - ny, bx - nx, by - ny], fill="#000000",
             width=1)


def overlay_labels(img, rooms, open_plan, glass, angle, plot_w,
                   plot_d, road):
    """Room-name labels only, centered; larger rooms win when two
    labels would collide (smaller shrinks, then skips)."""
    ink = ImageDraw.Draw(img, "RGBA")
    point, scale = _frame(plot_w, plot_d, road)
    _ = (open_plan, glass, angle, scale)
    order = sorted(rooms,
                   key=lambda r: float(r["w"]) * float(r["d"]),
                   reverse=True)
    placed_boxes = []
    for room in order:
        ax, ay = point(room["x"], room["y"])
        bx, by = point(room["x"] + room["w"],
                       room["y"] + room["d"])
        x, y = min(ax, bx), min(ay, by)
        w_px, h_px = abs(bx - ax), abs(by - ay)
        label = _room_label(room, w_px)
        cx = x + w_px / 2.0
        cy = y + h_px / 2.0
        for size in (22, 18, 14):
            font = _font(size)
            bbox = ink.textbbox((cx, cy), label, font=font,
                                anchor="mm")
            if any(not (bbox[2] < px0 or bbox[0] > px1
                         or bbox[3] < py0 or bbox[1] > py1)
                   for px0, py0, px1, py1 in placed_boxes):
                continue
            ink.text((cx, cy), label, font=font, anchor="mm",
                     fill=(0, 0, 0, 255), stroke_width=2,
                     stroke_fill=(255, 255, 255, 220))
            placed_boxes.append(bbox)
            break
    return img


def drift_check_png(raw_img, rooms, open_plan, glass, angle,
                    plot_w, plot_d, road):
    """Temp inspection aid: thin red wall outlines over the raw
    render, to judge whether the AI's walls drifted from ours."""
    ink = ImageDraw.Draw(raw_img)
    point, scale = _frame(plot_w, plot_d, road)
    _ = scale
    placed = place_openings(rooms, open_plan, angle, glass)
    for seg in wall_segments(rooms, placed["doors"],
                             placed["windows"], open_plan, glass):
        ax, ay = point(seg["x0"], seg["y0"])
        bx, by = point(seg["x1"], seg["y1"])
        ink.rectangle([min(ax, bx), min(ay, by), max(ax, bx),
                       max(ay, by)], outline=(255, 0, 0), width=2)
    return raw_img


def edit_image(plan_png, api_key):
    """One Muse Image edit call; returns the raw PNG bytes."""
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    try:
        result = client.images.edit(
            model=IMAGE_MODEL, prompt=RENDER_PROMPT,
            image=("plan.png", plan_png, "image/png"),
            size="%dx%d" % CANVAS, n=1)
    except TypeError:  # older openai client: file object only
        result = client.images.edit(
            model=IMAGE_MODEL, prompt=RENDER_PROMPT,
            image=io.BytesIO(plan_png), n=1)
    item = result.data[0]
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    if getattr(item, "url", None):
        import urllib.request
        with urllib.request.urlopen(item.url, timeout=60) as resp:
            return resp.read()
    raise RuntimeError("Muse Image returned no image")


def main(export_only=False):
    key = "" if export_only else _read_key()
    if not key and not export_only:
        print("META_API_KEY missing (env or .env); cannot run.")
        return
    os.makedirs("review/renders", exist_ok=True)
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    plot = result["plot"]
    try:
        angle = float(plot.get("north_angle", 180)) % 360.0
    except (TypeError, ValueError):
        angle = 180.0
    road = str(plot["road"]).lower()
    for opt in result["options"]:
        label = opt["label"]
        rooms = opt["placements"]
        open_plan = opt.get("open_plan", [])
        glass = opt.get("glass_partitions", [])
        print("exporting T1-%s ..." % label)
        plan = draw_plan_png(rooms, open_plan, glass, angle,
                             plot["width"], plot["depth"], road)
        buf = io.BytesIO()
        plan.save(buf, format="PNG")
        plan_bytes = buf.getvalue()
        with open("review/renders/T1_%s_input.png" % label,
                  "wb") as handle:
            handle.write(plan_bytes)
        if export_only:
            continue
        print("editing T1-%s (1 image call) ..." % label)
        raw = edit_image(plan_bytes, key)
        with open("review/renders/T1_%s_raw.png" % label,
                  "wb") as handle:
            handle.write(raw)
        over = Image.open(io.BytesIO(raw)).convert("RGB")
        if over.size != CANVAS:
            print("  note: returned %s, expected %s" %
                  (over.size, CANVAS))
            over = over.resize(CANVAS)
        overlay_labels(over, rooms, open_plan, glass, angle,
                       plot["width"], plot["depth"], road)
        over.save("review/renders/T1_%s_overlaid.png" % label)
        drift = Image.open(io.BytesIO(raw)).convert("RGB")
        if drift.size != CANVAS:
            drift = drift.resize(CANVAS)
        drift_check_png(drift, rooms, open_plan, glass, angle,
                        plot["width"], plot["depth"], road)
        drift.save("review/renders/_drift_T1_%s.png" % label)
        print("saved T1-%s raw + overlaid + drift." % label)


if __name__ == "__main__":
    import sys
    main(export_only=len(sys.argv) > 1
         and sys.argv[1] == "export-only")
