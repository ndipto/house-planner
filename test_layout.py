# test_layout.py
# Day 2 typology tests: three options (A/B/C) per brief, checked + scored.
#
# Run them with: python test_layout.py
# Every test pins honest behavior: livable options, known bends, wishes
# shaping the plan, and the briefs no typology can satisfy (a clear
# message, never a broken plan).

import xml.etree.ElementTree as ET

from ai_program import (
    MASTER_TOILET_D_RANGE,
    MASTER_TOILET_W_RANGE,
    SETBACK_FRONT_FT,
    SETBACK_SIDE_FT,
    SIZE_RULES,
    TOILET_D_RANGE,
    TOILET_W_RANGE,
)
from draw import svg_plan, svg_plot_preview
from layout import (RELAXED_RANGES, _check_all, livability_verdict,
                    shared_wall)
from openings import (SPACE_TYPES, audit_gaps, place_openings,
                     wall_segments)
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

PROGRAM_2BED = [
    _room("Porch", "porch", 8, 5),
    _room("Foyer", "foyer", 8, 10),
    _room("Living Room", "living room", 13, 14),
    _room("Dining", "dining", 11, 13),
    _room("Kitchen", "kitchen", 10, 13, veranda=True),
    _room("Family Living", "family living", 13, 14),
    _room("Bedroom 1", "bedroom", 13, 14, veranda=True),
    _room("Bedroom 2", "bedroom", 12, 13, veranda=True),
    _room("Common Toilet", "bathroom", 7, 8, kind="common"),
    _room("Bath 1", "bathroom", 7, 8, kind="attached",
          attached="Bedroom 1"),
]

WISHES_45 = ("combined living and kitchen, so we can make it a big space "
             "during family gathering. a small garden with the living room, "
             "which will work as a buffer space with outdoor and indoor.")


def _overlap_1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _independent_errors(placements, buildable):
    """Re-verify geometry from raw placements (not the checker's word)."""
    errors = []
    bx0, by0 = SETBACK_SIDE_FT, SETBACK_FRONT_FT  # buildable in plot coords
    bx1 = bx0 + buildable["width"]
    by1 = by0 + buildable["depth"]
    master, best_area = "", 0.0
    for rect in placements:
        if rect["type"] == "bedroom":
            area = rect["w"] * rect["d"]
            if area > best_area:
                master, best_area = rect["name"], area
    for rect in placements:
        if not (rect["x"] >= bx0 - 0.01 and rect["y"] >= by0 - 0.01
                and rect["x"] + rect["w"] <= bx1 + 0.01
                and rect["y"] + rect["d"] <= by1 + 0.01):
            errors.append("outside buildable: %s" % rect["name"])
        kind = rect["type"]
        if kind == "bathroom":
            if master and rect.get("attached_to", "") == master:
                w_low, w_high = MASTER_TOILET_W_RANGE
                d_low, d_high = MASTER_TOILET_D_RANGE
            else:
                w_low, w_high = TOILET_W_RANGE
                d_low, d_high = TOILET_D_RANGE
            if not w_low - 1e-6 <= rect["w"] <= w_high + 1e-6:
                errors.append("toilet width: %s" % rect["name"])
            if not d_low - 1e-6 <= rect["d"] <= d_high + 1e-6:
                errors.append("toilet depth: %s" % rect["name"])
            if abs(rect["w"] - rect["d"]) < 1 - 1e-6:
                errors.append("square-ish: %s" % rect["name"])
        elif kind in SIZE_RULES:
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
            "open_plan": option.get("open_plan", []),
            "glass_partitions": option.get("glass_partitions", []),
            "plot": {"w": plot["width"], "d": plot["depth"],
                     "road": plot["road"],
                     "north_angle": plot.get("north_angle", 0)}}


def _center_x(placements, name):
    for rect in placements:
        if rect["name"] == name:
            return rect["x"] + rect["w"] / 2
    raise AssertionError("missing room %s" % name)


def _footprint(option):
    """Sorted room boxes: two options with equal footprints are identical."""
    return sorted((r["name"], r["x"], r["y"], r["w"], r["d"])
                  for r in option["placements"])


def _assert_clean(option, buildable, plot):
    """Geometry is hard: G passes and the independent recheck agrees."""
    assert _rule_status(option, "G") == "PASS", \
        "option %s: nothing outside the plot" % option["label"]
    assert _independent_errors(option["placements"], buildable) == [], \
        "option %s geometry must be clean" % option["label"]
    ET.fromstring(svg_plan(_svg_for(option, plot)))


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
        for wanted in ("7", "13", "14", "15", "16", "17", "18"):
            assert wanted in ids, "option %s lists rule %s" % (opt["label"],
                                                               wanted)
        _assert_clean(opt, result["buildable"], result["plot"])
    assert by_label["A"]["livable"] is True, "A livable, kitchen west"
    assert by_label["A"]["livability_fails"] == []
    assert by_label["B"]["livable"] is True, "B livable, mirrored"
    assert _rule_status(by_label["B"], "13") == "BEND", "B misses west"
    assert by_label["C"]["livable"] is True, "C livable, third variant"
    for opt in options:
        assert _rule_status(opt, "19") == "PASS", "master 10%+ biggest"
        attached = [r for r in opt["placements"]
                    if r["type"] == "bathroom"
                    and r.get("bathroom_kind") == "attached"]
        master_bath = [b for b in attached
                       if b.get("attached_to") == "Bedroom 1"]
        others = [b for b in attached
                  if b.get("attached_to") != "Bedroom 1"]
        for other in others:
            assert master_bath[0]["w"] * master_bath[0]["d"] >= \
                other["w"] * other["d"] - 0.01, \
                "master keeps the largest attached toilet"
    print("PASS test_typology_options (A/B/C livable, B bends 13)")


