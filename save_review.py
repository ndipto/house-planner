"""Save the T1-T6 regression briefs' options as SVG files for review.

Run: .venv\\Scripts\\python.exe save_review.py
Writes review/T<n>_<frontage>x<depth>_<road>_<label>_<verdict>.svg
(one file per built option) plus review/NOTES.txt with the verdict,
hard-rule fails and wishes table behind each file. Re-run after
placer/drawing changes (TASK 2 re-saves with doors and windows).
"""

import os

from draw import svg_plan
from test_layout import (_program_4bed, PROGRAM_2BED, PROGRAM_3BED)
from typology import build_options

BRIEFS = [
    ("T1", PROGRAM_3BED, 40, 60, "North", 3, ""),
    ("T2", PROGRAM_2BED, 45, 55, "South", 2,
     "combined living and kitchen for family gathering, "
     "small garden beside the living room"),
    ("T3", PROGRAM_2BED, 40, 60, "East", 2,
     "south facing master bedroom, nice living room"),
    ("T4", PROGRAM_2BED, 50, 40, "South", 2,
     "open living and dining for family gathering. "
     "south facing master bedroom"),
    ("T5", PROGRAM_2BED, 30, 50, "North", 2, ""),
    ("T6", _program_4bed(), 50, 70, "West", 3,
     "garden, elderly parents need a bedroom near family living"),
]


def _svg_for_option(plot, option):
    """Render one option exactly like the app does."""
    return svg_plan({"ok": True, "placements": option["placements"],
                     "open_plan": option.get("open_plan", []),
                     "plot": {"w": plot["width"], "d": plot["depth"],
                              "road": plot["road"],
                              "north_angle": plot.get("north_angle", 0)}})


def main():
    try:
        os.makedirs("review", exist_ok=True)
    except OSError as exc:
        print("cannot create review/: %s" % exc)
        return
    lines = ["House Planner review set (T1-T6).", ""]
    for name, program, fw, fd, road, ntoilets, wishes in BRIEFS:
        result = build_options(program, fw, fd, road, ntoilets, wishes)
        lines.append("%s: frontage %d, depth %d, road %s, wishes %r"
                     % (name, fw, fd, road, wishes or "-"))
        if not result["options"]:
            for note in result["notes"]:
                lines.append("  no option fits: %s" % note)
            lines.append("")
            continue
        for opt in result["options"]:
            verdict = "LIVABLE" if opt["livable"] else "UNLIVABLE"
            fname = "%s_%dx%d_%s_%s_%s.svg" % (
                name, fw, fd, road, opt["label"], verdict)
            with open(os.path.join("review", fname), "w",
                      encoding="utf-8") as handle:
                handle.write(_svg_for_option(result["plot"], opt))
            fails = ", ".join(opt["livability_fails"]) or "-"
            wishes_txt = "; ".join("%s: %s" % (w["wish"], w["status"])
                                   for w in opt["wishes"]) or "-"
            lines.append("  Option %s %-9s fails=[%s] wishes=[%s] "
                         "-> %s" % (opt["label"], verdict, fails,
                                     wishes_txt, fname))
        lines.append("")
    with open(os.path.join("review", "NOTES.txt"), "w",
              encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
