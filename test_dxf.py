# test_dxf.py
# DXF export tests: dxf_plan output for real typology options.
#
# Run them with: python test_dxf.py
# Every test builds a deterministic 1-bed option (no AI) and checks the
# DXF against independently recomputed openings/geometry - not the
# exporter's own word.

from dxf_export import dxf_plan
from layout import SHORT_NAMES
from openings import place_openings, wall_segments
from typology import build_options


def _room(name, room_type, width, depth, veranda=False, kind="",
          attached=""):
    """One AI-shaped program room with the fields layout.py reads."""
    return {"name": name, "type": room_type, "width_ft": width,
            "depth_ft": depth, "adjacencies": [], "door_opens_into": "",
            "needs_veranda": veranda, "preferred_orientation": "",
            "features": [], "bathroom_kind": kind, "attached_to": attached}


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


def _dxf_and_option(road="South", angle=0.0):
    """(dxf string, option) for the 1-bed brief on a 40x60 plot."""
    result = build_options(PROGRAM_1BED, 40, 60, road, 1)
    assert result["options"], "1-bed 40x60 %s must build" % road
    opt = result["options"][0]
    dxf = dxf_plan({"ok": True, "placements": opt["placements"],
                    "open_plan": opt.get("open_plan", []),
                    "glass_partitions": opt.get("glass_partitions", []),
                    "plot": {"w": 40, "d": 60, "road": road.lower(),
                             "north_angle": angle}})
    return dxf, opt


def _entities(dxf):
    """Parse the ENTITIES section into [{type, codes}] (code -> value)."""
    lines = dxf.split("\n")
    try:
        start = lines.index("ENTITIES")
        end = lines.index("ENDSEC", start)
    except ValueError:
        raise AssertionError("ENTITIES section missing")
    assert lines[end - 1] == "0", "ENDSEC keeps its 0 code"
    body = lines[start + 1:end - 1]
    assert len(body) % 2 == 0, "DXF group codes pair up"
    found = []
    current = None
    for code, value in zip(body[0::2], body[1::2]):
        if code == "0":
            current = {"type": value, "codes": {}}
            found.append(current)
        elif current is not None:
            current["codes"][code] = value
    return found


def test_dxf_envelope():
    dxf, _opt = _dxf_and_option()
    lines = dxf.split("\n")
    assert lines[0] == "999", "file opens with a comment"
    assert lines[1:5] == ["House Planner concept plan - units: feet",
                          "0", "SECTION", "2"], "header section opens"
    assert dxf.endswith("0\nENDSEC\n0\nEOF\n"), "file ends with EOF"
    for section in ("HEADER", "TABLES", "ENTITIES"):
        assert "\n2\n%s\n" % section in dxf, section + " present"
    assert "9\n$INSUNITS\n70\n2\n" in dxf, "units are feet"
    assert "1\nAC1009\n" in dxf, "DXF R12 version tag"
    for layer in ("WALLS", "DOORS", "WINDOWS", "GLASS", "TEXT",
                  "DIMS", "PLOT", "SETBACK", "ROAD", "NORTH"):
        assert "0\nLAYER\n2\n%s\n" % layer in dxf, layer + " defined"
    assert "0\nLTYPE\n2\nDASHED\n" in dxf, "dashed linetype defined"
    entities = _entities(dxf)
    kinds = {e["type"] for e in entities}
    assert kinds <= {"LINE", "ARC", "CIRCLE", "TEXT"}, \
        "R12-basic entities only, got %s" % sorted(kinds)
    assert {"LINE", "ARC", "TEXT"} <= kinds, \
        "walls, door swings and labels present"
    for text in [e for e in entities if e["type"] == "TEXT"]:
        assert "1" in text["codes"] and "40" in text["codes"], \
            "every TEXT has a string and a height"
    print("PASS test_dxf_envelope (%d entities)" % len(entities))


def test_dxf_rooms_labeled():
    dxf, opt = _dxf_and_option()
    texts = [e["codes"].get("1", "") for e in _entities(dxf)
             if e["type"] == "TEXT"]
    for room in opt["placements"]:
        name = room["name"]
        short = SHORT_NAMES.get(room.get("type", ""), name.split(" ")[0])
        label = name if name == "Foyer" or name in texts else short
        assert label in texts, "%s labeled (full or short)" % name
    print("PASS test_dxf_rooms_labeled (%d rooms)"
          % len(opt["placements"]))