def test_fit_wishes_45x55():
    """45x55 South 2-bed + wishes: refused kitchen merge + garden.

    Architect round 1: the kitchen always stays enclosed (Bangladeshi
    cooking), so "combined living and kitchen" reads SKIPPED with the
    glass-to-dining alternative noted; the garden still lands.
    """
    result = build_options(PROGRAM_2BED, 45, 55, "South", 2, WISHES_45)
    options = result["options"]
    assert len(options) == 3, "all three options fit inside the plot"
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "7") == "PASS", "toilets reach their doors"
        assert _rule_status(opt, "18") == "PASS", "real toilet sizes"
        _assert_clean(opt, result["buildable"], result["plot"])
    by_label = {o["label"]: o for o in options}
    assert ("Kitchen", "Living Room") not in by_label["A"]["open_plan"] \
        and ("Living Room", "Kitchen") not in by_label["A"]["open_plan"], \
        "A never merges the kitchen into the living room"
    wishes_a = {w["wish"]: w["status"] for w in by_label["A"]["wishes"]}
    assert wishes_a["Glass partition: kitchen + living room"] \
        == "SKIPPED"
    assert wishes_a["Garden with the living room"] == "MET"
    assert any("glass partition" in note.lower()
               for note in result["notes"] + by_label["A"]["notes"]), \
        "the glass alternative is explained in the design notes"
    wishes_c = {w["wish"]: w["status"] for w in by_label["C"]["wishes"]}
    # Round 1: kitchens never merge, so C keeps the wished garden
    # too (its no-garden variant was an emergent merge ordering).
    assert wishes_c["Garden with the living room"] == "MET"
    # Round 1: C keeps the garden now; its middle dining is windowless
    # (rule 17, the known honest limit - never flips the verdict).
    assert [r["id"] for r in by_label["C"]["rules"]
            if r["status"] == "FAIL"] == ["17"], "C misses 17 only"
    garden = [r for r in by_label["A"]["placements"]
              if r["type"] == "garden"]
    assert len(garden) == 1, "A places the wished garden"
    living = next(r for r in by_label["A"]["placements"]
                  if r["name"] == "Living Room")
    assert garden[0]["garden_for"] == "Living Room"
    assert abs(garden[0]["y"] + garden[0]["d"] - living["y"]) < 0.01, \
        "garden buffers the living room's front wall"
    assert garden[0]["x"] == living["x"] \
        and garden[0]["w"] == living["w"], "garden spans the living front"
    print("PASS test_fit_wishes_45x55 (refused merge + garden, all livable)")


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
    # Too narrow for bands (needs 42 ft) and too shallow for strips
    # (needs 29 ft): honest skips, never a broken plan.
    shallow = build_options(PROGRAM_3BED, 30, 30, "South", 3)
    assert shallow["options"] == [], "nothing fits 27x20 ft buildable"
    assert any("skipped" in note for note in shallow["notes"]), \
        "each skipped option says why (message, not a broken plan)"
    print("PASS test_impossible_plot (no options + reasons)")


def test_one_bedroom():
    """1 bed + 1 toilet: livable options, common toilet on common space."""
    result = build_options(PROGRAM_1BED, 40, 60, "South", 1)
    options = result["options"]
    assert len(options) == 3, "1-bed brief still gets 3 options"
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "7") == "PASS", "toilet rule passes"
        _assert_clean(opt, result["buildable"], result["plot"])
    by_label = {o["label"]: o for o in options}
    assert [r["id"] for r in by_label["A"]["rules"]
            if r["status"] == "FAIL"] == [], "A has zero fails"
    assert [r["id"] for r in by_label["C"]["rules"]
            if r["status"] == "FAIL"] == ["10"], \
        "corner bedroom has no free veranda wall at this width (rule 10)"
    print("PASS test_one_bedroom (3 livable, rule 10 honest on C)")


def test_narrow_two_strip():
    """Buildable under 30 ft: two-strip options; 1-bed livable, 2-bed not."""
    one = build_options(PROGRAM_1BED, 25, 60, "North", 1)
    assert [o["typology"] for o in one["options"]] == ["two-strip"] * 3
    by_label = {o["label"]: o for o in one["options"]}
    for opt in one["options"]:
        assert opt["livable"] is True, "1-bed narrow fits one strip"
        _assert_clean(opt, one["buildable"], one["plot"])
    assert [r["id"] for r in by_label["A"]["rules"]
            if r["status"] == "FAIL"] == ["10"], "bedroom veranda missing"
    assert [r["id"] for r in by_label["C"]["rules"]
            if r["status"] == "FAIL"] == [], "alt order has zero fails"
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
        assert "7" in opt["livability_fails"], "common keeps no door"
        _assert_clean(opt, two["buildable"], two["plot"])
    print("PASS test_narrow_two_strip (1-bed livable, 2-bed honest)")


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
        _assert_clean(opt, result["buildable"], result["plot"])
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
        _mrect("Common", "bathroom", 10, 2, 6, 8, kind="common"),
    ]
    by_id = {row["id"]: row for row in _mini_rules(rects)}
    assert by_id["7"]["status"] == "PASS", "common opens onto dining"
    assert by_id["13"]["status"] == "BEND", "west wall covered, rest fine"
    assert by_id["14"]["status"] == "PASS", "bedroom has 12 ft window walls"
    assert by_id["15"]["status"] == "PASS", "common toilet exterior"
    assert by_id["16"]["status"] == "PASS", "all routes via common rooms"
    assert by_id["18"]["status"] == "PASS", "6x8 toilet, real size"
    assert livability_verdict(list(by_id.values())) == (True, []), \
        "bends never flip the verdict"
    print("PASS test_circulation_pass_branch (mini-plan LIVABLE)")


