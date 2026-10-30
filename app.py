# app.py
# House Planner web page (Day 2: brief -> room program -> floor plan).
#
# Run it with: streamlit run app.py
# Then open the local address Streamlit prints (usually http://localhost:8501).

import streamlit as st

from ai_program import format_ft_in, get_room_program
from draw import svg_plan, svg_plot_preview
from layout import _closest_road
from render import exterior_prompt, generate_exterior
from typology import build_options


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
    verdict = "LIVABLE" if opt["livable"] else "UNLIVABLE"
    wishes = opt.get("wishes", [])
    met = sum(1 for row in wishes if row["status"] == "MET")
    fails = ", ".join(opt["livability_fails"]) or "none"
    return "%s - score %.0f, wishes %d/%d, hard fails: %s." % (
        verdict, opt["score"], met, len(wishes), fails)


def _show_error(friendly, err):
    """Friendly error for users; raw text hidden in an expander."""
    st.error(friendly)
    with st.expander("Technical details"):
        st.code("%s: %s" % (type(err).__name__, err))


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
    wishes = st.text_area(
        "Family needs and wishes (plain words)",
        placeholder="Example: home office, big kitchen for family gatherings, elderly parent on ground floor",
    )
with preview_col:
    st.markdown(svg_plot_preview(frontage_ft, depth_ft, north_angle),
                unsafe_allow_html=True)

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
    with st.spinner("Building three layout options..."):
        try:
            options_result = build_options(
                rooms, frontage_ft, depth_ft, road_side, num_toilets,
                wishes, north_angle,
            )
        except Exception as err:
            _show_error("Could not lay out the plan from this program.", err)
            st.stop()
    options = options_result["options"]
    for item in options_result["notes"]:
        st.write("- " + item)
    if not options:
        st.warning("No option fits this plot; try a bigger plot or fewer rooms.")
        st.stop()
    plot = options_result["plot"]
    tried = sum(opt["tried"] for opt in options)
    st.write(
        "Built %d option(s) (%d arrangements examined); scores rank them, "
        "higher is better. UNLIVABLE means rules 4, 5, 7, 13-16, 19 or "
        "geometry G fail."
        % (len(options), tried)
    )
    columns = st.columns(len(options))
    for column, opt in zip(columns, options):
        with column:
            st.markdown("### Option %s" % opt["label"])
            st.write(opt["title"])
            st.caption(_option_summary(opt))
            if opt["livable"]:
                st.success("LIVABLE")
            else:
                st.error("UNLIVABLE (%s)"
                         % ", ".join(opt["livability_fails"]))
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
