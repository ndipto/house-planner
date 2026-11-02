# app.py
# House Planner web page (Day 2: brief -> room program -> floor plan).
#
# Run it with: streamlit run app.py
# Then open the local address Streamlit prints (usually http://localhost:8501).

import logging
import os
import re

import streamlit as st

st.set_page_config(layout="wide", page_title="House Planner",
                   page_icon="🏠")

logger = logging.getLogger("house_planner")

from ai_program import format_ft_in, get_api_key, get_room_program
from draw import svg_plan, svg_plot_preview
from dxf_export import dxf_plan
from layout import _closest_road
from plan_render import render_plan_checked
from typology import build_options
from voice import transcribe_audio


# --- Demo look: one CSS block for the whole page ---
# DM Serif Display for headings, Inter for everything else; bronze
# (#8A5A3B) accents on dark (#2B2B2B). Purely visual: if Streamlit
# ever renames a selector below, the page just falls back to its
# default look instead of breaking.
_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Inter:wght@400;500;600;700&display=swap');

[data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}
h1, h2, h3 {
    font-family: 'DM Serif Display', Georgia, serif !important;
}

/* Dark header band with a thin bronze accent line. */
[data-testid="stMainBlockContainer"] { padding-top: 1rem; }
.hp-band {
    background: #2B2B2B;
    border-bottom: 3px solid #8A5A3B;
    border-radius: 0 0 14px 14px;
    margin: -1rem -2rem 1.6rem -2rem;
    padding: 2.2rem 2rem 1.6rem 2rem;
}
.hp-band h1 {
    font-size: 2.7rem; font-weight: 400; color: #FAF8F5;
    margin: 0; line-height: 1.1;
}
.hp-band p { color: #D8D0C4; font-size: 1.02rem; margin: .45rem 0 0 0; }
.hp-band .hp-concept { font-size: .8rem; color: #A79E90; margin-top: .5rem; }

/* Start-screen step cards + example plan. */
.hp-step {
    background: #FFFFFF; border: 1px solid #EAE4DA; border-radius: 14px;
    padding: 1.4rem 1.1rem; text-align: center;
    box-shadow: 0 6px 22px rgba(43, 43, 43, .08);
}
.hp-step-title {
    font-weight: 700; font-size: 1.05rem; color: #2B2B2B;
    margin: .6rem 0 .25rem 0;
}
.hp-step-text { color: #6B6560; font-size: .9rem; margin: 0; }
.hp-example {
    background: #FFFFFF; border: 1px solid #EAE4DA; border-radius: 14px;
    padding: 1.2rem; box-shadow: 0 6px 22px rgba(43, 43, 43, .08);
    margin-top: 1.4rem;
}
.hp-example svg { width: 100%; height: auto; display: block; }
.hp-caption {
    text-align: center; color: #6B6560; font-size: .85rem;
    margin: .5rem 0 0 0;
}

/* Result cards: the plan and its side panel. */
[data-testid="stTabContent"] div[data-testid="column"] {
    background: #FFFFFF; border: 1px solid #EAE4DA; border-radius: 14px;
    padding: 1.4rem; box-shadow: 0 6px 22px rgba(43, 43, 43, .10);
}
.hp-option-title {
    font-size: 1.35rem; font-weight: 700; color: #2B2B2B;
    margin: 0 0 .5rem 0;
}

/* Bronze filled primary buttons; outlined DXF download. */
[data-testid="stBaseButton-primary"] {
    background-color: #8A5A3B; border-color: #8A5A3B;
}
[data-testid="stBaseButton-primary"]:hover {
    background-color: #74492F; border-color: #74492F;
}
div[data-testid="stDownloadButton"] button {
    border: 1px solid #8A5A3B; color: #8A5A3B; background: transparent;
}
div[data-testid="stDownloadButton"] button:hover {
    border-color: #8A5A3B; color: #74492F;
    background: rgba(138, 90, 59, .08);
}

/* Selected option tab in bronze with a bold label. */
button[data-testid="stTab"][aria-selected="true"] {
    color: #8A5A3B; font-weight: 700;
    background: rgba(138, 90, 59, .10); border-radius: 8px 8px 0 0;
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
              'stroke="#8A5A3B" stroke-width="1.8" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M3 11 12 4l9 7"/>'
              '<path d="M5 10v10h14V10"/><path d="M10 20v-5h4v5"/></svg>')
_ICON_PLAN = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
              'stroke="#8A5A3B" stroke-width="1.8" stroke-linecap="round" '
              'stroke-linejoin="round"><rect x="4" y="4" width="16" '
              'height="16" rx="1"/><path d="M4 12h16M12 12v8"/></svg>')
_ICON_RENDER = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" '
                'stroke="#8A5A3B" stroke-width="1.8" stroke-linecap="round" '
                'stroke-linejoin="round"><path d="M12 4v11"/>'
                '<path d="M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>')


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


def _brief_signature(frontage_ft, depth_ft, north_angle, num_bedrooms,
                     toilets_text, wishes):
    """Fingerprint of the current brief; any input change alters it."""
    return (float(frontage_ft), float(depth_ft), float(north_angle),
            int(num_bedrooms), str(toilets_text).strip(),
            str(wishes or ""))


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

# --- Header band: dark, full-width, serif title (always visible) ---
st.markdown(_STYLE, unsafe_allow_html=True)
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
        st.session_state["in_frontage"] = 40
        st.session_state["in_depth"] = 60
        st.session_state["in_north"] = 180
        st.session_state["in_bedrooms"] = 3
        st.session_state["in_toilets"] = "3"
        st.rerun()
    st.subheader("Plot")
    frontage_ft = st.number_input("Road frontage (ft)", min_value=10, value=40, key="in_frontage")
    depth_ft = st.number_input("Plot depth from road (ft)", min_value=10, value=60, key="in_depth")
    north_angle = st.slider(
        "North direction (degrees)",
        min_value=0, max_value=360, value=0, key="in_north",
        help="Drag until the north arrow matches your plot: 0 = north "
             "points away from the road (road on the south side).",
    )
    road_side = _closest_road(north_angle)
    st.caption("Road on the %s side." % road_side.capitalize())
    st.markdown(svg_plot_preview(frontage_ft, depth_ft, north_angle),
                unsafe_allow_html=True)
    st.divider()
    st.subheader("Family")
    num_bedrooms = st.number_input("Number of bedrooms", min_value=1,
                                   max_value=10, value=3, key="in_bedrooms")
    # Toilets: NO default on purpose. The field starts empty and the
    # client must fill it (number_input can't do that, so this is text).
    max_toilets = num_bedrooms + 1
    toilets_text = st.text_input(
        "Number of toilets",
        value="", key="in_toilets",
        placeholder=f"Required: whole number from 1 to {max_toilets}",
    )
    st.divider()
    st.subheader("Wishes")
    voice_note = st.audio_input("Speak your brief (optional)")
    if voice_note is not None:
        # New recording only: transcribe once, then fill the wishes box
        # below (set before the widget exists, so no rerun warning).
        heard = voice_note.getvalue()
        if st.session_state.get("voice_digest") != hash(heard):
            with st.spinner("Listening to your recording..."):
                try:
                    said = transcribe_audio(heard)
                except Exception as err:
                    _show_error("Could not transcribe this recording.", err)
                    said = ""
            st.session_state["voice_digest"] = hash(heard)
            if said:
                st.session_state["in_wishes"] = said
                st.rerun()
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
    # Toilets are required: stop with a clear message when empty/invalid.
    if not toilets_text.strip():
        st.error("Please enter the number of toilets (1 to %d) before generating." % max_toilets)
        st.stop()
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
    with st.spinner("Reading your brief and shaping the rooms..."):
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
                        with st.spinner("Making a presentation render of "
                                        "this plan..."):
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
                st.download_button(
                    "Download DXF",
                    data=_dxf_for_option(plot, opt),
                    file_name="house_plan_option_%s.dxf" % opt["label"],
                    mime="image/vnd.dxf",
                    key="dxf_%s" % opt["label"],
                    use_container_width=True)
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
    st.caption("Concept only - not for construction; consult a licensed architect.")
else:
    # Before generating: three clean step cards + one example plan.
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