def test_circulation_kitchen_trap():
    """Hand-made plan where the bedroom route must cross the kitchen."""
    rects = [
        _mrect("Bedroom", "bedroom", 20, 0, 10, 10),
        _mrect("Kitchen", "kitchen", 10, 0, 10, 10),
        _mrect("Common", "bathroom", 4, 0, 6, 8, kind="common"),
        _mrect("Foyer", "foyer", 3, 10, 10, 8),
    ]
    by_id = {row["id"]: row for row in _mini_rules(rects)}
    assert by_id["7"]["status"] == "FAIL", "no dining/family to open onto"
    assert by_id["13"]["status"] == "FAIL", "kitchen has no veranda"
    assert by_id["16"]["status"] == "FAIL", "bedroom route crosses kitchen"
    assert "KITCHEN" in by_id["16"]["detail"], "report must name the crossing"
    assert by_id["18"]["status"] == "PASS", "6x8 toilet, real size"
    assert livability_verdict(list(by_id.values()))[0] is False
    print("PASS test_circulation_kitchen_trap (UNLIVABLE, crossing named)")


WISHES_EAST = ("need a south facing master bedroom. "
                "and nice living room.")


def test_road_east_facing_master():
    """40 frontage x 60 deep, road East: livable, master south (low x)."""
    result = build_options(PROGRAM_2BED, 40, 60, "East", 2, WISHES_EAST)
    options = result["options"]
    assert len(options) == 3, "deep road-relative plot fits strips"
    middle = SETBACK_SIDE_FT + result["buildable"]["width"] / 2
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "18") == "PASS", "real toilet sizes"
        _assert_clean(opt, result["buildable"], result["plot"])
        assert _center_x(opt["placements"], "Bedroom 1") < middle, \
            "option %s: master on the south side" % opt["label"]
        assert any("south side (client wish" in note
                   for note in opt["notes"]), "the wish is reported"
        assert any(w["status"] == "MET" and "south-facing" in w["wish"]
                   for w in opt["wishes"]), "south wish MET in the table"
    by_label = {o["label"]: o for o in options}
    assert _center_x(by_label["A"]["placements"], "Bedroom 2") > middle, \
        "A: second bedroom takes the other corner"
    assert _center_x(by_label["B"]["placements"], "Bedroom 2") > middle, \
        "B: second bedroom takes the other corner"
    assert by_label["C"]["typology"] == "three-strip"
    common_c = next(r for r in by_label["C"]["placements"]
                    if r["name"] == "Common Toilet")
    common_a = next(r for r in by_label["A"]["placements"]
                    if r["name"] == "Common Toilet")
    assert (common_c["x"] < middle) != (common_a["x"] < middle), \
        "C moves the common toilet to the other side"
    feet = [_footprint(o) for o in options]
    assert feet[0] != feet[1] and feet[0] != feet[2] \
        and feet[1] != feet[2], "options must differ"
    print("PASS test_road_east_facing_master (master south x3)")


def test_wide_shallow_bands():
    """60 frontage x 40 deep, road South: shallow bands, all livable."""
    result = build_options(PROGRAM_2BED, 60, 40, "South", 2)
    options = result["options"]
    assert [o["typology"] for o in options] == ["shallow-band"] * 3
    assert any("shallow two-band" in note for note in result["notes"]), \
        "the fallback is announced"
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "18") == "PASS", "real toilet sizes"
        assert _rule_status(opt, "G") == "PASS", "nothing outside"
        _assert_clean(opt, result["buildable"], result["plot"])
        baths = [r for r in opt["placements"] if r["type"] == "bathroom"]
        assert baths and all(b["w"] == 5.0 for b in baths), \
            "toilets never stretched to fill the band"
    by_label = {o["label"]: o for o in options}
    assert _rule_status(by_label["A"], "13") == "PASS", \
        "A: kitchen west corner + veranda"
    assert _rule_status(by_label["B"], "13") == "BEND", "B misses west"
    # Day 3 (real doors): the band kitchen sits at the far end, away from
    # dining, and the 3 ft corner store cannot take a 3 ft door - both
    # honestly reported (non-verdict rules; C stays LIVABLE).
    assert [r["id"] for r in by_label["C"]["rules"]
            if r["status"] == "FAIL"] == ["4", "12"], "C misses 4 + 12"
    feet = [_footprint(o) for o in options]
    assert feet[0] != feet[1] and feet[0] != feet[2] \
        and feet[1] != feet[2], "options must differ"
    print("PASS test_wide_shallow_bands (3 livable bands)")