def test_dxf_openings_match():
    dxf, opt = _dxf_and_option()
    rects = opt["placements"]
    placed = place_openings(rects, opt.get("open_plan", []), 0.0,
                            opt.get("glass_partitions", []))
    segments = wall_segments(rects, placed["doors"], placed["windows"],
                             opt.get("open_plan", []),
                             opt.get("glass_partitions", []))
    entities = _entities(dxf)
    arcs = [e for e in entities if e["type"] == "ARC"]
    assert len(arcs) == len(placed["doors"]), \
        "one swing arc per door (%d)" % len(placed["doors"])
    for arc in arcs:
        radius = float(arc["codes"]["40"])
        assert radius > 0, "positive arc radius"
        start = float(arc["codes"]["50"])
        end = float(arc["codes"]["51"])
        assert 0.0 <= start < 360.0 and 0.0 <= end < 360.0, \
            "arc angles in range"
        assert abs((end - start) % 360.0 - 90.0) < 1.0, \
            "quarter-circle swing, got %.1f deg" % (
                (end - start) % 360.0)
    win_lines = [e for e in entities if e["type"] == "LINE"
                 and e["codes"].get("8") == "WINDOWS"]
    assert len(win_lines) == 2 * len(placed["windows"]), \
        "two lines per window (%d)" % len(placed["windows"])
    glass_runs = sum(1 for s in segments if s["kind"] == "glass")
    glass_lines = [e for e in entities if e["type"] == "LINE"
                   and e["codes"].get("8") == "GLASS"]
    assert len(glass_lines) == 2 * glass_runs, \
        "two lines per glass run (%d)" % glass_runs
    wall_rects = sum(1 for s in segments if s["kind"] != "glass")
    wall_lines = [e for e in entities if e["type"] == "LINE"
                  and e["codes"].get("8") == "WALLS"]
    assert len(wall_lines) >= 4 * wall_rects, \
        "wall band outlines present (%d bands)" % wall_rects
    print("PASS test_dxf_openings_match (%d doors, %d windows)"
          % (len(placed["doors"]), len(placed["windows"])))


def test_dxf_road_sides():
    for road, draw_w, draw_d in (("South", 40, 60), ("North", 40, 60),
                                 ("East", 60, 40), ("West", 60, 40)):
        dxf, _opt = _dxf_and_option(road)
        roads = [e for e in _entities(dxf) if e["type"] == "TEXT"
                 and e["codes"].get("1") == "ROAD"]
        assert len(roads) == 1, "one ROAD label on %s" % road
        x = float(roads[0]["codes"]["10"])
        y = float(roads[0]["codes"]["20"])
        if road == "South":
            assert y < 0, "road below the plan"
        elif road == "North":
            assert y > draw_d, "road above the plan"
        elif road == "East":
            assert x > draw_w, "road right of the plan"
        else:
            assert x < 0, "road left of the plan"
    print("PASS test_dxf_road_sides (S/N/E/W)")


def test_dxf_ascii_and_empty():
    empty = dxf_plan({"ok": False, "placements": [],
                      "plot": {"w": 40, "d": 60, "road": "south",
                               "north_angle": 0.0}})
    assert empty.endswith("0\nENDSEC\n0\nEOF\n"), "empty plan valid DXF"
    assert "No rooms placed" in empty, "empty plan says so"
    dxf, opt = _dxf_and_option()
    rects = [dict(r) for r in opt["placements"]]
    biggest = max(range(len(rects)),
                  key=lambda i: rects[i]["w"] * rects[i]["d"])
    rects[biggest] = dict(rects[biggest], features=["\u09aa\u09dc\u09be\u09b0 \u0998\u09b0"])
    uni = dxf_plan({"ok": True, "placements": rects,
                    "open_plan": opt.get("open_plan", []),
                    "glass_partitions": opt.get("glass_partitions", []),
                    "plot": {"w": 40, "d": 60, "road": "south",
                             "north_angle": 0.0}})
    try:
        uni.encode("ascii")
    except UnicodeEncodeError:
        raise AssertionError("DXF stays ASCII-only")
    assert "?" in uni, "non-ASCII feature replaced, file intact"
    print("PASS test_dxf_ascii_and_empty")


def main():
    test_dxf_envelope()
    test_dxf_rooms_labeled()
    test_dxf_openings_match()
    test_dxf_road_sides()
    test_dxf_ascii_and_empty()
    print("5/5 dxf tests pass.")


if __name__ == "__main__":
    main()
