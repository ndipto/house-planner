# app.py
# House Planner web page (Day 2: brief -> room program -> floor plan).
#
# Run it with: streamlit run app.py
# Then open the local address Streamlit prints (usually http://localhost:8501).

import streamlit as st

from ai_program import format_ft_in, get_room_program
from draw import svg_plan
from layout import build_layout


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


# --- Page title and short intro ---
st.title("House Planner")
st.write(
    "Describe the house you want. The app asks Muse Spark for a room "
    "program, places the rooms on your plot, and draws a concept floor plan."
)

# --- Input form: plot + bedrooms + toilets + wishes ---
# Keep every input simple; plot numbers are in feet.
plot_width = st.number_input("Plot width (ft)", min_value=10, value=40)
plot_depth = st.number_input("Plot depth (ft)", min_value=10, value=60)
road_side = st.selectbox("Which side faces the road?", ["North", "South", "East", "West"])
num_bedrooms = st.number_input("Number of bedrooms", min_value=1, max_value=10, value=3)
# Toilets: NO default on purpose. The field starts empty and the
# client must fill it (number_input can't do that, so this is text).
max_toilets = num_bedrooms + 1
toilets_text = st.text_input(
    "Number of toilets",
    value="",
    placeholder=f"Required: whole number from 1 to {max_toilets}",
)
wishes = st.text_area(
    "Family needs and wishes (plain words)",
    placeholder="Example: home office, big kitchen for family gatherings, elderly parent on ground floor",
)

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
                plot_width, plot_depth, road_side,
                int(num_bedrooms), num_toilets, wishes,
            )
        except Exception as err:
            # Friendly error: most often a missing .env key or no internet.
            st.error(str(err))
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

    # 6. Floor plan: place rooms (plain Python), draw the SVG, list rules.
    st.subheader("Floor plan")
    with st.spinner("Trying candidate layouts and drawing the best plan..."):
        try:
            plan = build_layout(
                rooms, plot_width, plot_depth, road_side, num_toilets,
            )
        except Exception as err:
            st.error("Could not lay out the plan: %s" % err)
            st.stop()
    st.write(
        "Tried %d candidate layout(s) in %.1f seconds; showing the best one."
        % (plan["candidates_tried"], plan["seconds"])
    )
    if not plan["ok"]:
        st.warning("No full plan fits this plot; showing the best attempt below.")
    if plan.get("livable", True):
        st.success("LIVABLE: passes livability checks 13-16.")
    else:
        st.error("UNLIVABLE: fails livability checks %s (see rules 13-17 below)."
                 % ", ".join(plan.get("livability_fails", ["?"])))
    st.markdown(svg_plan(plan), unsafe_allow_html=True)

    # 7. Hard-rule check for the drawn plan (doors/windows arrive Day 3).
    st.subheader("Plan rule check")
    if plan["rules"]:
        st.table([
            {"Rule": "%s. %s" % (row["id"], row["name"]),
             "Result": row["status"],
             "Detail": row["detail"]}
            for row in plan["rules"]
        ])
    else:
        st.warning("No plan to check.")

    # 8. Design goals (soft) + placer notes.
    st.subheader("Design goals")
    if plan["goals"]:
        st.table([
            {"Goal": row["name"], "Result": row["status"], "Detail": row["detail"]}
            for row in plan["goals"]
        ])
    if plan["notes"]:
        st.subheader("Placer notes")
        for item in plan["notes"]:
            st.write("- " + item)
