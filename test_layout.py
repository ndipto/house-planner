# test_layout.py
# Day 2 maintained check: layout engine + SVG drawing.
#
# No test framework needed, run from the repo root with:
#   python test_layout.py
# Prints PASS lines; any failure raises AssertionError (exit code 1).
#
# Covers the fixed Day 2 behaviors: the strict search finds a fully
# passing plan for the 40x60 demo (no relax fallback), geometry is
# independently clean (inside buildable, no overlaps), the SVG is
# well-formed with the ROAD label on the real side for all four road
# directions, and impossible plots return a best attempt with the
# failed rules listed (never a crash or an empty plan).

import xml.etree.ElementTree as ET

from ai_program import SIZE_RULES
from draw import svg_plan
# _check_all is private but it is the honest entry point for hand-made
# mini-plans (build_layout would run a full search instead).
from layout import _check_all, build_layout, livability_verdict


def _room(name, room_type, width, depth, veranda=False, kind="", attached=""):
    """One AI-shaped program room with the fields layout.py reads."""
    return {"name": name, "type": room_type, "width_ft": width,
            "depth_ft": depth, "adjacencies": [], "door_opens_into": "",
            "needs_veranda": veranda, "preferred_orientation": "",
            "features": [], "bathroom_kind": kind, "attached_to": attached}


PROGRAM_3BED = [
    _room("Porch", "porch", 8, 5),
    _room("Foyer", "foyer", 8, 10),
    _room("Living Room", "living room", 13, 14),
    _room("Dining", "dining", 11, 13),
    _room("Kitchen", "kitchen", 10, 13, veranda=True),
    _room("Family Living", "family living", 13, 14),
    _room("Bedroom 1", "bedroom", 13, 14, veranda=True),
    _room("Bedroom 2", "bedroom", 12, 13, veranda=True),
    _room("Bedroom 3", "bedroom", 11, 12),
    _room("Common Toilet", "bathroom", 7, 8, kind="common"),
    _room("Bath 1", "bathroom", 7, 8, kind="attached",
          attached="Bedroom 1"),
    _room("Bath 2", "bathroom", 7, 8, kind="attached",
          attached="Bedroom 2"),
]


def _overlap_1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _independent_errors(result):
    """Re-verify geometry from raw placements (not the checker's word)."""
    errors = []
    rects = result["placements"]
    build = result["buildable"]
    bx0, by0 = 1.5, 6.0  # buildable rect in plot-local coords
    bx1, by1 = bx0 + build["w"], by0 + build["d"]
    for rect in rects:
        if not (rect["x"] >= bx0 - 0.01 and rect["y"] >= by0 - 0.01
                and rect["x"] + rect["w"] <= bx1 + 0.01
                and rect["y"] + rect["d"] <= by1 + 0.01):
            errors.append("outside buildable: %s" % rect["name"])
        kind = rect["type"]
        if kind in SIZE_RULES:
            low, high = SIZE_RULES[kind]
            if not low - 1e-6 <= rect["w"] <= high + 1e-6:
                errors.append("width out of range: %s" % rect["name"])
            if not low - 1e-6 <= rect["d"] <= high + 1e-6:
                errors.append("depth out of range: %s" % rect["name"])
            if abs(rect["w"] - rect["d"]) < 1 - 1e-6:
                errors.append("square-ish: %s" % rect["name"])
    for i, first in enumerate(rects):
        for second in rects[i + 1:]:
            area = (_overlap_1d(first["x"], first["x"] + first["w"],
                                 second["x"], second["x"] + second["w"])
                    * _overlap_1d(first["y"], first["y"] + first["d"],
                                  second["y"], second["y"] + second["d"]))
            if area > 0.01:
                errors.append("overlap: %s x %s"
                              % (first["name"], second["name"]))
    return errors


def _rule_status(result, rule_id):
    for row in result["rules"]:
        if row["id"] == rule_id:
            return row["status"]
    return "?"


_DEMO = None


