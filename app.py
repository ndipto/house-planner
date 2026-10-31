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
from render import exterior_prompt, generate_exterior
from typology import build_options
from voice import transcribe_audio


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
        toilet_use = ""
        if str(room.get("type", "")).strip().lower() == "bathroom":
            kind = str(room.get("bathroom_kind", "")).strip() or "?"
            target = str(room.get("attached_to", "")).strip()
            toilet_use = kind if not target else f"{kind} ({target})"
        rows.append({
            "Name": room.get("name", "?"),
            "Type": room.get("type", "?"),
            "Width": format_ft_in(width),
            "Depth": format_ft_in(depth),
            "Area": area_text,
            "Door into": room.get("door_opens_into", "?"),
            "Veranda": "yes" if room.get("needs_veranda") else "no",
            "Toilet use": toilet_use,
            "Features": ", ".join(features),
        })
    return rows


def _option_summary(opt):
    """One-line demo summary: verdict, score, wishes, hard fails."""
    verdict = "All key rules met" if opt["livable"] else "Needs review"
    wishes = opt.get("wishes", [])
    met = sum(1 for row in wishes if row["status"] == "MET")
    fails = ", ".join(opt["livability_fails"]) or "none"
    return "%s - score %.0f, wishes %d/%d, hard fails: %s." % (
        verdict, opt["score"], met, len(wishes), fails)


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
            with st.spinner("Transcribing your brief with Muse Voice..."):
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
if st.button("Generate room program"):
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
    with st.spinner("Asking Muse Spark for your room program..."):
        try:
            result = get_room_program(
                frontage_ft, depth_ft, road_side,
                int(num_bedrooms), num_toilets, wishes, north_angle,
            )
        except Exception as err:
            _show_error("Could not get a room program. Check your API key "
                        "and connection, then try again.", err)
            st.stop()
    rooms = result["rooms"]
    with st.spinner("Building three layout options..."):
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

    # 3. Program area vs. buildable area.
    st.subheader("Program area vs. buildable area")
    buildable = result["buildable"]
    area = result["program_area"]
    st.write(
        f"Buildable after setbacks: {buildable['area']:.0f} sq ft "
        f"({format_ft_in(buildable['width'])} x {format_ft_in(buildable['depth'])})."
    )
    st.write(
        f"Program: rooms {area['net']:.0f} + interior walls {area['interior_walls']:.0f} "
        f"+ exterior walls {area['exterior_walls']:.0f} = {area['total']:.0f} sq ft "
        f"(corridors {area['circulation']:.0f} sq ft of the rooms)."
    )
    if result["revised"] and not result["area_warning"]:
        st.info("The first draft was too big, so the AI shrank rooms to fit.")
    if result["area_warning"]:
        st.warning(result["area_warning"])
    else:
        st.success("The program fits inside the buildable area.")

    # 4. Size check results from plain Python.
    st.subheader("Size check")
    problems = result["size_problems"]
    if not problems:
        st.success("All room sizes pass our rules.")
    else:
        st.warning("Some rooms need attention:")
        for item in problems:
            st.write("- " + item)

    # 5. Toilet rule check (HARD rule).
    st.subheader("Toilet check")
    toilet_problems = result["toilet_problems"]
    if not toilet_problems:
        st.success("Toilet rule passes: exactly 1 common, rest attached largest-first.")
    else:
        st.warning("Toilet rule needs attention:")
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
    tried = sum(opt["tried"] for opt in options)
    st.write(
        "Built %d option(s) (%d arrangements examined); scores rank them, "
        "higher is better. 'Needs review' means a hard rule (4, 5, 7, "
        "13-16, 19, or geometry G) missed - see under each option."
        % (len(options), tried)
    )
    columns = st.columns(len(options))
    for column, opt in zip(columns, options):
        with column:
            st.markdown("### Option %s" % opt["label"])
            st.write(opt["title"])
            st.caption(_option_summary(opt))
            if opt["livable"]:
                st.success("All key rules met")
            else:
                st.warning("Needs review")
                for sentence in _friendly_issues(opt):
                    st.write(sentence)
            st.markdown(_svg_for_option(plot, opt), unsafe_allow_html=True)
            fails = [r["id"] for r in opt["rules"] if r["status"] == "FAIL"]
            bends = [r["id"] for r in opt["rules"] if r["status"] == "BEND"]
            st.write("Fail: %s; bend: %s."
                     % (", ".join(fails) if fails else "none",
                        ", ".join(bends) if bends else "none"))
            cache = st.session_state.setdefault("exteriors", {})
            plan_key = "%s|%s|%d" % (
                opt["label"], opt["title"],
                hash(repr(opt["placements"])))
            if plan_key in cache:
                st.image(cache[plan_key],
                         caption="Exterior concept (AI render)")
            if st.button("Generate exterior concept",
                         key="ext_%s" % opt["label"]):
                prompt = exterior_prompt(plot, opt)
                with st.spinner(
                        "Rendering the exterior with Muse Image..."):
                    try:
                        png = generate_exterior(prompt)
                    except Exception as err:
                        _show_error("Could not render this view.", err)
                    else:
                        cache[plan_key] = png
                        st.image(png,
                                 caption="Exterior concept (AI render)")

    if len(options) == 2:
        st.info("Two layouts fit this plot shape.")
    # 7. Per-option detail (plans show solid walls, doors, windows).
    for opt in options:
        with st.expander("Option %s details: %s"
                         % (opt["label"], opt["title"])):
            st.markdown(_svg_for_option(plot, opt), unsafe_allow_html=True)
            st.table([
                {"Rule": "%s. %s" % (row["id"], row["name"]),
                 "Result": row["status"],
                 "Detail": row["detail"]}
                for row in opt["rules"]
            ])
            st.table([
                {"Goal": row["name"], "Result": row["status"],
                 "Detail": row["detail"]}
                for row in opt["goals"]
            ])
            if opt["wishes"]:
                st.table([
                    {"Client wish": row["wish"], "Result": row["status"]}
                    for row in opt["wishes"]
                ])
            if opt["relaxed"]:
                st.write("Relaxed sizes: %s." % ", ".join(opt["relaxed"]))
            for item in opt["notes"]:
                st.write("- " + item)
    st.caption("Concept only - not for construction; consult a licensed architect.")