def _center_y(placements, name):
    for rect in placements:
        if rect["name"] == name:
            return rect["y"] + rect["d"] / 2
    raise AssertionError("missing room %s" % name)


def test_front_facing_master():
    """South road + south master: front-most bedroom, all livable."""
    result = build_options(PROGRAM_2BED, 45, 55, "South", 2,
                           "south facing master bedroom")
    options = result["options"]
    assert len(options) == 3
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "7") == "PASS", "common keeps its door"
        assert _rule_status(opt, "8") == "PASS", "no toilet on front wall"
        assert _rule_status(opt, "18") == "PASS", "real toilet sizes"
        _assert_clean(opt, result["buildable"], result["plot"])
        assert _center_y(opt["placements"], "Bedroom 1") < \
            _center_y(opt["placements"], "Bedroom 2"), \
            "option %s: master front-most" % opt["label"]
        assert any("front-most (client wish" in note
                   for note in opt["notes"]), "the wish is reported"
    print("PASS test_front_facing_master (front-most x3)")


def _arrow_spins(svg_text):
    """Rotate angles on the north-needle polygons in an SVG string."""
    root = ET.fromstring(svg_text)
    ns = "{http://www.w3.org/2000/svg}"
    spins = []
    for poly in root.iter("%spolygon" % ns):
        transform = poly.get("transform", "")
        if transform.startswith("rotate("):
            spins.append(transform.split(" ")[0][len("rotate("):])
    return spins


def test_preview_north_angles():
    """Preview at 0/90/30 deg: to scale, ROAD + dims + turning arrow."""
    for angle, spin in ((0, []), (90, ["90"]), (30, ["30"])):
        root = ET.fromstring(svg_plot_preview(40, 60, angle))
        ns = "{http://www.w3.org/2000/svg}"
        plot = root.find("%srect[@stroke-width='3']" % ns)
        ratio = float(plot.get("width")) / float(plot.get("height"))
        assert abs(ratio - 40 / 60) < 0.01, "preview to scale at %d" % angle
        texts = [(t.text or "") for t in root.iter("%stext" % ns)]
        assert "ROAD" in texts, "road band labeled at %d" % angle
        assert any("frontage" in t and "40" in t for t in texts), \
            "frontage dim at %d" % angle
        assert any(t.startswith("60") and "deep" in t for t in texts), \
            "depth dim at %d" % angle
        assert any("north %d deg" % angle in t for t in texts), \
            "angle caption at %d" % angle
        assert _arrow_spins(svg_plot_preview(40, 60, angle)) == spin, \
            "arrow turn at %d" % angle
    print("PASS test_preview_north_angles (0/90/30 preview)")


def test_angle_matches_cardinal():
    """Cardinal angles equal the old road sides, placement for placement."""
    for angle, road in ((0, "South"), (90, "East"), (180, "North"),
                        (270, "West")):
        angled = build_options(PROGRAM_2BED, 40, 60, road, 2, WISHES_EAST,
                               angle)
        plain = build_options(PROGRAM_2BED, 40, 60, road, 2, WISHES_EAST)
        assert [o["label"] for o in angled["options"]] == ["A", "B", "C"]
        for opt_a, opt_p in zip(angled["options"], plain["options"]):
            assert _footprint(opt_a) == _footprint(opt_p), \
                "angle %d matches road %s" % (angle, road)
            assert opt_a["livable"] == opt_p["livable"]
    print("PASS test_angle_matches_cardinal (0/90/180/270)")


def test_angle_30_south_wish():
    """North 30 deg + south master: front-most, livable, arrow at 30."""
    result = build_options(PROGRAM_2BED, 45, 55, "south", 2,
                           "south facing master bedroom", 30)
    assert [o["label"] for o in result["options"]] == ["A", "B", "C"]
    for opt in result["options"]:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "18") == "PASS", "real toilet sizes"
        _assert_clean(opt, result["buildable"], result["plot"])
        assert _center_y(opt["placements"], "Bedroom 1") < \
            _center_y(opt["placements"], "Bedroom 2"), \
            "option %s: master front-most" % opt["label"]
        svg = svg_plan(_svg_for(opt, result["plot"]))
        ET.fromstring(svg)  # well-formed with the angle
        assert _arrow_spins(svg) == ["30"], "plan arrow follows north"
        assert "north 30 deg" in svg, "plan names the angle"
    print("PASS test_angle_30_south_wish (front-most + arrow)")


WISHES_50 = ("open living and dining for family gathering. "
             "south facing master bedroom.")