def _demo_result():
    """Demo plan, built once and shared (the search takes seconds)."""
    global _DEMO
    if _DEMO is None:
        _DEMO = build_layout(PROGRAM_3BED, 40, 60, "South", 3)
    return _DEMO


def test_demo_case():
    """40x60, road South, 3 bed, 3 toilet: strict plan, all rules pass."""
    result = _demo_result()
    assert result["ok"], "demo plan should build"
    assert not result["truncated"], "demo search should finish in cap"
    assert result["candidates_tried"] > 10, "should try many candidates"
    for rule_id in ("1", "2", "3", "7", "8", "10", "G"):
        assert _rule_status(result, rule_id) == "PASS", \
            "demo rule %s should PASS" % rule_id
    assert _independent_errors(result) == [], "demo geometry must be clean"
    print("PASS test_demo_case (%d candidates, %.1fs)"
          % (result["candidates_tried"], result["seconds"]))


def test_svg_rotation():
    """ROAD label lands on the real side for all four road directions."""
    rooms = [{"name": "Room A", "type": "bedroom", "x": 5, "y": 10,
              "w": 12, "d": 14},
             {"name": "Room B", "type": "kitchen", "x": 20, "y": 10,
              "w": 10, "d": 13}]
    for road, plot_w, plot_d in (("south", 40, 60), ("north", 40, 60),
                                 ("east", 60, 40), ("west", 60, 40)):
        fake = {"ok": True, "placements": rooms,
                "plot": {"w": plot_w, "d": plot_d, "road": road}}
        root = ET.fromstring(svg_plan(fake))  # must be well-formed XML
        ns = "{http://www.w3.org/2000/svg}"
        plot = root.find("%srect[@stroke-width='3']" % ns)
        px = (float(plot.get("x")), float(plot.get("y")),
              float(plot.get("width")), float(plot.get("height")))
        road_label = [t for t in root.iter("%stext" % ns)
                      if (t.text or "") == "ROAD"]
        assert len(road_label) == 1, "one ROAD label for %s" % road
        lx, ly = float(road_label[0].get("x")), float(road_label[0].get("y"))
        if road == "south":
            assert ly > px[1] + px[3], "ROAD below plot for south"
        elif road == "north":
            assert ly < px[1], "ROAD above plot for north"
        elif road == "east":
            assert lx > px[0] + px[2], "ROAD right of plot for east"
        else:
            assert lx < px[0], "ROAD left of plot for west"
        for rect in root.iter("%srect" % ns):
            if rect.get("fill") == "#fff" and rect.get("stroke-width") == "1.6":
                rx, ry = float(rect.get("x")), float(rect.get("y"))
                assert px[0] - 1 <= rx <= px[0] + px[2] + 1, \
                    "room inside plot x for %s" % road
                assert px[1] - 1 <= ry <= px[1] + px[3] + 1, \
                    "room inside plot y for %s" % road
    print("PASS test_svg_rotation (ROAD on the real side x4)")


def test_impossible_plot():
    """Tiny plot: best attempt returned, failures listed, nothing crashes."""
    result = build_layout(PROGRAM_3BED, 20, 20, "South", 3)
    assert result["ok"], "best attempt should still build"
    assert result["rules"], "failed rules must be listed"
    assert _rule_status(result, "G") == "FAIL", "geometry must fail honestly"
    ET.fromstring(svg_plan(result))
    print("PASS test_impossible_plot (best attempt + failed rules)")


def test_one_bedroom():
    """1 bed + 1 toilet: common toilet placed on common space."""
    small = [r for r in PROGRAM_3BED if r["name"] in (
        "Porch", "Foyer", "Living Room", "Dining", "Kitchen",
        "Family Living", "Bedroom 1", "Common Toilet")]
    result = build_layout(small, 30, 40, "North", 1)
    assert result["ok"], "small plan should build"
    assert _rule_status(result, "7") == "PASS", "toilet rule should pass"
    ET.fromstring(svg_plan(result))
    print("PASS test_one_bedroom (common toilet on common space)")


