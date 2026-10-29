# Night report (Oct 29–30 overnight queue)

All four tasks attempted in order, committed one by one, nothing pushed
(you push from your own terminal). Full suite green after every task:
**26/26 tests pass.**

Commits tonight: `7049e9a` (TASK 1), `673d994` (TASK 2), `3fb0191`
(TASK 3), plus this report.

## TASK 1 — Regression set T1–T6: done (with one honest gap)

- `test_t1`–`test_t6` added to `test_layout.py`; `save_review.py` writes
  `review/` (15 SVGs + `NOTES.txt`, one file per option).
- **T1–T4: all LIVABLE with every clear wish MET.** T2/T4 compare-C
  options stay LIVABLE by design while missing wishes (ranked lower).
- **T5 (30×50 North, narrow): honest skip, no broken plan.** Side rooms
  need ~54 ft of depth, 40 ft exist; all three options skipped with the
  shortfall stated. Encoded in the test.
- **T6 (50×70 West, 4 bed): honest UNLIVABLE, wishes MET.** Both wishes
  (garden ✓, bedroom near family living ✓ — new "X near Y" wish type,
  evaluated by a door-able shared wall) are MET on all options, but the
  4-bedroom spine strands back bedrooms (rules 5, 16) and ties the
  master (rule 19). Fixing needs a new typology move — see decision 1.
  Per the 30-minute rule I documented it and moved on.
- Test expectation changes (contract evolved under TASK 2's explicit
  order to really check doors/windows — old assertions encoded the
  PENDING era, details in git log):
  - rule 5 `PENDING` → `PASS` (doors now modeled);
  - wide-band C zero-fails → `["4", "12"]` (band kitchen away from
    dining + 3 ft corner store — both honest, non-verdict, C livable);
  - T6 pins rules 4+12 FAIL alongside the verdict (flip together later).

## TASK 2 — Walls, doors, windows: done

- New `openings.py`: one placement, two readers — `draw.py` renders the
  gaps, `layout.py` checks them, so drawing and checker can't disagree.
- Walls: 10 in exterior / 5 in interior solid black bands; open-plan
  pairs share no wall. Doors: entry 3'6" porch→foyer, room 3'0", toilet
  2'6", veranda 2'6", leaf + swing arc, 4 in off true corners, no
  clashes (re-verified from endpoints by `audit_gaps`). Windows: bed
  4'0" (two preferred, opposite first), living 5'0", dining/family 4'0",
  kitchen 3'0", bath 2'0" high and never road-side; S/SE ranked first,
  west last.
- Rules 4/5/6/7/9/11/12 really check the drawn gaps; new soft rule 20
  (living-space windows + west-glass report). **Zero PENDING** on all 21
  review options (new `test_no_pending_rules`).
- Judgment calls I made (flagged for your review below): T-junction
  partitions get 0 corner clearance (not true corners); hub rooms join
  over whatever shared walls exist (spans strips AND bands); an
  open-merged kitchen needs no dining door; wardrobes are doorless
  infill; middle-spine rooms borrow light (rule 20 bends).
- Placer fix: kitchen slides along the dining wall to a 3 ft door
  bearing when 1–2 ft short (verified + reverted otherwise, noted on
  the option) — saved the 1-bed plans' clean record.
- `review/` re-saved with walls/doors/windows (spot-check: T1-A draws
  97 wall bands + 12 swing arcs, XML valid).

## TASK 3 — README: done

Judges' README: what it is, 4-step pipeline, `muse-spark-1.3` via the
Meta Model API (only AI call; Image/Voice listed as stretch), how to
run, Oct 26–Nov 4 history from git log, AI-coding authorship note. No
key anywhere (only `.env.example`'s placeholder, which was already
there).

## Decisions needed (architect)

1. **T6 4-bed west UNLIVABLE (5/16/19):** allow a new typology move (L
   extension, second family hub, deeper spine rule?) or accept that a
   4-bed west plot honestly fails? Wishes already MET; only the hard
   rules block it.
2. **T5 narrow skip:** accept "side rooms need 54 ft, have 40 ft" as the
   final answer, or relax something (smaller rooms, 2-strip variant)?
3. **Band kitchens away from dining** (wide C, T4C fail rules 4+12,
   stay LIVABLE): accept as honest compare options, or re-zone bands so
   the kitchen always lands next to dining?
4. **3 ft corner store** (wide bands): allow a 2'6" store door, grow the
   store, or open it to the kitchen as a pantry?
5. **T-junction 0-clearance:** a door frame may sit against a partition
   junction (my exception to your 4 in rule) — confirm?
6. **Open-merged kitchen needs no dining door** (T2: one space with
   living) — confirm?
7. **Wardrobes doorless, middle-spine rooms borrowing light** — confirm
   both as designed?
