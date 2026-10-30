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

## Architect review round 1 (12 rules from the T1 plans)

All 12 implemented, PROJECT.md rules 22-33, review/ SVGs re-saved,
27/27 tests pass (new test_architect_round1; T1-T6 re-run green).

What changed per rule:
1. Doors hug corners (best-corner side wins), hinged corner-side, leaf
   against the wall; never centered.
2. Kitchen windows join toilet windows in never facing the road (new
   rule 21, checked; placement bans the road wall).
3. Wardrobe/store opens to its bedroom; attached baths route through
   it where it sits between (rule 7 accepts the chain). Bands
   wardrobes, which never touch a bedroom, open to family/dining
   instead (see open point 4 below).
4. ROOMS vs SPACES: no doors between foyer/living/dining/family - wide
   openings with 2 ft stubs (runs under 6 ft stay solid). Rule 11
   judges bedrooms singly + the whole open area pooled.
5. Kitchen always enclosed, never to living: living+kitchen combines
   are refused (SKIPPED + glass-to-dining note); kitchen+dining/family
   combines become 6 ft+ glass partitions with a slider (rule 4
   passes via glass). T2A/B honestly fail 4+12 (kitchen off dining).
6. Kitchen door at the far-from-living corner (placed + rule 4 checks
   it on 6 ft+ bearings).
7. Foyer side glazing placed (E/W, 3 ft); foyer joins rule 20. Foyer
   extension into front space NOT built ("may" + rule 9 gardens take
   the leftover instead).
8. Verified: strips already stagger (new test pins a side room off the
   spine lines); no alignment is forced anywhere.
9. Leftover plot (setbacks + front corners) drawn light green; wished
   gardens filled green too.
10. Front bedrooms take the road-side window first (rule 6 fails only
    when one would have fit).
11. Variety glass + slider dining-family on exactly one option (C
    first; silent when no 6 ft run exists - T4/wide bands).
12. Family living gets its 5 ft window on the back (N) wall first.

Incidental test updates (all justified by the new rules): 45x55 merge
asserts -> SKIPPED + glass note; T2 bar likewise; T2-C garden now MET
(its no-garden variant was an emergent merge ordering, gone with the
refused merge) and misses only 17 (windowless middle dining, known
limit); bath asserts accept dressing chains.

Open points carried forward: T6 still UNLIVABLE (5/16/19, decision 1
above stands); T5 still an honest skip (decision 2); band kitchens off
dining still fail 4+12 (decision 3); NEW: bands wardrobes open to
family, not a bedroom - accept, or re-zone bands so each wardrobe sits
between its bath and bedroom?

## Architect decisions round 2 - part 1 (Oct 31, committed, not pushed)

Items 9 and 5 done; items 3/4/6/7 mostly done (26/28 tests pass - the
2 fails are one stuck point, see below). Items 1, 2, 8 and the review
re-save land in part 2.

Done:
- Item 9 (rotated drawing): overall dims now sit on the per-road edges
  (N/S below+left; E left+below; W right+below) so labels never
  collide; landscape cells oversized 1 unit to kill hairline grid
  seams on rotated plans. New test_svg_dimensions_rotated.
- Item 5 (T returns + bearings): door frames may sit at partition
  T-junctions with a 3 in return (architect allowed 3-4 in; 3.5 in
  broke front-master bands, so 3 in); 3 ft doors need 3.5 ft bearings
  in the stacker, fatal proxy and scorer alike (the kitchen trusts no
  nudge anymore - the nudge only rescues an already-placed 3.0).
- Item 3 (kitchen-dining hard rule): rule 4 is verdict-hard; band
  plans re-zoned so the kitchen always sits next to dining (front
  [kitchen, dining, ...]; C runs [living, foyer, dining, kitchen]
  with the kitchen ending the row so no path crosses it); the common
  toilet sits beside family; front-master bands already complied.
- Item 6 (enclosed kitchen + glass): kitchen pairs stay out of
  open-plan merge; glass/slider to dining or family AND the swing door
  into dining is always kept (test now pins door + glass together).
- Item 7 (wardrobes/ensuite): paired strip tops embed a 2.5 ft
  dressing band (pair fixed at 8.5 ft: 6 wet + 2.5 dressing) so Bath
  1 keeps Bath->wardrobe->bedroom; rule 7 accepts via-dressing touch
  (3 ft+ on each side, reported).