def test_master_front_south_50x40():
    """50x40 road South, north 0: front-corner south master, both wishes.

    A/B put the master in a front corner (south MET, open plan MET);
    C stays classic for comparison (both NOT MET, ranked lower). Every
    option is livable with the master 10%+ biggest and every bedroom
    door opening into family living (dining fallback allowed).
    """
    result = build_options(PROGRAM_2BED, 50, 40, "South", 2, WISHES_50, 0)
    options = result["options"]
    assert [o["label"] for o in options] == ["A", "B", "C"]
    by_label = {o["label"]: o for o in options}
    assert "master front" in by_label["A"]["title"]
    assert "master front" in by_label["B"]["title"]
    for opt in options:
        assert opt["livable"] is True, "option %s livable" % opt["label"]
        assert _rule_status(opt, "5") == "PASS", "bedroom doors reach"
        assert _rule_status(opt, "19") == "PASS", "master 10%+ biggest"
        _assert_clean(opt, result["buildable"], result["plot"])
        beds = [r for r in opt["placements"] if r["type"] == "bedroom"]
        master = max(beds, key=lambda r: r["w"] * r["d"])
        assert master["name"] == "Bedroom 1", "Bedroom 1 is the master"
        for bed in beds:
            if bed["name"] != "Bedroom 1":
                assert master["w"] * master["d"] >= \
                    1.1 * bed["w"] * bed["d"] - 0.01, \
                    "master 10%+ over %s" % bed["name"]
        hubs = [r for r in opt["placements"]
                if r["type"] in ("family living", "dining")]
        for bed in beds:
            touch = max(shared_wall(bed, hub) for hub in hubs)
            assert touch >= 3 - 1e-6, \
                "%s opens into family/dining" % bed["name"]
        fam = max(shared_wall(master, r) for r in opt["placements"]
                  if r["type"] == "family living")
        assert fam >= 3 - 1e-6, "master opens into family living"
    wishes = {label: {w["wish"]: w["status"]
                      for w in by_label[label]["wishes"]}
              for label in ("A", "B", "C")}
    for label in ("A", "B"):
        assert wishes[label]["Open plan: dining + living room"] == "MET"
        assert wishes[label]["south-facing master bedroom"] == "MET"
    assert wishes["C"]["Open plan: dining + living room"] == "NOT MET"
    assert wishes["C"]["south-facing master bedroom"] == "NOT MET"
    assert by_label["C"]["score"] < by_label["A"]["score"]
    assert by_label["C"]["score"] < by_label["B"]["score"]
    feet = [_footprint(o) for o in options]
    assert feet[0] != feet[1] and feet[0] != feet[2] \
        and feet[1] != feet[2], "options must differ"
    print("PASS test_master_front_south_50x40 (front master, wishes MET x2)")


def _program_4bed():
    """T6 program: 4 bedrooms, common toilet + 2 attached."""
    return PROGRAM_2BED + [
        _room("Bedroom 3", "bedroom", 11, 12),
        _room("Bedroom 4", "bedroom", 11, 12),
        _room("Bath 2", "bathroom", 7, 8, kind="attached",
              attached="Bedroom 2"),
    ]


def _livable_options(result):
    return [o for o in result["options"] if o["livable"]]


def _wish_map(option):
    return {w["wish"]: w["status"] for w in option["wishes"]}


def test_t1_40x60_north_3bed():
    """T1: 40x60 road North, 3 bed, 3 toilets. Bar: a livable option
    with the master largest (rule 19) and bedroom doors off the hub
    (rule 5), all inside the buildable area."""
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    livable = _livable_options(result)
    assert livable, "T1 needs at least one LIVABLE option"
    best = livable[0]
    assert _rule_status(best, "19") == "PASS", "master is the largest"
    assert _rule_status(best, "5") != "FAIL", "no blocked bedroom door"
    _assert_clean(best, result["buildable"], result["plot"])
    print("PASS test_t1_40x60_north_3bed (%d livable)"
          % len(livable))


def test_t2_45x55_south_combined_garden():
    """T2: 45x55 road South, combined living+kitchen + garden. Bar: a
    livable option with the garden MET and the kitchen merge honestly
    SKIPPED (architect round 1: enclosed kitchen, glass alternative)."""
    wishes = ("combined living and kitchen for family gathering, "
              "small garden beside the living room")
    result = build_options(PROGRAM_2BED, 45, 55, "South", 2, wishes)
    good = [o for o in _livable_options(result)
            if _wish_map(o).get("Glass partition: kitchen + living room")
            == "SKIPPED"
            and _wish_map(o).get("Garden with the living room")
            == "MET"]
    assert good, "T2 needs a LIVABLE option, garden MET, merge SKIPPED"
    assert any("glass partition" in note.lower()
               for note in result["notes"] + good[0]["notes"]), \
        "the glass alternative is explained"
    _assert_clean(good[0], result["buildable"], result["plot"])
    print("PASS test_t2_45x55_south_combined_garden")


def test_t3_40x60_east_south_master():
    """T3: frontage 40, depth 60, road East, south-facing master. Bar:
    a livable option with the south-master wish MET."""
    result = build_options(
        PROGRAM_2BED, 40, 60, "East", 2,
        "south facing master bedroom, nice living room")
    good = [o for o in _livable_options(result)
            if _wish_map(o).get("south-facing master bedroom")
            == "MET"]
    assert good, "T3 needs a LIVABLE option, master facing south"
    _assert_clean(good[0], result["buildable"], result["plot"])
    print("PASS test_t3_40x60_east_south_master")


