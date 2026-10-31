# exp_render_plan.py
# STEP 1 EXPERIMENT (not wired into the app): rendered floor plans.
#
# What this script does (T1 options A/B/C only):
#   1. Exports each option as a PNG plan (walls, doors, windows,
#      verandas/porch outlines, plot boundary; no text, no dims) using
#      the SAME scale/margins/transform as draw.svg_plan.
#   2. Sends it to Muse Image EDIT mode (POST /v1/images/edits,
#      model muse-image-1.0) asking for a colored top-down
#      presentation render that keeps every wall/door/window in place.
#   3. Overlays the exact wall bands + room-name labels (same
#      coordinates) on the returned image so geometry stays correct.
#   4. Saves raw + overlaid PNGs to review/renders/ for review.
#
# Docs: dev.meta.ai/docs/image-generation ("Edit an image"):
# client.images.edit(model, prompt, image, size, n) - OpenAI-compatible.
# Pillow is pure pip (no system package), so this path also works on
# Streamlit Cloud. Cost: 3 image calls for T1 A/B/C.
#
# Run: .venv\Scripts\python.exe exp_render_plan.py

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
    "Render this architectural floor plan as a top-down colored "
    "presentation plan: warm wood floors in bedrooms and living "
    "spaces, light tiles in kitchen and toilets, simple furniture "
    "(beds, sofas, dining table, kitchen counter, toilet fixtures), "
    "green lawn and plants in the open areas, soft shadows. Keep "
    "every wall, door and window exactly where it is. Do not add or "
    "remove rooms. No text."
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


def overlay_walls_labels(img, rooms, open_plan, glass, angle, plot_w,
                         plot_d, road):
    """Draw the exact wall bands + room-name labels over a render."""
    ink = ImageDraw.Draw(img, "RGBA")
    point, scale = _frame(plot_w, plot_d, road)
    placed = place_openings(rooms, open_plan, angle, glass)
    for seg in wall_segments(rooms, placed["doors"],
                             placed["windows"], open_plan, glass):
        ax, ay = point(seg["x0"], seg["y0"])
        bx, by = point(seg["x1"], seg["y1"])
        ink.rectangle([min(ax, bx), min(ay, by), max(ax, bx),
                       max(ay, by)], fill=(30, 30, 30, 255))
    for room in rooms:
        if str(room.get("type", "")) not in UNWALLED_TYPES:
            ax, ay = point(room["x"], room["y"])
            bx, by = point(room["x"] + room["w"],
                           room["y"] + room["d"])
        else:
            ax, ay = point(room["x"], room["y"])
            bx, by = point(room["x"] + room["w"],
                           room["y"] + room["d"])
            ink.rectangle([min(ax, bx), min(ay, by), max(ax, bx),
                           max(ay, by)], outline=(30, 30, 30, 255),
                          width=2)
        x, y = min(ax, bx), min(ay, by)
        w_px, h_px = abs(bx - ax), abs(by - ay)
        label = _room_label(room, w_px)
        size = 22 if (h_px >= 44 and len(label) * 12 < w_px - 8) \
            else (18 if h_px >= 30 else 14)
        font = _font(size)
        cx = x + w_px / 2.0
        ink.text((cx, y + h_px / 2.0 - size / 2.0), label,
                 font=font, anchor="ma", fill=(0, 0, 0, 255),
                 stroke_width=2, stroke_fill=(255, 255, 255, 220))
    return img


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


def main():
    key = _read_key()
    if not key:
        print("META_API_KEY missing (env or .env); cannot run.")
        return
    os.makedirs("review/renders", exist_ok=True)
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    plot = result["plot"]
    try:
        angle = float(plot.get("north_angle", 180)) % 360.0
    except (TypeError, ValueError):
        angle = 180.0
    for opt in result["options"]:
        label = opt["label"]
        rooms = opt["placements"]
        open_plan = opt.get("open_plan", [])
        glass = opt.get("glass_partitions", [])
        print("exporting T1-%s ..." % label)
        plan = draw_plan_png(rooms, open_plan, glass, angle,
                             plot["width"], plot["depth"],
                             str(plot["road"]).lower())
        buf = io.BytesIO()
        plan.save(buf, format="PNG")
        plan_bytes = buf.getvalue()
        with open("review/renders/T1_%s_input.png" % label,
                  "wb") as handle:
            handle.write(plan_bytes)
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
        overlay_walls_labels(over, rooms, open_plan, glass, angle,
                             plot["width"], plot["depth"],
                             str(plot["road"]).lower())
        over.save("review/renders/T1_%s_overlaid.png" % label)
        print("saved T1-%s raw + overlaid." % label)


if __name__ == "__main__":
    main()