- Item 4 (pantry) partial: the residual band store lands under the
  kitchen on A (adjacent, opens toward it); B/C place it away from
  the kitchen - moving it under the kitchen is still open (part 2).
- Incidental: shrunk pass (10,10)->(10,11) (10x10 is square on 10 ft
  strips) with computed master need; T6-C now LIVABLE via the shrunk
  master (A/B still 19-blocked); T6 pins updated to per-label
  reality; T6-C 19 pin and the T2-C glass-door pin flipped to match
  round-2 behavior (documented in the tests).

STUCK (30-minute rule - do not debug further without a new idea):
test_front_facing_master + test_angle_30_south_wish, option C (45x55
South, south-master wish, three-strip): rule 19 FAILS (Bedroom 1
126 sq ft vs Bedroom 2 180 sq ft). Pass-1 winner is correct except
sizes; the grow pass forces bed1 to 15 ft (breaks bed3/kitchen
bearings, fatal2, rejected); the shrunk pass stacks a 19-OK tribe
but reports fatal2=1 (one bearing miss) and is rejected - while a
direct probe of the same order/bounds/spans reports fatal2=0 and
accepts. The probe-vs-real divergence survived 60+ minutes: order
slots, bounds, spans, base_min, tops, bath extras were each verified
or ruled out; the printed real second tribe (top 45, bottom 6.0)
bears 3.5+ on every slot by hand computation, yet f2=1. Suspects
left: the real winner-order differs from the probed one in a slot
detail never printed, or a spans/base_min input differs from what
the final geometry implies. Next idea when resuming: print the full
second tribe WITH per-slot fatal reaches inside the real run until
the missing slot is isolated - then fix that slot's bound, not the
pass logic.

Part 2 finished below (items 1+2, pantry, re-save done; item 8
blocked under the 30-minute rule; rule-19 C still stuck).

## Architect decisions round 2 - part 2 (Oct 31, final; committed, not pushed)