def test_t4_50x40_south_open_south_master():
    """T4: 50x40 road South, open living+dining + south master. Bar: a
    livable option with both wishes MET, master largest, hub doors."""
    result = build_options(
        PROGRAM_2BED, 50, 40, "South", 2,
        "open living and dining for family gathering. "
        "south facing master bedroom")
    good = [o for o in _livable_options(result)
            if _wish_map(o).get("Open plan: dining + living room")
            == "MET"
            and _wish_map(o).get("south-facing master bedroom")
            == "MET"]
    assert good, "T4 needs a LIVABLE option with both wishes MET"
    assert _rule_status(good[0], "19") == "PASS", "master is the largest"
    assert _rule_status(good[0], "5") != "FAIL", "no blocked bedroom door"
    _assert_clean(good[0], result["buildable"], result["plot"])
    print("PASS test_t4_50x40_south_open_south_master")


def test_t5_30x50_north_narrow():
    """T5: 30x50 road North, narrow plot. The side rooms need ~54 ft of
    depth and only 40 ft exist, so no honest plan fits: the placer
    must skip every option with a clear message, never a broken plan.
    """
    result = build_options(PROGRAM_2BED, 30, 50, "North", 2)
    assert result["options"] == [], "T5 fits nothing; options stay empty"
    assert len(result["notes"]) == 3, "one skip note per option"
    for note in result["notes"]:
        assert "need at least" in note and "have" in note, \
            "skip note states the shortfall: %s" % note
    print("PASS test_t5_30x50_north_narrow (honest skip)")


def test_t6_50x70_west_4bed_elderly():
    """T6: 50x70 road West, 4 bed, 3 toilets, garden + a bedroom near
    family living. Both wishes must be MET; the verdict must stay
    honest (livable exactly when zero hard fails).

    NOTE (night queue, deferred to the architect): the 4-bedroom west
    spine still strands back bedrooms (rules 5/16) and ties the master
    (rule 19), so all options currently read UNLIVABLE with reasons.
    Fixing that needs a new typology move (L extension / second hub);
    when it lands, strengthen this test to require a LIVABLE option.
    """
    result = build_options(
        _program_4bed(), 50, 70, "West", 3,
        "garden, elderly parents need a bedroom near family living")
    assert len(result["options"]) == 3, "T6 builds all 3 options"
    for opt in result["options"]:
        assert _wish_map(opt).get("Bedroom near family living") \
            == "MET", "elderly bedroom near family living"
        assert _wish_map(opt).get("Garden with the living room") \
            == "MET", "garden placed"
        assert opt["livable"] == (opt["livability_fails"] == []), \
            "verdict matches hard fails on %s" % opt["label"]
        # Day 3 honesty: the stranded bedroom and the kitchen (no
        # dining wall) miss their doors too; both flip to PASS with
        # the typology fix, together with the verdict.
        assert _rule_status(opt, "4") == "FAIL", "kitchen doorless"
        assert _rule_status(opt, "12") == "FAIL", "doors incomplete"
        _assert_clean(opt, result["buildable"], result["plot"])
    print("PASS test_t6_50x70_west_4bed_elderly (wishes MET, "
          "verdict honest)")


def _doors_by_kind(doors):
    kinds = {}
    for door in doors:
        kinds.setdefault(door["kind"], []).append(door)
    return kinds


def test_no_pending_rules():
    """Day 3: no rule stays PENDING on any review-brief option."""
    briefs = [
        (PROGRAM_3BED, 40, 60, "North", 3, ""),
        (PROGRAM_2BED, 45, 55, "South", 2,
         "combined living and kitchen for family gathering, "
         "small garden beside the living room"),
        (PROGRAM_2BED, 40, 60, "East", 2,
         "south facing master bedroom, nice living room"),
        (PROGRAM_2BED, 50, 40, "South", 2,
         "open living and dining for family gathering. "
         "south facing master bedroom"),
        (_program_4bed(), 50, 70, "West", 3,
         "garden, elderly parents need a bedroom near family living"),
        (PROGRAM_1BED, 40, 60, "North", 1, ""),
        (PROGRAM_2BED, 60, 40, "South", 2, ""),
    ]
    count = 0
    for program, fw, fd, road, ntoilets, wishes in briefs:
        result = build_options(program, fw, fd, road, ntoilets, wishes)
        for opt in result["options"]:
            count += 1
            pending = [r["id"] for r in opt["rules"]
                       if r["status"] == "PENDING"]
            assert pending == [], "option %s still PENDING: %s" \
                % (opt["label"], pending)
    assert count > 15, "the sweep must cover real options"
    print("PASS test_no_pending_rules (%d options, zero PENDING)" % count)