def test_livability_verdict():
    """Demo plan is UNLIVABLE until placer strategies land (pinned)."""
    result = _demo_result()
    assert result["livable"] is False, "demo should be UNLIVABLE for now"
    assert result["livability_fails"] == ["13", "14", "16"], \
        "demo should fail kitchen walls, bedroom walls, circulation"
    assert _rule_status(result, "13") == "FAIL", "kitchen has 3.5 ft, needs 6"
    assert _rule_status(result, "14") == "FAIL", "Bedroom 2 has 4.5 ft, needs 6"
    assert _rule_status(result, "15") == "PASS", "toilets are exterior"
    assert _rule_status(result, "16") == "FAIL", "routes cross kitchen/bedroom"
    print("PASS test_livability_verdict (UNLIVABLE on 13, 14, 16)")


def _mrect(name, room_type, x, y, width, depth, kind="", veranda_for=""):
    """One hand-placed rect with the fields the checker reads."""
    return {"name": name, "type": room_type, "x": x, "y": y,
            "w": width, "d": depth, "bathroom_kind": kind,
            "attached_to": "", "needs_veranda": False,
            "veranda_for": veranda_for}


def _mini_rules(rects):
    """Rule rows for a hand-made mini-plan (no search)."""
    info = {"row_front_y": 0, "row_widths": [30], "house_back": 30}
    rules, _goals, _quality = _check_all(rects, info, 40, 50, "south", 1,
                                         livability=True)
    return rules


def test_circulation_pass_branch():
    """Hand-made plan where every route keeps to common rooms."""
    rects = [
        _mrect("Foyer", "foyer", 0, 10, 10, 10),
        _mrect("Dining", "dining", 10, 10, 10, 10),
        _mrect("Kitchen", "kitchen", 20, 10, 8, 10),
        _mrect("Kitchen veranda", "veranda", 28, 10, 4, 6,
               veranda_for="Kitchen"),
        _mrect("Bedroom", "bedroom", 10, 20, 12, 10),
        _mrect("Common", "bathroom", 2, 20, 8, 8, kind="common"),
    ]
    by_id = {row["id"]: row for row in _mini_rules(rects)}
    assert by_id["13"]["status"] == "PASS", "kitchen has 10 ft exterior + veranda"
    assert by_id["14"]["status"] == "PASS", "bedroom has 10 ft window wall"
    assert by_id["15"]["status"] == "PASS", "common toilet exterior"
    assert by_id["16"]["status"] == "PASS", "all routes via common rooms"
    assert livability_verdict(list(by_id.values())) == (True, [])
    print("PASS test_circulation_pass_branch (mini-plan LIVABLE)")


def test_circulation_kitchen_trap():
    """Hand-made plan where the bedroom route must cross the kitchen."""
    rects = [
        _mrect("Bedroom", "bedroom", 20, 0, 10, 10),
        _mrect("Kitchen", "kitchen", 10, 0, 10, 10),
        _mrect("Common", "bathroom", 3, 0, 7, 10, kind="common"),
        _mrect("Foyer", "foyer", 3, 10, 10, 8),
    ]
    by_id = {row["id"]: row for row in _mini_rules(rects)}
    assert by_id["13"]["status"] == "FAIL", "kitchen has no veranda"
    assert by_id["16"]["status"] == "FAIL", "bedroom route crosses kitchen"
    assert "KITCHEN" in by_id["16"]["detail"], "report must name the crossing"
    assert livability_verdict(list(by_id.values()))[0] is False
    print("PASS test_circulation_kitchen_trap (UNLIVABLE, crossing named)")


if __name__ == "__main__":
    test_demo_case()
    test_svg_rotation()
    test_impossible_plot()
    test_one_bedroom()
    test_livability_verdict()
    test_circulation_pass_branch()
    test_circulation_kitchen_trap()
    print("ALL LAYOUT TESTS PASSED")
