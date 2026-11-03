# app.py
# House Planner web page (Day 2: brief -> room program -> floor plan).
#
# Run it with: streamlit run app.py
# Then open the local address Streamlit prints (usually http://localhost:8501).

import base64
import logging
import os
import re

import streamlit as st

st.set_page_config(layout="wide", page_title="House Planner",
                   page_icon="🏠",
                   initial_sidebar_state="expanded")

logger = logging.getLogger("house_planner")

from ai_program import format_ft_in, get_api_key, get_room_program
from draw import svg_plan, svg_plot_preview
from dxf_export import dxf_plan
from layout import _closest_road
from plan_render import render_plan_checked
from typology import build_options
from voice import transcribe_audio


# --- Demo look: one CSS block for the whole page ---
# Poppins for headings, Inter for everything else; warm orange
# gradient accents on light grey (#F5F6F8). Purely visual: if
# Streamlit ever renames a selector below, the page just falls back
# to its default look instead of breaking.
_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Poppins:wght@600;700;800&display=swap');

[data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    background-color: #F5F6F8;
}
h1, h2, h3 {
    font-family: 'Poppins', 'Inter', sans-serif !important;
}

/* Dark header band with a warm accent line. */
[data-testid="stMainBlockContainer"] { padding-top: 1rem; }
.hp-band {
    background: #1F2937;
    border-bottom: 3px solid #FF6B4A;
    border-radius: 0 0 22px 22px;
    margin: -1rem -2rem 1.6rem -2rem;
    padding: 2.2rem 2rem 1.6rem 2rem;
}
.hp-band h1 {
    font-size: 2.7rem; font-weight: 800; color: #FFFFFF;
    margin: 0; line-height: 1.1;
}
.hp-band p { color: #E5E7EB; font-size: 1.02rem; margin: .45rem 0 0 0; }
.hp-band .hp-concept { font-size: .8rem; color: #9CA3AF; margin-top: .5rem; }

/* Start-screen step cards + example plan. */
.hp-step {
    background: #FFFFFF; border: 1px solid #ECEEF2; border-radius: 22px;
    padding: 1.4rem 1.1rem; text-align: center;
    box-shadow: 0 8px 24px rgba(0, 0, 0, .06);
}
.hp-step-title {
    font-weight: 700; font-size: 1.05rem; color: #1F2937;
    margin: .6rem 0 .25rem 0;
}
.hp-step-text { color: #6B7280; font-size: .9rem; margin: 0; }
.hp-example {
    background: #FFFFFF; border: 1px solid #ECEEF2; border-radius: 22px;
    padding: 1.2rem; box-shadow: 0 8px 24px rgba(0, 0, 0, .06);
    margin-top: 1.4rem;
}
.hp-example svg { width: 100%; height: auto; display: block; }
.hp-caption {
    text-align: center; color: #6B7280; font-size: .85rem;
    margin: .5rem 0 0 0;
}

/* Orange icon tiles inside cards. */
.hp-step > svg {
    width: 44px; height: 44px; padding: 9px; box-sizing: border-box;
    background: #FFF1EA; border-radius: 14px;
}

/* Result cards: the plan and its side panel. */
[data-testid="stTabContent"] div[data-testid="column"] {
    background: #FFFFFF; border: 1px solid #ECEEF2; border-radius: 22px;
    padding: 1.4rem; box-shadow: 0 8px 24px rgba(0, 0, 0, .06);
}
.hp-option-title {
    font-size: 1.35rem; font-weight: 700; color: #1F2937;
    margin: 0 0 .5rem 0;
}

/* Gradient pill primary buttons; outlined DXF download. */
[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #FF8A3D, #FF5E62);
    border: none; border-radius: 999px; font-weight: 600;
}
[data-testid="stBaseButton-primary"]:hover {
    background: #F2553A; border: none;
}
div[data-testid="stDownloadButton"] button {
    border: 1.5px solid #FF6B4A; color: #FF6B4A; background: #FFFFFF;
    border-radius: 999px; font-weight: 600;
}
div[data-testid="stDownloadButton"] button:hover {
    border-color: #F2553A; color: #F2553A;
    background: #FFF1EA;
}

/* Option tabs as pill chips; selected is the warm gradient. */
button[data-testid="stTab"] {
    border: 1px solid #ECEEF2; border-radius: 999px; background: #FFFFFF;
    color: #1F2937; padding: 4px 18px;
}
button[data-testid="stTab"][aria-selected="true"] {
    background: linear-gradient(135deg, #FF8A3D, #FF5E62);
    border-color: transparent; color: #FFFFFF; font-weight: 700;
}

/* Hide Streamlit's menu, footer and branding. */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
</style>
"""

# Small line icons for the three start-screen cards (inline SVG so
# the page needs no image files or emoji).
_ICON_PLOT = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
              'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M3 11 12 4l9 7"/>'
              '<path d="M5 10v10h14V10"/><path d="M10 20v-5h4v5"/></svg>')
_ICON_PLAN = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
              'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
              'stroke-linejoin="round"><rect x="4" y="4" width="16" '
              'height="16" rx="1"/><path d="M4 12h16M12 12v8"/></svg>')
_ICON_RENDER = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
                'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
                'stroke-linejoin="round"><path d="M12 4v11"/>'
                '<path d="M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>')
_ICON_CHECK = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
               'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
               'stroke-linejoin="round"><circle cx="12" cy="12" r="8"/>'
               '<path d="M9 12l2 2 4-4"/></svg>')
_ICON_IMAGE = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
               'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
               'stroke-linejoin="round"><rect x="4" y="5" width="16" '
               'height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/>'
               '<path d="M4 17l5-4 4 3 3-2 4 3"/></svg>')
_ICON_FILE = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
              'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/>'
              '<path d="M14 3v4h4"/></svg>')
_ICON_MIC = ('<svg width="44" height="44" viewBox="0 0 24 24" fill="none" '
             'stroke="#FF6B4A" stroke-width="1.8" stroke-linecap="round" '
             'stroke-linejoin="round"><rect x="9" y="3" width="6" '
             'height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/>'
             '<path d="M12 18v3"/></svg>')
def _hero_img_tag():
    """Landing hero <img> tag from assets/hero.png, or "" if missing.

    The file is generated once with Muse Image and committed; the
    page never calls the image service at load. A missing file still
    leaves a clean gradient hero behind.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "assets", "hero.png")
    try:
        with open(path, "rb") as handle:
            blob = base64.b64encode(handle.read()).decode("ascii")
    except OSError:
        return ""
    return ('<img src="data:image/png;base64,%s" '
            'alt="Modern family house">' % blob)


# --- SaaS look: landing page + planner additions (loaded after _STYLE) ---
# Same deal as _STYLE: purely visual, fails soft if Streamlit ever
# renames a selector.
_STYLE_SAAS = """
<style>
/* Landing nav. */
.hp-logo {
    font-family: 'Poppins', 'Inter', sans-serif;
    font-weight: 800; font-size: 1.25rem; color: #1F2937;
    margin: 0; padding-top: .45rem;
}

/* One-screen landing: text left, image right (stacked on phones). */
.hp-screen {
    display: flex; gap: 2.5rem; align-items: center;
}
.hp-screen-txt { flex: 1 1 auto; }
.hp-pill-solid {
    display: inline-block; color: #FFFFFF;
    background: linear-gradient(135deg, #FF8A3D, #FF5E62);
    font-size: .78rem; font-weight: 600; letter-spacing: .06em;
    text-transform: uppercase; border-radius: 999px;
    padding: .3rem .9rem; margin: 0 0 .9rem 0;
}
.hp-screen h1 {
    font-size: clamp(2rem, 4.5vw, 3rem); font-weight: 800;
    color: #1F2937; margin: 0; line-height: 1.15;
}
.hp-screen p {
    color: #6B7280; font-size: clamp(1rem, 2vw, 1.12rem);
    margin: .9rem 0 0 0;
}
.hp-screen-img { flex: 0 0 44%; }
.hp-screen-img img {
    width: 100%; height: 52vh; object-fit: cover; display: block;
    border-radius: 22px; box-shadow: 0 8px 24px rgba(0, 0, 0, .10);
}
@media (max-width: 640px) {
    .hp-screen { flex-direction: column; gap: 1.2rem; }
    .hp-screen-img { flex-basis: auto; width: 100%; order: -1; }
    .hp-screen-img img { height: 30vh; }
}
.hp-footer {
    text-align: center; color: #6B7280; font-size: .8rem;
    margin: 1.2rem 0 0 0;
}

/* Voice card: title + hint on top, the REAL recorder joined below
   as one card, so the only mic-looking control is the live one. */
.hp-voice {
    background: #FFFFFF; border: 1px solid #ECEEF2;
    border-bottom: none; border-radius: 22px 22px 0 0;
    padding: 1.2rem 1rem .9rem 1rem; text-align: center;
    margin-bottom: 0;
}
.hp-voice-title {
    font-family: 'Poppins', 'Inter', sans-serif;
    font-weight: 800; font-size: 1.1rem; color: #1F2937;
    margin: 0 0 .2rem 0;
}
.hp-voice-hint { color: #6B7280; font-size: .88rem; margin: 0; }
[data-testid="stAudioInput"] {
    width: 100%; background: #FFFFFF; border: 1px solid #ECEEF2;
    border-top: none; border-radius: 0 0 22px 22px;
    padding: .9rem; box-shadow: 0 8px 24px rgba(0, 0, 0, .06);
}
[data-testid="stAudioInput"] button {
    min-height: 64px; width: 100%; border-radius: 14px;
    border: 1.5px solid #FF6B4A;
}
[data-testid="stAudioInput"] svg { width: 28px; height: 28px; }

/* Pill buttons with hover + rounded white inputs everywhere. */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
    border-radius: 999px; transition: all .15s ease;
}
[data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(255, 107, 74, .35);
}
[data-testid="stBaseButton-secondary"]:hover {
    border-color: #FF6B4A; color: #FF6B4A;
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    border-radius: 14px; background-color: #FFFFFF;
    border-color: #ECEEF2;
}
[data-testid="stExpander"] { border-radius: 12px; }

/* Sidebar: white panel, orange section labels. */
[data-testid="stSidebarContent"] { background-color: #FFFFFF; }
[data-testid="stSidebar"] h3 {
    font-family: 'Inter', sans-serif !important;
    font-size: .78rem !important; letter-spacing: .09em;
    text-transform: uppercase; color: #FF6B4A !important;
}

/* Transparent header: the menu bar and branding stay hidden,
   but the sidebar expand button (the only way back into the
   inputs once the sidebar is closed - the default on phones)
   stays visible as a big orange round button. The button lives
   INSIDE the toolbar, so the toolbar hides with visibility
   (which a child can override) instead of display:none (which
   no child can escape). The header is an absolute overlay, so
   this moves no page content on desktop. */
[data-testid="stHeader"] { background-color: transparent; }
[data-testid="stToolbar"] { visibility: hidden; }
[data-testid="stExpandSidebarButton"] {
    visibility: visible !important;
    position: fixed; top: 0.75rem; left: 0.75rem; z-index: 999;
    display: flex; align-items: center; justify-content: center;
    width: 48px; height: 48px; min-width: 48px; min-height: 48px;
    padding: 0; border: none; border-radius: 50%;
    background: linear-gradient(135deg, #FF8A3D, #FF5E62);
    color: #FFFFFF; cursor: pointer;
    box-shadow: 0 4px 12px rgba(0, 0, 0, .25);
}
[data-testid="stExpandSidebarButton"]:hover {
    background: #F2553A;
}
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stExpandSidebarButton"] span {
    color: #FFFFFF !important; fill: #FFFFFF !important;
}

/* Phone-only hint above the planner step cards. */
.hp-mobile-hint { display: none; }
@media (max-width: 768px) {
    .hp-mobile-hint {
        display: block; text-align: center; color: #6B7280;
        font-size: .9rem; margin: 0 0 1rem 0;
    }
}

/* AI activity card: rows of dot + model + task + duration. */
.hp-act {
    background: #FFFFFF; border: 1px solid #ECEEF2; border-radius: 14px;
    padding: .8rem .9rem; margin-top: .8rem;
}
.hp-act-title {
    font-family: 'Poppins', 'Inter', sans-serif;
    font-weight: 700; font-size: .95rem; color: #1F2937; margin: 0;
}
.hp-act-sub { color: #6B7280; font-size: .78rem; margin: 0 0 .5rem 0; }
.hp-act-row {
    display: flex; align-items: center; gap: .45rem;
    font-size: .82rem; color: #1F2937; padding: .18rem 0;
}
.hp-act-row b { font-weight: 700; }
.hp-act-dur { margin-left: auto; color: #6B7280; white-space: nowrap; }
.hp-dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.hp-dot-done { background: #22C55E; }
.hp-dot-retried { background: #F59E0B; }
.hp-dot-failed { background: #EF4444; }
</style>
"""

# Landing only: no sidebar at all (injected on the home screen).
# The expand button lives in the header toolbar, outside the
# sidebar, so it needs its own rule (both the current testid and
# the pre-1.66 one, in case Cloud ever serves another build).
_HIDE_SIDEBAR = """
<style>
[data-testid="stSidebar"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
[data-testid="stExpandSidebarButton"] { display: none !important; }
</style>
"""

# Landing only: the one screen fills the viewport and sits centered
# in it (injected on the home screen, never on the planner).
_HOME_CENTER = """
<style>
[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] {
    min-height: 100vh; min-height: 100dvh; justify-content: center;
}
</style>
"""


def _example_svg():
    """One saved review plan for the start screen, or "" if missing.

    Reads a committed review SVG (display only; the drawing code in
    draw.py is untouched). A missing file hides the example instead
    of breaking the page.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "review", "T1_40x60_North_A_OK.svg")
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _render_option_plan(plot, option, extra=""):
    """Colored presentation render of one option, auto-checked.

    Returns (png_bytes, note): note names the rooms to compare
    with the plan when the check flags any, else "". Raises with
    a friendly message when the key is missing or the calls fail.
    """
    try:
        angle = float(plot.get("north_angle", 0)) % 360.0
    except (TypeError, ValueError):
        angle = 0.0
    key = (get_api_key() or "").strip()
    if not key:
        raise RuntimeError(
            "META_API_KEY is missing, so no render was made. On "
            "Streamlit Cloud add it under Settings > Secrets; on your "
            "laptop put META_API_KEY=your-key-here in .env.")
    png, check, _attempts = render_plan_checked(
        option["placements"], option.get("open_plan", []),
        option.get("glass_partitions", []), angle,
        float(plot["width"]), float(plot["depth"]),
        str(plot["road"]).lower(), key, extra=extra or "")
    if check is None or check["all_ok"]:
        return png, ""
    bad = [name for name, verdict in check["rooms"].items()
           if not verdict["ok"]]
    return png, "Compare these rooms with the plan: %s." % (
        ", ".join(bad))


def _svg_for_option(plot, option):
    """Render one typology option via svg_plan (adapts the plan shape)."""
    return svg_plan({"ok": True, "placements": option["placements"],
                     "open_plan": option.get("open_plan", []),
                     "glass_partitions": option.get("glass_partitions",
                                                   []),
                     "plot": {"w": plot["width"], "d": plot["depth"],
                              "road": plot["road"],
                              "north_angle": plot.get("north_angle", 0)}})


def _dxf_for_option(plot, option):
    """Render one typology option via dxf_plan (same adapted shape)."""
    return dxf_plan({"ok": True, "placements": option["placements"],
                     "open_plan": option.get("open_plan", []),
                     "glass_partitions": option.get("glass_partitions",
                                                   []),
                     "plot": {"w": plot["width"], "d": plot["depth"],
                              "road": plot["road"],
                              "north_angle": plot.get("north_angle", 0)}})


def _rooms_for_table(rooms):
    """Format rooms for display: ft-in sizes, areas, features as text.

    Streamlit tables show plain text best, so lists (features,
    adjacencies) become comma-separated strings here.
    """
    rows = []
    for room in rooms:
        width = room.get("width_ft")
        depth = room.get("depth_ft")
        try:
            area = float(width) * float(depth)
            area_text = f"{area:.0f} sq ft"
        except (TypeError, ValueError):
            area_text = "?"
        features = room.get("features") or []
        room_type = str(room.get("type", "?"))
        toilet_use = ""
        if room_type.strip().lower() == "bathroom":
            kind = str(room.get("bathroom_kind", "")).strip().lower()
            target = str(room.get("attached_to", "")).strip()
            if kind == "common":
                toilet_use = "Family toilet"
            elif target:
                toilet_use = "Toilet for %s" % target
            elif kind == "attached":
                toilet_use = "With a bedroom"
            room_type = "Toilet"
        rows.append({
            "Name": room.get("name", "?"),
            "Type": room_type,
            "Width": format_ft_in(width),
            "Depth": format_ft_in(depth),
            "Area": area_text,
            "Door into": room.get("door_opens_into", "?"),
            "Veranda": "yes" if room.get("needs_veranda") else "no",
            "Toilet use": toilet_use,
            "Features": ", ".join(features),
        })
    return rows


def _plain_title(opt):
    """Client-friendly option title, e.g. 'Kitchen on the west side'."""
    title = str(opt.get("title", ""))
    low = title.lower()
    match = re.search(
        r"kitchen (?:\+ master )?"
        r"(west|east|north|south|road-left|road-right)", low)
    master = re.search(
        r"master (front )?(west|east|north|south|road-left|road-right)",
        low)
    if match:
        side = match.group(1)
        if side == "road-left":
            base = "Kitchen on the left side"
        elif side == "road-right":
            base = "Kitchen on the right side"
        else:
            base = "Kitchen on the %s side" % side
    elif master:
        side = master.group(2)
        if master.group(1):
            base = "Master bedroom at the front, %s side" % side
        else:
            base = "Master bedroom on the %s side" % side
    elif "l-shape" in low:
        base = "L-shaped plan with a garden court"
    else:
        rooms = re.search(
            r"rooms (west|east|north|south|road-left|road-right)", low)
        if rooms:
            base = "Rooms on the %s side" % rooms.group(1)
        else:
            base = "Layout variant %s" % opt.get("label", "")
    if "unmet" in low:
        base += "; kitchen with a window"
    elif "jali-screened" in low:
        base += "; kitchen veranda with a privacy screen"
    elif "no kitchen veranda" in low:
        base += "; kitchen with a window instead of a veranda"
    elif "kitchen veranda on" in low or "off-road" in low:
        base += "; kitchen veranda away from the road"
    return base


def _wishes_line(opt):
    """'Your wishes: X of Y included', or '' when no wishes were read."""
    wishes = opt.get("wishes", [])
    if not wishes:
        return ""
    met = sum(1 for row in wishes if row["status"] == "MET")
    return "Your wishes: %d of %d included" % (met, len(wishes))


_NOTE_PATTERNS = [
    # Internal builder notes translated to plain design notes. Any
    # note matching nothing here is skipped on the card (it stays
    # in the code and tests, just not in front of the client).
    (re.compile(r"Glass partition with a sliding glass door between "
                r"(.+) and (.+) \(variety\)\.?"),
     lambda m: "%s and %s joined by a glass partition with a "
               "sliding door." % (m.group(1), m.group(2))),
    (re.compile(r"Glass partition: (.+) \+ (.+) share .*sliding.*"),
     lambda m: "%s and %s joined by a glass partition with a "
               "sliding door." % (m.group(1), m.group(2))),
    (re.compile(r"Open plan: (.+) \+ (.+) share .*one gathering.*"),
     lambda m: "%s and %s share one open gathering space."
               % (m.group(1), m.group(2))),
    (re.compile(r"Garden placed in front of (.+?) \(.*"),
     lambda m: "A small garden sits in front of %s."
               % m.group(1)),
    (re.compile(r"Garden fills the leftover .* at the end of the "
                r"(front|back) row\.?"),
     lambda m: "A garden fills the open end of the plan."),
    (re.compile(r"Court garden fills the open .* corner .*"),
     lambda m: "A courtyard garden fills the open corner."),
    (re.compile(r"Open court fills the L's back-east corner\."),
     lambda m: "An open court fills the corner of the L."),
    (re.compile(r"House .* wide in .* buildable; sides stay landscape\."),
     lambda m: "Open green space along the sides of the house."),
    (re.compile(r"(.+) on the (.+) side \(client wish\)\."),
     lambda m: "%s is on the %s side, as you wished."
               % (m.group(1), m.group(2))),
    (re.compile(r"(.+) placed in the front corner \(client wish.*"),
     lambda m: "%s sits in a front corner, as you wished."
               % m.group(1)),
    (re.compile(r"(.+) placed (.+) \(client wish: (.+) facing\)\."),
     lambda m: "%s faces %s, as you wished."
               % (m.group(1), m.group(3))),
    (re.compile(r"Living Room moves to a front corner.*"),
     lambda m: "The living room sits in a front corner by the "
               "entrance."),
    (re.compile(r"Option C keeps rooms separate \(compare with .*"),
     lambda m: "This option keeps rooms separate so you can "
               "compare."),
    (re.compile(r"Compact two-strip: .*"),
     lambda m: "A compact plan shaped for a narrow plot."),
    (re.compile(r"No kitchen veranda \(option C choice\): the "
                r"kitchen window ventilates from the . wall\."),
     lambda m: "The kitchen gets light and air from its window."),
]


def _design_notes(opt):
    """Up to 3 short plain design notes; skips internal notes."""
    out = []
    for note in opt.get("notes", []):
        for pattern, plain in _NOTE_PATTERNS:
            match = pattern.match(note)
            if match:
                text = plain(match)
                if text not in out:
                    out.append(text)
                break
        if len(out) >= 3:
            break
    return out[:3]


_PLAIN_RULES = {
    "1": "Room sizes feel right",
    "2": "No dark central corridor",
    "3": "Corridors stay small",
    "4": "Kitchen opens into dining",
    "5": "Bedrooms open off family living",
    "6": "Every bedroom has a window",
    "7": "Right toilets in the right places",
    "8": "Toilets ventilated, away from the front",
    "9": "Toilet windows face away from the road",
    "10": "Verandas separate and well sized",
    "11": "Fresh air from two sides in every room",
    "12": "Doors and windows all drawn",
    "13": "Kitchen has an outside wall and veranda",
    "14": "Bedrooms have window walls",
    "15": "Every toilet has an outside wall",
    "16": "Easy movement without passing through bedrooms",
    "17": "Living spaces open to two sides",
    "18": "Toilets are practical sizes",
    "19": "Master bedroom is the largest",
    "20": "Living spaces have windows",
    "21": "Kitchen windows face away from the road",
    "G": "Everything fits inside the plot",
}

_PLAIN_GOALS = {
    "Good entry (porch + foyer)": "Welcoming entry with porch",
    "Outline not a plain rectangle": "Lively building outline",
    "Landscape left on big plots": "Garden space left over",
    "Kitchen west (among dining/family)": "Kitchen on the west side",
}

_WISH_RESULT = {"MET": "Included", "NOT MET": "Not included",
                "SKIPPED": "Not advised"}


def _check_result(status):
    """Plain checklist result: Met / Not met / Partly."""
    return {"PASS": "Met", "FAIL": "Not met", "BEND": "Partly",
            "MET": "Met", "MISSED": "Not met"}.get(status, "--")


def _checklist_rows(opt):
    """Every rule + goal as plain {Check, Result} rows (no numbers)."""
    rows = []
    for row in opt.get("rules", []):
        rows.append({"Check": _PLAIN_RULES.get(row["id"], row["name"]),
                     "Result": _check_result(row["status"])})
    for row in opt.get("goals", []):
        rows.append({"Check": _PLAIN_GOALS.get(row["name"], row["name"]),
                     "Result": _check_result(row["status"])})
    return rows


def _why_it_works(opt):
    """Checklist rows as short plain sentences (no ticks or scores)."""
    sentences = []
    for row in _checklist_rows(opt):
        if row["Result"] == "Met":
            sentences.append("%s." % row["Check"])
        elif row["Result"] == "Partly":
            sentences.append("%s - partly, worth a second look."
                             % row["Check"])
        else:
            sentences.append("%s - needs a closer look."
                             % row["Check"])
    return sentences


_FRIENDLY_RULE = {
    "4": "Kitchen door does not open into dining",
    "5": "A bedroom door does not open into family living or dining",
    "7": "A toilet is missing, misplaced, or has no door",
    "13": "Kitchen has no exterior wall or veranda",
    "14": "A bedroom has no window wall",
    "15": "A toilet has no exterior wall",
    "16": "Some rooms can only be reached through the kitchen, "
           "a bedroom, or a toilet",
    "G": "Rooms do not fit inside the plot",
}


def _friendly_issues(opt):
    """One plain-language sentence per failed hard rule."""
    by_id = {row["id"]: row for row in opt["rules"]}
    sentences = []
    for rule_id in opt["livability_fails"]:
        detail = by_id.get(rule_id, {}).get("detail", "")
        if rule_id == "19":
            for part in detail.split("; "):
                size = re.match(r"(.+?) \(\d+ sq ft\) not 10% over "
                                r"(.+?) \(\d+ sq ft\)", part)
                if size:
                    sentences.append("Master bedroom is smaller than %s"
                                     % size.group(2))
                elif "smaller than another" in part:
                    sentences.append("Master toilet is smaller than "
                                     "another attached toilet")
                elif part:
                    sentences.append("Master bedroom rule needs review")
        elif rule_id in _FRIENDLY_RULE:
            sentences.append(_FRIENDLY_RULE[rule_id])
    return sentences


def _show_error(friendly, err):
    """Friendly error for users; raw text hidden in an expander."""
    st.error(friendly)
    with st.expander("Technical details"):
        st.code("%s: %s" % (type(err).__name__, err))



_RESULT_KEYS = ("result_signature", "result_program", "result_options")


def _safe_float(value):
    """float(value), or None when the field is still empty."""
    if value is None:
        return None
    return float(value)


def _safe_int(value):
    """int(value), or None when the field is still empty."""
    if value is None:
        return None
    return int(value)


def _brief_signature(frontage_ft, depth_ft, north_angle, num_bedrooms,
                     toilets_text, wishes):
    """Fingerprint of the current brief; any input change alters it."""
    return (_safe_float(frontage_ft), _safe_float(depth_ft),
            _safe_float(north_angle), _safe_int(num_bedrooms),
            str(toilets_text).strip(), str(wishes or ""))


def _missing_fields(frontage_ft, depth_ft, num_bedrooms, toilets_text):
    """Labels of the required fields the client has not filled yet."""
    missing = []
    if frontage_ft is None:
        missing.append("road frontage")
    if depth_ft is None:
        missing.append("plot depth")
    if num_bedrooms is None:
        missing.append("number of bedrooms")
    if not str(toilets_text or "").strip():
        missing.append("number of toilets")
    return missing


def _has_results(state):
    """True when a full generated result is stored."""
    return all(key in state for key in _RESULT_KEYS)


def _results_stale(state, signature):
    """True when stored results belong to an older brief."""
    return _has_results(state) and state["result_signature"] != signature


def _remember_results(state, signature, program, options):
    """Store one generation (program + options) under the brief."""
    state["result_signature"] = signature
    state["result_program"] = program
    state["result_options"] = options


def _clear_results(state):
    """Drop stored results (old plans never show for a new brief)."""
    for key in _RESULT_KEYS:
        state.pop(key, None)


MAX_GENERATIONS = 10
MAX_RENDERS = 5
DEMO_LIMIT_MESSAGE = ("Demo limit reached - thanks for trying "
                      "House Planner!")


def _demo_used(state, key):
    """How many of a limited demo action this session has used."""
    try:
        return max(int(state.get(key, 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


def _demo_allowed(state, key, limit):
    """True while the session still has quota left for the action."""
    return _demo_used(state, key) < limit


def _demo_bump(state, key):
    """Record one completed demo action (counts only successes)."""
    state[key] = _demo_used(state, key) + 1


def _options_sentence(count):
    """Grammar-clean 'Here are N layout options...' intro line."""
    if count == 1:
        head = "Here is 1 layout option for your brief."
    else:
        head = "Here are %d layout options for your brief." % count
    return (head + " 'Needs review' means this option is worth "
            "a second look - the reason is shown under that option.")


def _activity_entries():
    """Stored activity entries (newest last), or [] outside runs."""
    try:
        return list(st.session_state.get("ai_activity") or [])
    except Exception:
        return []


def _activity_card():
    """Compact 'AI activity' card HTML, or "" when nothing ran yet."""
    entries = _activity_entries()
    if not entries:
        return ""
    dots = {"done": "hp-dot-done", "retried": "hp-dot-retried",
            "failed": "hp-dot-failed"}
    rows = []
    for row in reversed(entries):
        try:
            duration = "%.1f s" % float(row.get("seconds", 0))
        except (TypeError, ValueError):
            duration = "? s"
        rows.append(
            '<div class="hp-act-row"><span class="hp-dot %s"></span>'
            "<b>%s</b><span>%s</span>"
            '<span class="hp-act-dur">%s</span></div>'
            % (dots.get(row.get("status"), "hp-dot-done"),
               row.get("label", "?"), row.get("task", "?"), duration))
    return (
        '<div class="hp-act"><div class="hp-act-title">AI activity</div>'
        '<p class="hp-act-sub">Live calls to Meta models</p>%s</div>'
        % "".join(rows))

# --- Screen router: landing first, planner on "Start planning" ---
# Both style blocks load on every screen; the landing hides the
# sidebar and stops before the planner code below. Switching screens
# is plain session state, so no reload ever loses the inputs.
st.markdown(_STYLE, unsafe_allow_html=True)
st.markdown(_STYLE_SAAS, unsafe_allow_html=True)
_SCREEN = st.session_state.get("screen", "home")
if _SCREEN == "home":
    st.markdown(_HIDE_SIDEBAR, unsafe_allow_html=True)
    st.markdown(_HOME_CENTER, unsafe_allow_html=True)
    # One screen: logo, image + text side by side, one button, footer.
    st.markdown('<p class="hp-logo">House Planner</p>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="hp-screen">'
        '<div class="hp-screen-txt">'
        '<span class="hp-pill-solid">Plan - Render - Download</span>'
        "<h1>Design Your Home Smarter</h1>"
        "<p>Enter your plot and family needs. Get three layouts, "
        "a colored render and a DXF file.</p>"
        "</div>"
        '<div class="hp-screen-img">%s</div>'
        "</div>" % _hero_img_tag(),
        unsafe_allow_html=True)
    home_go = st.button("Start planning", key="home_start",
                        type="primary")
    st.markdown('<p class="hp-footer">Concept only - not for '
                "construction</p>", unsafe_allow_html=True)
    if home_go:
        st.session_state["screen"] = "planner"
        st.rerun()
    st.stop()

# --- Planner screen: back link + header band + sidebar + results ---
if st.button("\u2190 Back to home", key="back_home"):
    st.session_state["screen"] = "home"
    st.rerun()
st.markdown(
    '<div class="hp-band">'
    "<h1>House Planner</h1>"
    "<p>Concept floor plans in seconds</p>"
    '<p class="hp-concept">Concept only - not for construction</p>'
    "</div>",
    unsafe_allow_html=True)

# --- Sidebar: EVERY input lives here ---
# Keep every input simple; plot numbers are in feet. The small plot
# preview redraws on every change (Streamlit reruns the page).
with st.sidebar:
    if st.button("Try an example"):
        st.session_state["in_frontage"] = 48
        st.session_state["in_depth"] = 55
        st.session_state["in_north"] = 180
        st.session_state["in_bedrooms"] = 3
        st.session_state["in_toilets"] = "3"
        st.rerun()
    st.subheader("Plot")
    frontage_ft = st.number_input("Road frontage (ft)", min_value=10, value=None, placeholder="e.g. 40", key="in_frontage")
    depth_ft = st.number_input("Plot depth from road (ft)", min_value=10, value=None, placeholder="e.g. 60", key="in_depth")
    north_angle = st.slider(
        "North direction (degrees)",
        min_value=0, max_value=360, value=0, key="in_north",
        help="Drag until the north arrow matches your plot: 0 = north "
             "points away from the road (road on the south side).",
    )
    road_side = _closest_road(north_angle)
    st.caption("Road on the %s side." % road_side.capitalize())
    if frontage_ft and depth_ft:
        st.markdown(svg_plot_preview(frontage_ft, depth_ft, north_angle),
                    unsafe_allow_html=True)
    else:
        st.caption("Enter frontage and depth to see your plot.")
    st.divider()
    st.subheader("Family")
    num_bedrooms = st.number_input("Number of bedrooms", min_value=1,
                                   max_value=10, value=None,
                                   placeholder="e.g. 3", key="in_bedrooms")
    # Toilets: NO default on purpose. The field starts empty and the
    # client must fill it; the allowed range shows once bedrooms do.
    max_toilets = int(num_bedrooms) + 1 if num_bedrooms else None
    toilets_text = st.text_input(
        "Number of toilets",
        value="", key="in_toilets",
        placeholder="e.g. 2",
    )
    if max_toilets:
        st.caption("Whole number from 1 to %d." % max_toilets)
    st.divider()
    st.subheader("Wishes")
    st.markdown(
        '<div class="hp-voice">'
        '<div class="hp-voice-title">Speak your brief</div>'
        '<p class="hp-voice-hint">Tap and talk - we\'ll type it '
        "for you</p></div>", unsafe_allow_html=True)
    voice_note = st.audio_input("Speak your brief (optional)",
                                label_visibility="collapsed")
    if voice_note is not None:
        # New recording only: transcribe once, then fill the wishes box
        # below (set before the widget exists, so no rerun warning).
        heard = voice_note.getvalue()
        if st.session_state.get("voice_digest") != hash(heard):
            with st.spinner("Muse Voice Transcribe is typing your "
                                "brief..."):
                try:
                    said = transcribe_audio(heard)
                except Exception as err:
                    _show_error("Could not transcribe this recording.", err)
                    said = ""
            st.session_state["voice_digest"] = hash(heard)
            if said:
                st.session_state["in_wishes"] = said
                st.rerun()
    if any(row.get("task") == "Voice brief"
           for row in _activity_entries()):
        st.markdown(_activity_card(), unsafe_allow_html=True)
    wishes = st.text_area(
        "Family needs and wishes (plain words)",
        placeholder="Example: home office, big kitchen for family gatherings, elderly parent on ground floor",
        key="in_wishes",
    )
    generate_pressed = st.button("Generate plans", type="primary",
                                        use_container_width=True)

_signature = _brief_signature(frontage_ft, depth_ft, north_angle,
                              num_bedrooms, toilets_text, wishes)
if _results_stale(st.session_state, _signature):
    _clear_results(st.session_state)

# --- Generate: ask the AI, then store results in session state ---
if generate_pressed:
    # Empty inputs: list everything missing in one friendly message.
    missing = _missing_fields(frontage_ft, depth_ft, num_bedrooms,
                              toilets_text)
    if missing:
        st.warning("Please fill in: %s - or press 'Try an example'."
                   % ", ".join(missing))
        st.stop()
    frontage_ft = float(frontage_ft)
    depth_ft = float(depth_ft)
    num_bedrooms = int(num_bedrooms)
    max_toilets = num_bedrooms + 1
    try:
        num_toilets = int(toilets_text.strip())
    except ValueError:
        st.error("Number of toilets must be a whole number (1 to %d)." % max_toilets)
        st.stop()
    if not 1 <= num_toilets <= max_toilets:
        st.error("Number of toilets must be from 1 to %d (bedrooms + 1)." % max_toilets)
        st.stop()

    # Demo guard: at most 10 plan generations per browser session.
    if not _demo_allowed(st.session_state, "generations_used",
                         MAX_GENERATIONS):
        st.info(DEMO_LIMIT_MESSAGE)
        st.stop()

    if not get_api_key():
        st.warning("The AI service is not configured.")
        st.write("Add your Meta Model API key as META_API_KEY in the app's "
                 "Secrets settings (Streamlit Cloud) or in a local .env "
                 "file, then try again.")
        st.stop()
    # While waiting, show a spinner so the page does not look frozen.
    with st.spinner("Muse Spark is building the room program..."):
        try:
            result = get_room_program(
                frontage_ft, depth_ft, road_side,
                int(num_bedrooms), num_toilets, wishes, north_angle,
            )
        except Exception as err:
            _show_error("Could not shape the rooms from your brief. Check "
                        "your API key and connection, then try again.", err)
            st.stop()
    rooms = result["rooms"]
    with st.spinner("Building layout options..."):
        try:
            options_result = build_options(
                rooms, frontage_ft, depth_ft, road_side, num_toilets,
                wishes, north_angle,
            )
        except Exception as err:
            _show_error("Could not lay out the plan from this program.", err)
            st.stop()
    _remember_results(st.session_state, _signature, result,
                        options_result)
    _demo_bump(st.session_state, "generations_used")

if _has_results(st.session_state):
    result = st.session_state["result_program"]
    options_result = st.session_state["result_options"]
    # Placer notes go to the log now, never on the page.
    for item in options_result["notes"]:
        logger.info("placer note: %s", item)
    rooms = result["rooms"]
    options = options_result["options"]
    if not options:
        st.warning("No option fits this plot; try a bigger plot or fewer rooms.")
        st.stop()
    plot = options_result["plot"]
    st.write(_options_sentence(len(options)))
    if len(options) == 2:
        st.info("Two layouts fit this plot shape.")
    # PLANS FIRST: one tab per option; the plan draws LARGE on the
    # left (two thirds) with a narrow info panel on the right.
    tabs = st.tabs(["Option %s" % opt["label"] for opt in options])
    for tab, opt in zip(tabs, options):
        with tab:
            plan_col, side_col = st.columns([2, 1])
            cache = st.session_state.setdefault("plan_renders", {})
            notes = st.session_state.setdefault("plan_render_notes",
                                                {})
            with side_col:
                st.markdown('<p class="hp-option-title">%s</p>'
                            % _plain_title(opt), unsafe_allow_html=True)
                if opt["livable"]:
                    st.success("All key rules met")
                else:
                    st.warning("Needs review")
                    for sentence in _friendly_issues(opt):
                        st.write(sentence)
                wishes_line = _wishes_line(opt)
                if wishes_line:
                    st.write(wishes_line)
                for note in _design_notes(opt):
                    st.write("- " + note)
                with st.expander("Render options"):
                    extra = st.text_input(
                        "Extra instructions for the render",
                        key="extra_%s" % opt["label"],
                        placeholder="e.g. marble tiles in living, plants "
                                    "on verandas")
                plan_key = "%s|%s|%d|%d" % (
                    opt["label"], opt["title"],
                    hash(repr(opt["placements"])), hash(extra or ""))
                if plan_key in cache:
                    want_render = st.button(
                        "Regenerate", key="regen_%s" % opt["label"],
                        type="primary", use_container_width=True)
                else:
                    want_render = st.button(
                        "Render this plan",
                        key="render_%s" % opt["label"],
                        type="primary", use_container_width=True)
                if want_render:
                    # Demo guard: at most 5 renders per browser session.
                    if not _demo_allowed(st.session_state, "renders_used",
                                         MAX_RENDERS):
                        st.info(DEMO_LIMIT_MESSAGE)
                    else:
                        with st.spinner("Muse Image is rendering the "
                                        "plan..."):
                            try:
                                png, note = _render_option_plan(
                                    plot, opt, extra or "")
                            except Exception as err:
                                _show_error("Could not render this plan.",
                                            err)
                            else:
                                cache[plan_key] = png
                                notes[plan_key] = note
                                _demo_bump(st.session_state, "renders_used")
                                st.rerun()
                st.download_button(
                    "Download DXF",
                    data=_dxf_for_option(plot, opt),
                    file_name="house_plan_option_%s.dxf" % opt["label"],
                    mime="image/vnd.dxf",
                    key="dxf_%s" % opt["label"],
                    use_container_width=True)
                activity = _activity_card()
                if activity:
                    st.markdown(activity, unsafe_allow_html=True)
            with plan_col:
                st.markdown(_svg_for_option(plot, opt),
                            unsafe_allow_html=True)
                if plan_key in cache:
                    st.image(
                        cache[plan_key],
                        caption="AI renders are experimental and may "
                                "not match the plan exactly. The floor "
                                "plan is the reliable drawing; always "
                                "check the render against it.")
                    st.download_button(
                        "Download image",
                        data=cache[plan_key],
                        file_name="house_plan_option_%s_render.png"
                                  % opt["label"],
                        mime="image/png",
                        key="img_%s" % opt["label"],
                        use_container_width=True)
                    if notes.get(plan_key):
                        st.caption(notes[plan_key])
    # ONE collapsed expander with everything else, for one option.
    with st.expander("Plan details"):
        labels = [opt["label"] for opt in options]
        picked = st.radio("Details for option", labels, horizontal=True,
                          key="details_option")
        detail = {opt["label"]: opt for opt in options}[picked]
        # 1. Rooms as a table (sizes in feet and inches).
        st.subheader("Rooms")
        if rooms:
            st.table(_rooms_for_table(rooms))
        else:
            st.warning("The AI returned no rooms. Try again with simpler wishes.")

        # 2. Design explanation in the architect's voice.
        st.subheader("Design explanation")
        st.write(result["design_explanation"] or "No explanation returned.")

        # 3. Space check: do the rooms fit on the plot?
        st.subheader("Space check")
        buildable = result["buildable"]
        area = result["program_area"]
        st.write(
            f"Buildable after setbacks: {buildable['area']:.0f} sq ft "
            f"({format_ft_in(buildable['width'])} x {format_ft_in(buildable['depth'])})."
        )
        st.write(
            f"Your rooms: rooms {area['net']:.0f} + interior walls {area['interior_walls']:.0f} "
            f"+ exterior walls {area['exterior_walls']:.0f} = {area['total']:.0f} sq ft "
            f"(corridors {area['circulation']:.0f} sq ft of the rooms)."
        )
        if result["revised"] and not result["area_warning"]:
            st.info("The first draft was too big, so the rooms were shrunk to fit.")
        if result["area_warning"]:
            st.warning(result["area_warning"])
        else:
            st.success("Your rooms fit inside the buildable area.")

        # 4. Room sizes.
        st.subheader("Room sizes")
        problems = result["size_problems"]
        if not problems:
            st.success("All room sizes look good.")
        else:
            st.warning("Some rooms need attention:")
            for item in problems:
                st.write("- " + item)

        # 5. Toilets.
        st.subheader("Toilets")
        toilet_problems = result["toilet_problems"]
        if not toilet_problems:
            st.success("The toilet arrangement looks good.")
        else:
            st.warning("The toilets need attention:")
            for item in toilet_problems:
                st.write("- " + item)

        # 6. Why this plan works: short plain sentences, no ticks.
        st.subheader("Why this plan works")
        for sentence in _why_it_works(detail):
            st.write(sentence)
        if detail["wishes"]:
            st.table([
                {"Your wish": row["wish"],
                 "Result": _WISH_RESULT.get(row["status"],
                                           row["status"])}
                for row in detail["wishes"]
            ])
    st.caption("Concept only - not for construction.")
else:
    # Before generating: three clean step cards + one example plan.
    # The hint shows on phones only (CSS media query); on desktop
    # the sidebar sits open next to the cards, so it stays hidden.
    st.markdown(
        '<p class="hp-mobile-hint">Tap the orange button at the '
        "top left to enter your plot details</p>",
        unsafe_allow_html=True)
    step1, step2, step3 = st.columns(3)
    with step1:
        st.markdown(
            '<div class="hp-step">%s'
            '<div class="hp-step-title">Describe your plot</div>'
            '<p class="hp-step-text">Plot size, road side and family</p>'
            "</div>" % _ICON_PLOT, unsafe_allow_html=True)
    with step2:
        st.markdown(
            '<div class="hp-step">%s'
            '<div class="hp-step-title">Get 3 plan options</div>'
            '<p class="hp-step-text">Three layouts that follow '
            "proven design rules</p>"
            "</div>" % _ICON_PLAN, unsafe_allow_html=True)
    with step3:
        st.markdown(
            '<div class="hp-step">%s'
            '<div class="hp-step-title">Render or download</div>'
            '<p class="hp-step-text">Colored render or DXF file</p>'
            "</div>" % _ICON_RENDER, unsafe_allow_html=True)
