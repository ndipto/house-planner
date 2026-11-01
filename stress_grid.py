# stress_grid.py
# Stress test: a grid of rule-based briefs through the full app logic.
#
# Run: python stress_grid.py
# No AI calls (no key needed): the room program is built by fixed rules
# from the bedroom count, then each brief runs the exact app path -
# build_options, svg_plan, dxf_plan and the card helpers (_plain_title,
# _friendly_issues, _wishes_line, _design_notes, _checklist_rows).
# Every brief must either yield plans or no options (the app's friendly
# no-fit message); anything else - an exception anywhere - is a crash
# and fails the run. Prints the crash list (if any) plus a coverage
# table: per plot size x bedrooms, options built / "All key rules met".
#
# Grid: 7 frontages x 5 depths x 4 roads x 4 bedroom counts = 560 briefs.

import sys
import time
import traceback

from app import (
    _checklist_rows,
    _design_notes,
    _dxf_for_option,
    _friendly_issues,
    _plain_title,
    _svg_for_option,
    _wishes_line,
)
from typology import build_options

FRONTAGES = [25, 30, 35, 40, 50, 60, 70]
DEPTHS = [35, 40, 50, 60, 80]
ROADS = ["North", "East", "South", "West"]
BEDS = [1, 2, 3, 4]


def _room(name, room_type, width, depth, veranda=False, kind="",
          attached=""):
    """One AI-shaped program room with the fields layout.py reads."""
    return {"name": name, "type": room_type, "width_ft": width,
            "depth_ft": depth, "adjacencies": [], "door_opens_into": "",
            "needs_veranda": veranda, "preferred_orientation": "",
            "features": [], "bathroom_kind": kind, "attached_to": attached}


BED_SIZES = [(13, 14, True), (12, 13, True), (11, 12, False),
             (10, 11, False)]


def _program(bedrooms, toilets):
    """Fixed rule-based program: hub rooms + N beds + exact toilets."""
    program = [
        _room("Porch", "porch", 8, 5),
        _room("Foyer", "foyer", 8, 10),
        _room("Living Room", "living room", 13, 14),
        _room("Dining", "dining", 11, 13),
        _room("Kitchen", "kitchen", 10, 13, veranda=True),
        _room("Family Living", "family living", 13, 14),
    ]
    for index in range(bedrooms):
        width, depth, veranda = BED_SIZES[index]
        program.append(_room("Bedroom %d" % (index + 1), "bedroom",
                             width, depth, veranda=veranda))
    program.append(_room("Common Toilet", "bathroom", 7, 8,
                         kind="common"))
    for index in range(1, toilets):
        program.append(_room("Bath %d" % index, "bathroom", 7, 8,
                             kind="attached",
                             attached="Bedroom %d" % index))
    return program


def run_brief(frontage, depth, road, bedrooms, toilets):
    """One brief through the app path; returns (options, green)."""
    result = build_options(_program(bedrooms, toilets), frontage,
                           depth, road, toilets, "")
    plot = result["plot"]
    green = 0
    for opt in result["options"]:
        _svg_for_option(plot, opt)
        _dxf_for_option(plot, opt)
        _plain_title(opt)
        _friendly_issues(opt)
        _wishes_line(opt)
        _design_notes(opt)
        _checklist_rows(opt)
        if opt["livable"]:
            green += 1
    return len(result["options"]), green


def main():
    started = time.time()
    table = {}
    crashes = []
    nofit = 0
    done = 0
    total = len(FRONTAGES) * len(DEPTHS) * len(ROADS) * len(BEDS)
    for fw in FRONTAGES:
        for fd in DEPTHS:
            for road in ROADS:
                for beds in BEDS:
                    toilets = beds  # sensible: one toilet per bedroom
                    key = (fw, fd, beds)
                    opts, green = table.setdefault(key, [0, 0])
                    try:
                        built, met = run_brief(fw, fd, road, beds,
                                               toilets)
                    except Exception:  # noqa: BLE001 - the grid catches all
                        crashes.append((fw, fd, road, beds, toilets,
                                        traceback.format_exc()))
                    else:
                        table[key] = [opts + built, green + met]
                        if not built:
                            nofit += 1
                    done += 1
                    if done % 20 == 0:
                        print("... %d/%d briefs" % (done, total),
                              flush=True)
    print()
    print("STRESS GRID: %d briefs in %.0f s, %d no-fit, %d crashes"
          % (total, time.time() - started, nofit, len(crashes)))
    for fw, fd, road, beds, toilets, tb in crashes:
        print("=" * 70)
        print("CRASH: %dx%d road %s, %d bed/%d toilet"
              % (fw, fd, road, beds, toilets))
        print(tb)
    print("=" * 70)
    print("COVERAGE (plot size x bedrooms: options built / green), "
          "4 roads each:")
    header = "plot      " + "".join("  %d-bed  " % beds for beds in BEDS)
    print(header)
    for fw in FRONTAGES:
        for fd in DEPTHS:
            row = "%dx%-6d" % (fw, fd)
            for beds in BEDS:
                opts, green = table[(fw, fd, beds)]
                row += "   %2d/%-3d" % (opts, green)
            print(row)
    return 1 if crashes else 0


if __name__ == "__main__":
    sys.exit(main())