def test_doors_windows_placed():
    """Day 3: T1-A carries the full door/window table, gaps clean."""
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    opt = {o["label"]: o for o in result["options"]}["A"]
    assert opt["livable"] is True
    placed = place_openings(opt["placements"], opt["open_plan"], 0.0)
    doors, windows = placed["doors"], placed["windows"]
    assert placed["problems"] == [], "all required doors placed"
    assert audit_gaps(opt["placements"], doors, windows) == [], \
        "corners cleared, no clashes"
    kinds = _doors_by_kind(doors)
    entry = kinds.get("entry", [])
    assert len(entry) == 1 and entry[0]["width"] == 3.5, "entry 3'-6\""
    assert {entry[0]["room"], entry[0]["into"]} == {"Porch", "Foyer"}
    by_name = {r["name"]: r for r in opt["placements"]}
    for bed in ("Bedroom 1", "Bedroom 2", "Bedroom 3"):
        hits = [d for d in doors if d["room"] == bed]
        assert len(hits) == 1, "%s has one own door" % bed
        other = hits[0]["into"] if hits[0]["room"] == bed \
            else hits[0]["room"]
        assert by_name[other]["type"] in ("family living", "dining"), \
            "%s opens off the hub" % bed
        assert hits[0]["width"] == 3.0
    assert any("Kitchen" in (d["room"], d["into"])
               and "Dining" in (d["room"], d["into"]) for d in doors), \
        "kitchen door into dining"
    for bath, host in (("Bath 1", "Bedroom 1"), ("Bath 2", "Bedroom 2")):
        hits = [d for d in doors if d["room"] == bath]
        assert len(hits) == 1 and hits[0]["width"] == 2.5, \
            "%s toilet door 2'-6\"" % bath
        other = hits[0]["into"]
        if other == host:
            continue  # direct door (no dressing lobby between)
        assert by_name[other]["type"] in ("wardrobe", "storage"), \
            "%s opens into its dressing %s" % (bath, other)
        assert any({d["room"], d["into"]} == {other, host}
                   for d in doors), \
            "%s opens on to %s" % (other, host)
    verandas = [r for r in opt["placements"] if r["type"] == "veranda"]
    assert verandas, "T1-A has verandas"
    for veranda in verandas:
        hits = [d for d in doors if veranda["name"] in (d["room"],
                                                        d["into"])]
        assert len(hits) == 1, "%s has one door" % veranda["name"]
    for bed in ("Bedroom 1", "Bedroom 2", "Bedroom 3"):
        assert any(w["room"] == bed for w in windows), \
            "%s windowed" % bed
    for bath in ("Bath 1", "Bath 2", "Common Toilet"):
        sides = [w["wall"] for w in windows if w["room"] == bath]
        assert sides, "%s windowed" % bath
        assert "S" not in sides, "%s window never road-side" % bath
    print("PASS test_doors_windows_placed (%d doors, %d windows)"
          % (len(doors), len(windows)))


def test_door_bearing_nudge():
    """Day 3: the 1-bed kitchen slides to a 3 ft dining bearing."""
    result = build_options(PROGRAM_1BED, 40, 60, "North", 1)
    by_label = {o["label"]: o for o in result["options"]}
    for label in ("A", "B"):
        opt = by_label[label]
        names = {r["name"]: r for r in opt["placements"]}
        bearing = shared_wall(names["Kitchen"], names["Dining"])
        assert bearing >= 3.0 - 0.01, \
            "%s kitchen bears %.1f ft on dining" % (label, bearing)
        assert _rule_status(opt, "4") == "PASS", "kitchen door fits"
    assert any("nudged" in note for opt in result["options"]
               for note in opt["notes"]), "the nudge is reported"
    print("PASS test_door_bearing_nudge (1-bed A/B bear 3 ft)")


def test_svg_walls_doors_windows():
    """Day 3: the SVG draws solid walls, door arcs and window lines;
    open-plan pairs share no wall band."""
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    opt = {o["label"]: o for o in result["options"]}["A"]
    placed = place_openings(opt["placements"], opt["open_plan"], 0.0)
    svg = svg_plan(_svg_for(opt, result["plot"]))
    ET.fromstring(svg)
    assert svg.count('fill="#000"') > 20, "solid wall bands drawn"
    assert svg.count("<path d=\"M") == len(placed["doors"]), \
        "one swing arc per door"
    assert "stroke-width=\"1\"" in svg, "window/leaf thin lines drawn"
    open_result = build_options(
        PROGRAM_2BED, 50, 40, "South", 2,
        "open living and dining for family gathering. "
        "south facing master bedroom")
    open_opt = {o["label"]: o for o in open_result["options"]}["A"]
    assert ("Dining", "Living Room") in open_opt["open_plan"] \
        or ["Dining", "Living Room"] in open_opt["open_plan"], \
        "A merges dining + living"
    names = {r["name"]: r for r in open_opt["placements"]}
    living, dining = names["Living Room"], names["Dining"]
    lo = max(living["x"], dining["x"])
    hi = min(living["x"] + living["w"], dining["x"] + dining["w"])
    if abs(living["x"] + living["w"] - dining["x"]) < 0.02:
        seam = (dining["x"], living["y"] + living["d"] / 2)
    elif abs(dining["x"] + dining["w"] - living["x"]) < 0.02:
        seam = (living["x"], living["y"] + living["d"] / 2)
    else:
        seam = ((lo + hi) / 2, dining["y"])
    # The open pair shares no wall band across its seam (checked before
    # gaps are cut), and dropping the pair restores wall bands there.
    segs = wall_segments(open_opt["placements"], [], [],
                         open_opt["open_plan"])
    for seg in segs:
        assert not (seg["x0"] < seam[0] < seg["x1"]
                    and seg["y0"] < seam[1] < seg["y1"]), \
            "no wall band crosses the open seam"
    closed = wall_segments(open_opt["placements"], [], [], [])
    assert len(closed) > len(segs), "the open wall is really omitted"
    print("PASS test_svg_walls_doors_windows")


