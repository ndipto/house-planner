# app.py
# House Planner web page (Day 2: brief -> room program -> floor plan).
#
# Run it with: streamlit run app.py
# Then open the local address Streamlit prints (usually http://localhost:8501).

import streamlit as st

import re

from ai_program import format_ft_in, get_api_key, get_room_program
from draw import svg_plan, svg_plot_preview
from layout import _closest_road
from plan_render import render_plan_checked
from typology import build_options
from voice import transcribe_audio


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

# --- Page title and short intro ---
st.title("House Planner")
st.write("A concept house planner for Bangladesh, built with an "
         "architect's rules.")
st.warning("Concept only - not for construction; consult a licensed "
           "architect.")
if st.button("Try an example"):
    st.session_state["in_frontage"] = 40
    st.session_state["in_depth"] = 60
    st.session_state["in_north"] = 180
    st.session_state["in_bedrooms"] = 3
    st.session_state["in_toilets"] = "3"
    st.rerun()

# --- Input form: plot + bedrooms + toilets + wishes ---
# Keep every input simple; plot numbers are in feet. The live preview
# beside the inputs redraws on every change (Streamlit reruns).
input_col, preview_col = st.columns([1, 1])
with input_col:
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
    voice_note = st.audio_input("Speak your brief (optional, Bangla or English)")
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
with preview_col:
    st.markdown(svg_plot_preview(frontage_ft, depth_ft, north_angle),
                unsafe_allow_html=True)

_signature = _brief_signature(frontage_ft, depth_ft, north_angle,
                              num_bedrooms, toilets_text, wishes)
if _results_stale(st.session_state, _signature):
    _clear_results(st.session_state)

# --- Button: ask the AI, then show results ---
if st.button("Generate plans"):
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

if _has_results(st.session_state):
    result = st.session_state["result_program"]
    options_result = st.session_state["result_options"]
    # 1. Rooms as a table (sizes in feet and inches).
    st.subheader("Rooms")
    rooms = result["rooms"]
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

    # 6. Floor plan options: place rooms (plain Python), draw each SVG.
    st.subheader("Floor plan options")
    options = options_result["options"]
    with st.expander("Technical notes"):
        for item in options_result["notes"]:
            st.write("- " + item)
    if not options:
        st.warning("No option fits this plot; try a bigger plot or fewer rooms.")
        st.stop()
    plot = options_result["plot"]
    st.write(
        "Here are %d layout option(s) for your brief. 'Needs review' "
        "means an architect should take a second look - the reason "
        "is shown under that option." % len(options)
    )
    columns = st.columns(len(options))
    for column, opt in zip(columns, options):
        with column:
            st.markdown("### Option %s" % opt["label"])
            st.write(_plain_title(opt))
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
            cache = st.session_state.setdefault("plan_renders", {})
            notes = st.session_state.setdefault("plan_render_notes",
                                                {})
            extra = st.text_input(
                "Extra instructions for the render (e.g. marble tiles "
                "in living, bed against the north wall, plants on "
                "verandas)",
                key="extra_%s" % opt["label"])
            plan_key = "%s|%s|%d|%d" % (
                opt["label"], opt["title"],
                hash(repr(opt["placements"])), hash(extra or ""))
            if plan_key in cache:
                want_render = st.button(
                    "Regenerate", key="regen_%s" % opt["label"])
            else:
                want_render = st.button(
                    "Render this plan",
                    key="render_%s" % opt["label"])
            if want_render:
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
            if plan_key in cache:
                left, right = st.columns(2)
                with left:
                    st.markdown(_svg_for_option(plot, opt),
                                unsafe_allow_html=True)
                    st.caption("Your plan")
                with right:
                    st.image(
                        cache[plan_key],
                        caption="AI presentation render - check "
                                "against the plan")
                    if notes.get(plan_key):
                        st.caption(notes[plan_key])
            else:
                st.markdown(_svg_for_option(plot, opt),
                            unsafe_allow_html=True)

    if len(options) == 2:
        st.info("Two layouts fit this plot shape.")
    # 7. Per-option architect's checklist (plain names, no numbers).
    for opt in options:
        with st.expander("Option %s: Architect's checklist"
                         % opt["label"]):
            st.markdown(_svg_for_option(plot, opt), unsafe_allow_html=True)
            st.table(_checklist_rows(opt))
            if opt["wishes"]:
                st.table([
                    {"Your wish": row["wish"],
                     "Result": _WISH_RESULT.get(row["status"],
                                               row["status"])}
                    for row in opt["wishes"]
                ])
    st.caption("Concept only - not for construction; consult a licensed architect.")