26/28 tests pass (same 2 stuck-point fails as part 1 - the "27/28"
in PROJECT.md's part-2 line was a miscount, corrected); T1-T6
review/ re-saved: all 18 options LIVABLE.

Done:
- Item 1 (T6): all three LIVABLE WITHOUT the L-wing. Root cause was
  a one-line bug: _master_bounds filtered baths by _room_type
  "toilet", which never matches type "bathroom", so pass-2 never
  shrank the common bath on A/B (rule 19). Filter now on
  type == "bathroom" (typology.py). test_t6 strengthened: all
  LIVABLE, rules 7/12/19 PASS (every bedroom door opens into family
  living - the architect's clause). The permitted second-hub L-wing
  was not needed.
- Item 4 (pantry) complete: corner Stores open to the kitchen first
  (openings.py; Wardrobes keep bedroom-first per item 7); rule 4
  allows the pantry door alongside dining + own veranda (layout.py).
  Pinned in test_doors_windows_placed (T1-A Store -> Kitchen).
  The ensuite bath then doors directly to its bedroom (allowed).
- Item 2: T5 compact two-strip, 3 livable (committed earlier).
- review/ re-saved via save_review.py (18 LIVABLE SVGs + NOTES.txt);
  stale T6 UNLIVABLE SVGs deleted.

BLOCKED (30-minute rule, reverted to keep the suite green):
- Item 8 (kitchen veranda never road-side): banning wall S leaves
  the 40x60 North A/B/C kitchens veranda-less (their only exterior
  wall with space outside is S), so rule 13 hard-fails and all three
  go UNLIVABLE. Worse, a probe shows a compliant W-wall veranda FITS
  the shipped B geometry, yet the shipped option lacks it - shipped
  rooms/notes mix passes (same family as the stuck point below).
  The proper fix needs strip-margin typology work (house narrower
  than buildable on the kitchen side) plus the pass-mixing resolved.
  Both edits reverted; tree verified clean before the pantry change.

STUCK (unchanged from part 1): test_front_facing_master +
test_angle_30_south_wish option C (45x55 South south-master wish,
rule 19: Bedroom 1 126 sq ft vs Bedroom 2 180 sq ft). The T6
bath-filter fix did NOT move it (equal baths there): the shrunk
stack is 19-OK in a direct probe (fatal2=0) but the real run
reports fatal2=1 on the same tribe. Do not debug further without
a new idea.

Commits this round (none pushed): part 1 (items 9+5, 3/4/6/7
progress), part 2 item 2 (T5), part 2 item 1 (T6), this final
(pantry, re-save, docs). See git log for hashes.

## Night of Oct 31 (queue TASKs 1-6; PC restarted mid-TASK 4, resumed)

All six tasks done, committed one by one, nothing pushed (you push
from your own terminal). Suite after every task: **33/35 pass** -
the 2 fails are the same stuck pair as round 2 (rule-19 option C,
do-not-debug), nothing new broke. Zero live API calls from the
resume session (TASK 2's live render check ran before the restart).

Commits tonight: `086e780` (TASK 1), `4cb663f` (TASK 2),
`4981c59` (TASK 3), `8c2bd23` (TASK 4), `462edda` (TASK 5),
plus this report (TASK 6).

Done:
- TASK 1 (kitchen veranda variants): road-only kitchens now vary
  by option - A keeps the veranda drawn/labeled with a jali
  screen wall, B moves the kitchen so its veranda sits off-road,
  C drops the veranda for a non-road window. Noted per option;
  kitchen windows still never face the road. New
  test_kitchen_veranda_variants.
- TASK 2 (exterior render): per-option "Generate exterior
  concept" button, prompt built from the plan (plot, road,
  porch, verandas, flat roof, jali noted), spinner + per-option
  cache + friendly errors. Mocked test_render.py; verified live
  before the restart.
- TASK 3 (deploy-ready): key from st.secrets first, then env;
  requirements pinned; no local paths; DEPLOY.md with the exact
  click-by-click Cloud steps. Not deployed - you do that.
- TASK 4 (demo polish, finished after the restart): subtitle
  "A concept house planner for Bangladesh, built with an
  architect's rules"; "Try an example" fills 40x60 / road North
  / 3 bed / 3 toilets; A/B/C side by side with one-line
  summaries; rule tables already under expanders; concept-only
  notes top and bottom; spinners on all three waits; no raw
  errors anywhere (friendly text + hidden technical expander).
  Verified by compile + full top-level run + suite (below).
- TASK 5 (voice brief): mic input above the wishes box; a new
  recording transcribes once and fills the box (your edits after
  that are kept). Built against Meta's official docs ONLY
  (speech-to-text + transcribe reference): multipart parts
  `request` (model/audioEncoding/mode JSON) + `audio`; WAV-only
  endpoint, so voice.py normalizes any WAV to mono 16-bit
  24 kHz with the standard library (no ffmpeg, Cloud-safe).
  Mocked test_voice.py (3 tests); NO live call made - you must
  test with a real microphone (decision 1).
- TASK 6 (docs): README (Image + Voice, 35 tests, Oct 31
  history), PROJECT.md (status, files, voice shape, checklist),
  this section; review/ re-saved (6 SVGs redrawn by the
  variants, still 18/18 LIVABLE).

Stopped by rule (not by cap):
- Boot/smoke tests: PERMANENTLY SKIPPED from now on, per your
  new rule. What happened: the pre-restart "boot app headless"
  probe never returned (Start-Job + fetch hung, then the PC
  restarted). After the resume I tried twice more with a 60 s
  cap and guaranteed tree-kill (server-only, no browser at
  all): both failed fast inside the sandbox - Windows blocks
  ALL socket creation here (WinError 10013), so Streamlit
  cannot even build its event loop, and streamlit's own
  AppTest fails the same way. No server or browser was left
  running (ports verified free). TASK 4 is instead verified by
  py_compile + a full bare run of app.py (every top-level line
  executes clean) + the 33/35 suite. Please run `streamlit
  run app.py` once yourself and click through it.

Decisions needed (owner):
1. Voice live test: record a real brief - does the transcript
   land in the wishes box? (If the browser sends non-WAV, the
   app shows a friendly "record again or type it" message;
   tell me and I'll add an ffmpeg conversion step.)
2. Deploy to Streamlit Cloud with DEPLOY.md, then confirm the
   public link + Secrets key work.
3. Demo video (Nov 4): exterior render + voice brief are both
   in - pick which one stars in the recording.

