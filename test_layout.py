# test_layout.py
# Day 2 typology tests: three options (A/B/C) per brief, checked + scored.
#
# Run them with: python test_layout.py
# Every test pins honest behavior: livable options, known bends, and the
# briefs the typologies cannot satisfy (reported, never hidden).

import xml.etree.ElementTree as ET

from ai_program import (
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    SIZE_RULES,
)
from draw import svg_plan
from layout import RELAXED_RANGES, _check_all, livability_verdict
from typology import build_options


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

PROGRAM_1BED = [
    _room("Porch", "porch", 8, 5),
    _room("Foyer", "foyer", 8, 10),
    _room("Living Room", "living room", 13, 14),
    _room("Dining", "dining", 11, 13),
    _room("Kitchen", "kitchen", 10, 13, veranda=True),
    _room("Family Living", "family living", 13, 14),
    _room("Bedroom 1", "bedroom", 12, 13, veranda=True),
    _room("Common Toilet", "bathroom", 7, 8, kind="common"),
]


def _overlap_1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _independent_errors(placements, buildable):
    """Re-verify geometry from raw placements (not the checker's word)."""
    errors = []
    bx0, by0 = SETBACK_SIDE_FT, SETBACK_FRONT_FT  # buildable in plot coords
    bx1 = bx0 + buildable["width"]
    by1 = by0 + buildable["depth"]
    for rect in placements:
        if not (rect["x"] >= bx0 - 0.01 and rect["y"] >= by0 - 0.01
                and rect["x"] + rect["w"] <= bx1 + 0.01
                and rect["y"] + rect["d"] <= by1 + 0.01):
            errors.append("outside buildable: %s" % rect["name"])
        kind = rect["type"]
        if kind in SIZE_RULES:
            low, high = SIZE_RULES[kind]
            relaxed = RELAXED_RANGES.get(kind)
            for side, label in ((rect["w"], "width"), (rect["d"], "depth")):
                if low - 1e-6 <= side <= high + 1e-6:
                    continue
                if relaxed is not None and relaxed[0] - 1e-6 <= side \
                        <= relaxed[1] + 1e-6:
                    continue  # legal bend (rule 1 reports it)
                errors.append("%s out of range: %s" % (label, rect["name"]))
            if abs(rect["w"] - rect["d"]) < 1 - 1e-6:
                errors.append("square-ish: %s" % rect["name"])
    for i, first in enumerate(placements):
        for second in placements[i + 1:]:
            area = (_overlap_1d(first["x"], first["x"] + first["w"],
                                 second["x"], second["x"] + second["w"])
                    * _overlap_1d(first["y"], first["y"] + first["d"],
                                  second["y"], second["y"] + second["d"]))
            if area > 0.01:
                errors.append("overlap: %s x %s"
                              % (first["name"], second["name"]))
        for dim in ("x", "y", "w", "d"):
            doubled = round(first[dim] * 2)
            assert abs(first[dim] * 2 - doubled) < 0.01, \
                "6-inch rounding: %s %s" % (first["name"], dim)
    return errors


def _rule_status(option, rule_id):
    for row in option["rules"]:
        if row["id"] == rule_id:
            return row["status"]
    return "?"


def _svg_for(option, plot):
    """Adapt one option to the svg_plan() plan shape (mirrors the app)."""
    return {"ok": True, "placements": option["placements"],
            "plot": {"w": plot["width"], "d": plot["depth"],
                     "road": plot["road"]}}


def _center_x(placements, name):
    for rect in placements:
        if rect["name"] == name:
            return rect["x"] + rect["w"] / 2
    raise AssertionError("missing room %s" % name)


def _footprint(option):
    """Sorted room boxes: two options with equal footprints are identical."""
    return sorted((r["name"], r["x"], r["y"], r["w"], r["d"])
                  for r in option["placements"])


def test_typology_options():
    """40x60, road North, 3 bed, 3 toilet: 3 livable, different options."""
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    options = result["options"]
    assert [o["label"] for o in options] == ["A", "B", "C"]
    assert all(o["tried"] > 0 for o in options), "each option tries layouts"
    by_label = {o["label"]: o for o in options}
    # Kitchen sides mirror (road North: compass west is high x).
    assert _center_x(by_label["A"]["placements"], "Kitchen") > 20
    assert _center_x(by_label["B"]["placements"], "Kitchen") < 20
    assert _center_x(by_label["C"]["placements"], "Kitchen") > 20
    # Master (largest bedroom) takes a different back corner per option.
    assert _center_x(by_label["A"]["placements"], "Bedroom 1") < 20
    assert _center_x(by_label["B"]["placements"], "Bedroom 1") > 20
    assert _center_x(by_label["C"]["placements"], "Bedroom 1") > 20
    # Genuinely different plans, each fully checked.
    feet = [_footprint(o) for o in options]
    assert feet[0] != feet[1] and feet[0] != feet[2] \
        and feet[1] != feet[2], "options must differ"
    for opt in options:
        ids = [r["id"] for r in opt["rules"]]
        for wanted in ("13", "14", "15", "16", "17"):
            assert wanted in ids, "option %s lists rule %s" % (opt["label"],
                                                               wanted)
        assert _independent_errors(opt["placements"],
                                   result["buildable"]) == [], \
            "option %s geometry must be clean" % opt["label"]
        ET.fromstring(svg_plan(_svg_for(opt, result["plot"])))
    assert by_label["A"]["livable"] is True, "A livable, kitchen west"
    assert by_label["A"]["livability_fails"] == []
    assert by_label["B"]["livable"] is True, "B livable, mirrored"
    assert _rule_status(by_label["B"], "13") == "BEND", "B misses west"
    assert by_label["C"]["livable"] is True, "C livable, third variant"
    print("PASS test_typology_options (A/B/C livable, B bends 13)")


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
    """Tiny plot: no options, honest note, nothing crashes."""
    result = build_options(PROGRAM_3BED, 10, 10, "South", 3)
    assert result["options"] == [], "no option fits a 10x10 plot"
    assert result["notes"], "the reason must be noted"
    print("PASS test_impossible_plot (no options + note)")