def test_architect_round1():
    """Architect review round 1: spaces, corner doors, glass, road rules."""
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    by_label = {o["label"]: o for o in result["options"]}
    opt = by_label["A"]
    names = {r["name"]: r for r in opt["placements"]}
    placed = place_openings(opt["placements"], opt["open_plan"], 0.0,
                            opt["glass_partitions"])
    spaces = {n for n, r in names.items() if r["type"] in SPACE_TYPES}
    for door in placed["doors"]:
        assert not ({door["room"], door["into"]} <= spaces), \
            "no door between open spaces"
        assert door["hinge"] in (0, 1), "hinge recorded"
        host = names[door["wall_room"]]
        side = door["wall"]
        length = host["w"] if side in ("N", "S") else host["d"]
        if side in ("N", "S"):
            lo = min(door["x0"], door["x1"]) - host["x"]
            hi = max(door["x0"], door["x1"]) - host["x"]
        else:
            lo = min(door["y0"], door["y1"]) - host["y"]
            hi = max(door["y0"], door["y1"]) - host["y"]
        assert min(lo, length - hi) <= 0.6, \
            "door %s hugs a corner" % door["room"]
    segs = wall_segments(opt["placements"], placed["doors"],
                         placed["windows"], opt["open_plan"],
                         opt["glass_partitions"])
    int_lens = [max(s["x1"] - s["x0"], s["y1"] - s["y0"])
                for s in segs if s["kind"] == "int"]
    assert any(abs(size - 2.0) < 0.05 for size in int_lens), \
        "2 ft stub walls drawn between spaces"
    pairs = [{d["room"], d["into"]} for d in placed["doors"]]
    assert {"Bath 1", "Wardrobe (Bath 1)"} in pairs, "bath via dressing"
    assert {"Wardrobe (Bath 1)", "Bedroom 1"} in pairs, "dressing to bed"
    assert {"Bath 1", "Bedroom 1"} not in pairs, "no direct bath door"
    for o in result["options"]:
        assert _rule_status(o, "21") == "PASS", "kitchen off the road"
    fam_wins = [w for w in placed["windows"]
                if w["room"] == "Family Living"]
    assert any(w["wall"] == "N" and w["width"] == 5.0
               for w in fam_wins), "family gets its big back window"
    glass_opts = [o["label"] for o in result["options"]
                  if ("Dining", "Family Living")
                  in o["glass_partitions"]]
    assert glass_opts == ["C"], "variety glass lands on one option"
    assert any("sliding glass door" in n for n in by_label["C"]["notes"])
    t4 = build_options(PROGRAM_2BED, 50, 40, "South", 2,
                       "open living and dining for family gathering. "
                       "south facing master bedroom")
    a4 = {o["label"]: o for o in t4["options"]}["A"]
    rule4 = [x for x in a4["rules"] if x["id"] == "4"][0]
    assert rule4["status"] == "PASS" and "far corner" in rule4["detail"]
    p4 = place_openings(a4["placements"], a4["open_plan"], 0.0,
                        a4["glass_partitions"])
    assert any(w["room"] == "Bedroom 1" and w["wall"] == "S"
               for w in p4["windows"]), "front bedroom road window"
    t2 = build_options(PROGRAM_2BED, 45, 55, "South", 2,
                       "combined living and kitchen for family gathering, "
                       "small garden beside the living room")
    c2 = {o["label"]: o for o in t2["options"]}["C"]
    assert ("Kitchen", "Dining") in c2["glass_partitions"]
    p2 = place_openings(c2["placements"], c2["open_plan"], 0.0,
                        c2["glass_partitions"])
    assert not any({d["room"], d["into"]} == {"Kitchen", "Dining"}
                   for d in p2["doors"]), "slider, no swing door"
    spine_ys = set()
    for n in ("Foyer", "Living Room", "Dining", "Family Living"):
        spine_ys.add(round(names[n]["y"], 2))
        spine_ys.add(round(names[n]["y"] + names[n]["d"], 2))
    sides = [r for r in opt["placements"]
             if r["type"] in ("bedroom", "kitchen", "bathroom",
                               "wardrobe", "storage")]
    assert any(round(r["y"], 2) not in spine_ys
               or round(r["y"] + r["d"], 2) not in spine_ys
               for r in sides), "side rooms stagger off the spine lines"
    svg = svg_plan(_svg_for(opt, result["plot"]))
    assert svg.count("#d5e5cf") > 5, "leftover drawn as landscape"
    print("PASS test_architect_round1 (12 rules honored)")


if __name__ == "__main__":
    test_typology_options()
    test_fit_wishes_45x55()
    test_svg_rotation()
    test_impossible_plot()
    test_road_east_facing_master()
    test_front_facing_master()
    test_master_front_south_50x40()
    test_wide_shallow_bands()
    test_preview_north_angles()
    test_angle_matches_cardinal()
    test_angle_30_south_wish()
    test_one_bedroom()
    test_narrow_two_strip()
    test_l_shape_wide()
    test_circulation_pass_branch()
    test_circulation_kitchen_trap()
    test_t1_40x60_north_3bed()
    test_t2_45x55_south_combined_garden()
    test_t3_40x60_east_south_master()
    test_t4_50x40_south_open_south_master()
    test_t5_30x50_north_narrow()
    test_t6_50x70_west_4bed_elderly()
    test_no_pending_rules()
    test_doors_windows_placed()
    test_door_bearing_nudge()
    test_svg_walls_doors_windows()
    test_architect_round1()
    print("ALL LAYOUT TESTS PASSED")
