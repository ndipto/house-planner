# app.py
# House Planner web page (Day 1: brief -> room program).
#
# Run it with: streamlit run app.py
# Then open the local address Streamlit prints (usually http://localhost:8501).

import streamlit as st

from ai_program import get_room_program


# --- Page title and short intro ---
st.title("House Planner")
st.write(
    "Describe the house you want. The app asks Muse Spark for a room "
    "program and checks every room size against our design rules."
)

# --- Input form: plot + bedrooms + wishes ---
# Keep every input simple; numbers are in feet.
plot_width = st.number_input("Plot width (ft)", min_value=10, value=40)
plot_depth = st.number_input("Plot depth (ft)", min_value=10, value=60)
road_side = st.selectbox("Which side faces the road?", ["North", "South", "East", "West"])
num_bedrooms = st.number_input("Number of bedrooms", min_value=1, max_value=10, value=3)
wishes = st.text_area(
    "Family needs and wishes (plain words)",
    placeholder="Example: home office, big kitchen for family gatherings, elderly parent on ground floor",
)

# --- Button: ask the AI, then show results ---
if st.button("Generate room program"):
    # While waiting, show a spinner so the page does not look frozen.
    with st.spinner("Asking Muse Spark for your room program..."):
        try:
            result = get_room_program(
                plot_width, plot_depth, road_side, num_bedrooms, wishes
            )
        except Exception as err:
            # Friendly error: most often a missing .env key or no internet.
            st.error(str(err))
            st.stop()

    # 1. Rooms as a table.
    st.subheader("Rooms")
    rooms = result["rooms"]
    if rooms:
        st.table(rooms)
    else:
        st.warning("The AI returned no rooms. Try again with simpler wishes.")

    # 2. Design explanation in the architect's voice.
    st.subheader("Design explanation")
    st.write(result["design_explanation"] or "No explanation returned.")

    # 3. Size check results from plain Python.
    st.subheader("Size check")
    problems = result["size_problems"]
    if not problems:
        st.success("All room sizes pass our rules.")
    else:
        st.warning("Some rooms need attention:")
        for item in problems:
            st.write("- " + item)