def test_one_bedroom():
    """1 bed + 1 toilet: livable options, common toilet on common space."""
    result = build_options(PROGRAM_1BED, 40, 60, "South", 1)
    options = result["options"]
    assert len(options) == 3, "1-bed brief still gets 3 options"
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "7") == "PASS", "toilet rule passes"
        assert _independent_errors(opt["placements"],
                                   result["buildable"]) == []
        ET.fromstring(svg_plan(_svg_for(opt, result["plot"])))
    by_label = {o["label"]: o for o in options}
    assert [r["id"] for r in by_label["A"]["rules"]
            if r["status"] == "FAIL"] == ["10"], \
        "corner bedroom has no free veranda wall at this width (rule 10)"
    print("PASS test_one_bedroom (3 livable, rule 10 honest)")


def test_narrow_two_strip():
    """Buildable under 30 ft: two-strip options; 1-bed works via option C."""
    one = build_options(PROGRAM_1BED, 25, 60, "North", 1)
    assert [o["typology"] for o in one["options"]] == ["two-strip"] * 3
    by_label = {o["label"]: o for o in one["options"]}
    assert by_label["C"]["livable"] is True, "alt order saves 1-bed narrow"
    assert by_label["A"]["livable"] is False, "kitchen has no veranda wall"
    assert "13" in by_label["A"]["livability_fails"]
    assert _footprint(by_label["A"]) != _footprint(by_label["C"])
    two_bed = list(PROGRAM_1BED) + [
        _room("Bedroom 2", "bedroom", 11, 12),
        _room("Bath 1", "bathroom", 7, 8, kind="attached",
              attached="Bedroom 1"),
    ]
    two = build_options(two_bed, 25, 60, "North", 2)
    for opt in two["options"]:
        # Five side slots overconstrain one strip: honest UNLIVABLE.
        assert opt["livable"] is False, "narrow 2-bed cannot all fit"
        assert "13" in opt["livability_fails"], "kitchen keeps no veranda"
        assert _independent_errors(opt["placements"],
                                   two["buildable"]) == []
    print("PASS test_narrow_two_strip (1-bed via C, 2-bed honest)")


def test_l_shape_wide():
    """Buildable 45 ft+: option C is an L-shape with court, fully green."""
    result = build_options(PROGRAM_1BED, 55, 60, "South", 1)
    by_label = {o["label"]: o for o in result["options"]}
    assert by_label["C"]["typology"] == "l-shape", "wide plot gets the L"
    assert by_label["C"]["livable"] is True
    assert [r["id"] for r in by_label["C"]["rules"]
            if r["status"] == "FAIL"] == [], "L has zero fails"
    assert by_label["A"]["livable"] is True
    assert [r["id"] for r in by_label["A"]["rules"]
            if r["status"] == "FAIL"] == [], "A has zero fails"
    for opt in result["options"]:
        assert _independent_errors(opt["placements"],
                                   result["buildable"]) == []
    ET.fromstring(svg_plan(_svg_for(by_label["C"], result["plot"])))
    print("PASS test_l_shape_wide (L green, A green)")


def _mrect(name, room_type, x, y, width, depth, kind="", veranda_for=""):
    """One hand-placed rect with the fields the checker reads."""
    return {"name": name, "type": room_type, "x": x, "y": y,
            "w": width, "d": depth, "bathroom_kind": kind,
            "attached_to": "", "needs_veranda": False,
            "veranda_for": veranda_for}


def _mini_rules(rects):
    """Rule rows for a hand-made mini-plan (no search)."""
    info = {"row_front_y": 0, "row_widths": [30], "house_back": 30}
    rules, _goals, _quality = _check_all(rects, info, 40, 50, "south", 1)
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
    assert by_id["13"]["status"] == "BEND", "west wall covered, rest fine"
    assert by_id["14"]["status"] == "PASS", "bedroom has 12 ft window walls"
    assert by_id["15"]["status"] == "PASS", "common toilet exterior"
    assert by_id["16"]["status"] == "PASS", "all routes via common rooms"
    assert livability_verdict(list(by_id.values())) == (True, []), \
        "bends never flip the verdict"
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
    test_typology_options()
    test_svg_rotation()
    test_impossible_plot()
    test_one_bedroom()
    test_narrow_two_strip()
    test_l_shape_wide()
    test_circulation_pass_branch()
    test_circulation_kitchen_trap()
    print("ALL LAYOUT TESTS PASSED")
