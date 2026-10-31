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

## Wide shallow plots (Nov 1, T7; committed, not pushed)

Your brief (70x40, road East, 3 bed/3 bath, kitchen/reading/
gaming wishes) built nothing: strips need 29 ft depth (have 25)
and bands failed with "front rooms cannot fill 61 ft width".
Fix in this commit (34/36 tests, same 2 stuck fails; 20/20
review SVGs livable, incl. new T7 A/B):

1. Leftover width is landscape now (typology.py): exact row
   fills still rank first (old plans byte-identical: no T1-T6
   SVG changed); partial fills leave the row end as garden
   (3 ft+), and back-row slack over 6 ft becomes a Court, so
   the built footprint reads as an L (two wings, court in the
   open corner). The wished-garden check now needs the
   garden_for flag so leftover landscape never fakes a MET.
2. Dining-second retry (typology.py, one recursion, only when
   plain bands fail): front kitchen/dining/foyer/living so
   dining joins the open spaces; the back row splits its last
   bedroom ahead of family under dining, the common sits
   beside family, and family must overlap a space by 6 ft+.
   Attempt 1 (dining-LAST) built A/B but islanded dining
   (rules 12+16); the island is structural at the row end, so
   attempt 2 moved dining second - A/B LIVABLE, zero fails.
   T7-C stays honestly skipped (its mirror order strands a
   bedroom); widely spaced bedrooms cannot all share one row
   on 60 ft+ widths, which is why the retry reorders instead
   of stretching.
3. Rules untouched: the same checker verdicts everything
   (T7 pins 4/5/7/13/16/19 PASS-or-bend, kitchen by dining
   with no living touch, master 10%+ biggest).
4. Features drawn (layout.py carries them, draw.py writes up to
   2 italic lines when the room fits): "reading corner" and
   "gaming setup" show inside Family Living and Bedroom 1 on
   the T7 plans.
5. T7 added (test_layout.py + save_review.py + 2 review SVGs).

Also: placer/skip messages moved into a collapsed "Technical
notes" expander in app.py; the no-fit case shows only its one
friendly sentence (reasons stay one click away). Per-option
notes were already inside collapsed detail expanders.

Open: if you want T7-C built too (a 3rd compare option on very
wide plots), say so - it needs a side-wing typology, a bigger
change than this fix.

## Rules 34/35 + big master toilet (Nov 1; committed, not pushed)

36/38 tests (same 2 stuck fails, zero regressions); all 20
review SVGs re-saved with the new foyer zones and door swings
(verdicts unchanged, T1-T7 still all livable).

Rule 34 - foyer inside living (typology.py, openings.py,
draw.py): foyer+living are always merged into one open pair
(no wall, stub or door between them); the foyer draws as a
gray labeled zone (floor-finish change, name only, no
dims/area); the entry door sits at the foyer corner nearest
the living room (new "faronly" fit with an any-corner
fallback). Checker untouched: foyer stays a node for rules 5
(still never entered from a bedroom) and 16, and the goal
still sees porch + foyer.

Rule 35 - veranda doors swing out (openings.py): bedroom and
kitchen veranda doors now swing into the veranda (corner-hug
kept). The checker never read swing direction, so only the
drawing changed; pinned in test_foyer_zone_veranda_swing.

Big master toilet (typology.py, test T8): "big ... toilet ...
master" is now a detected wish. The master bath keeps up to
6'-6" x 10'-0": width from the program (capped), depth grown
by stack scoring that still lets door bearings dominate, so
tight plots shrink it honestly instead of breaking doors.
T8 (your 50x50 case): A/B MET at 6.5 x 10.0, C honest NOT MET
at 6.5 x 7.5, all livable. wish table never 0/0 for it again.

Also (app.py): two-option plots show "Two layouts fit this
plot shape." under the options. No side-wing typology built,
per your instruction.

## Friendly labels + master-role swap (Nov 1; committed, not pushed)

39/41 tests (same 2 stuck fails, zero regressions); review/
re-saved 20/20 OK with the new _OK/_REVIEW names (old
_LIVABLE files removed; your 2 copy.jpg untouched).

Labels: LIVABLE/UNLIVABLE never reach users anymore. Green
"All key rules met", amber "Needs review" + one plain
sentence per failed hard rule ("Master bedroom is smaller
than Bedroom 3", "Kitchen door does not open into dining",
...). Internal verdict booleans, ranking, rules-table
PASS/FAIL words, and test/console wording are unchanged.

Master-role swap (typology.py _try_master_swap, tried on
every option, kept only when rule 19 is fixed AND the fail
set strictly shrinks): the largest bedroom takes the master
name and each attached bath keeps its physical bedroom; a
full re-check gates acceptance. New 49x51 test: A/B fail
ONLY 19 with the bigbath wish MET, C livable, swap correctly
declined. Why declined (proven, 3 angles): the big bath
(6.5x9.5) sits on Bedroom 1, so any swap detaching it fails
rule 18 (master-only bounds); re-attaching it to the far
bedroom fails rule 7 (no shared wall); and Bedroom 3 needs
>=14.5 ft depth for its door bearing but <=13.6 ft for rule
19 at master-max - jointly unsatisfiable in A/B's strip
arrangement. The shrunk second pass already finds 19-clean
sizes but correctly rejects them (a real bearing breaks).
If you want A/B green anyway, the options are: (a) let the
swap accept a rule-18 FAIL (non-verdict) as the honest price,
(b) shrink the big bath (loses the MET wish), or (c) a new
side order for the third bedroom - say which.

## Pre-deploy check (Nov 1; committed, not pushed)

1. SECURITY: clean. `.env` was never tracked or committed (no
   history); the 5 commits mentioning `META_API_KEY` carry only
   the name plus `your-key-here` placeholders (verified by
   value length, values never printed); no `sk-` strings in
   history. `.env` and `.streamlit/secrets.toml` are both in
   `.gitignore` (explicit rules, verified with check-ignore).
2. Missing key: the app opens without a key (no top-level key
   use) and Generate now shows "The AI service is not
   configured" + where to put the key, then stops - no crash.
   Verified by simulation: empty key reads "", the AI call
   raises a friendly catchable error. (No server smoke test:
   sandbox blocks sockets.)
3. requirements.txt: exact match - streamlit, python-dotenv
   and openai are the only third-party imports (app, AI,
   render), all pinned; placer/drawing/voice/tests are
   stdlib-only, so nothing test-only is required.
4. DEPLOY.md: fixed 2 gaps - added the Python 3.13 version step
   (matches local 3.13.2 + requirements) and the new
   not-configured message. Main file app.py and secret
   META_API_KEY already matched.
5. README: test counts corrected (41: 35 layout incl. T1-T8 +
   3 + 3) and a Nov 1 line added (wide plots, rules 34-35,
   bigbath, friendly labels, master swap).
6. Suite: 39/41 (same 2 stuck fails). Ready to push + deploy
   with DEPLOY.md; the owner still owes one live mic test.

## Session-state results (Nov 1; committed, not pushed)

Cloud bug: "Generate exterior concept" reloaded the app to the
empty start state - every button click reruns the script and
the results only existed inside the Generate branch. Fixed in
app.py: Generate now stores the room program + built options
in st.session_state under a brief fingerprint (size, north,
bedrooms, toilets, wishes); the whole results section renders
from state on every rerun. Any input change clears stored
results, so old plans never show for a new brief. Exterior
buttons (unique key per option) keep their per-option image
cache, so renders survive reruns; spinner + friendly error
kept. Button audit: "Try an example" and voice fill inputs,
so the fingerprint clears stale results for them
automatically; exterior correctly exempt (same brief).
Tests: test_session_state_helpers covers the fingerprint +
store/stale/clear lifecycle directly (AppTest is socket
blocked here). Suite 40/42, same 2 stuck fails.

Tool folders: .agents/.eden/.hg/.muse/.sl were all empty and
untracked (nothing to untrack, nothing deleted); added all
five to .gitignore so they can never be committed.

## Rendered floor plan experiment (Nov 1; committed, not pushed)

STEP 1 only: the app is unchanged, nothing is wired in. New
script exp_render_plan.py exports a T1 option as a PNG line
plan (Pillow, same scale/margins/transform as draw.svg_plan:
walls, door leafs + swing arcs, windows, veranda/porch
outlines, plot boundary; no text, no dims), sends it to Muse
Image EDIT mode (POST /v1/images/edits, model muse-image-1.0,
OpenAI-compatible client.images.edit, size 1024x1536), then
overlays the exact wall bands + room-name labels at the same
coordinates. Pillow is pure pip (no system package), so this
path works on Streamlit Cloud with no packages.txt. The
overlay is redrawn with PIL at the same coordinates rather
than rasterizing the SVG (avoids cairosvg system libs).
Cost: 3 image calls used of the 6 allowed (T1 A/B/C, one
each). The model returned 1280x1920 (same 2:3 aspect,
1.25x upscale), so overlays align after a plain resize.
Files: review/renders/T1_{A,B,C}_{input,raw,overlaid}.png.

Fidelity (judged by eye on all 3 pairs):
- Walls/doors/windows: EXCELLENT. No wall moved, no room
  added or removed in any option; the overlay bands sit
  exactly on the AI's walls. The AI even kept door gaps,
  window positions and the jali veranda, and obeyed "No
  text" (raw images carry no text).
- Room functions: MIXED - this is the one real problem.
  The input plan has no labels, so the AI guesses each
  room's function from size/position and always puts the
  kitchen in the wrong room: in A and C the real kitchen
  got living-room furniture (sofa/dining set) while a
  bedroom got the stove/sink/counters; B mirrors the same
  swap and additionally put a toilet inside the
  bedroom-turned-kitchen. Entry/foyer in A got a bed;
  one bed intrudes into a veranda in B. Toilets, living,
  dining and family-living furniture are right everywhere.
- Furniture scale: GOOD where the function is right
  (beds, sofas, dining sets, toilet fixtures all fit
  their rooms); wrong only where the function is wrong.
- Outdoors: A/B got lawn + plants as asked; C paved most
  of the plot as patio instead of lawn (acceptable but
  worth a stronger "lawn, minimal paving" line).
- Style note: the AI renders walls with 3D height and
  shadows (cutaway look), not a flat plan. It looks like
  a client presentation image, arguably better than flat.

Recommendation for STEP 2 (needs architect approval, would
spend 1-2 of the 3 remaining image calls to verify): put
room-name labels (or a room list with positions) into the
input PNG or the prompt so the AI furnishes the right
rooms; the overlay already redraws clean labels on top.
STOPPING here for review as instructed.

## Render experiment round 2 (Nov 1; committed, not pushed)

Still an experiment: the app is unchanged, nothing is wired
in. Changes from round 1, all in exp_render_plan.py: the
input PNG now carries gray furniture outlines per room type
(bed + side tables + wardrobe; kitchen counter + stove +
sink; WC + basin + shower; sofa + coffee + chairs; dining
table + chairs; chair + plant on veranda/porch; foyer zone
empty), each piece kept clear of door-swing/approach boxes;
prompt switched to a strictly flat orthographic view with
lawn + minimal paving; overlay is room-name labels ONLY
(collision-free: larger rooms win, smaller shrink or skip),
no walls. Same 9 files in review/renders/ replaced in
place. Cost: 3 more image calls (6 total across rounds 1+2,
at this task's cap).

Fidelity (judged by eye, all 3 pairs + temp red-outline
drift checks, since deleted):
- Furniture in the right rooms? PARTLY - big variance
  between calls. A is near-perfect: kitchen has the
  counter/stove/sink, all 3 bedrooms have beds, living /
  dining / family all correct. B kept the kitchen counter
  but ADDED a full bed + wardrobe to the kitchen, and put
  a dining set in the living room instead of the sofa set.
  C repeated the round-1 swap: a bed in the kitchen and a
  kitchen island with stools in the living room, plus a
  dining set in family living instead of sofas. Small-box
  misses in all 3: the jali veranda (A) rendered as a
  bathroom; filler store boxes got a spare WC; a few
  doubled basins and 2 extra dining chairs. Beds render
  correctly 100% of the time; counters and sofa groups
  are obeyed in A but reinterpreted in B/C - the AI seems
  to classify the room first (from shape/position) and
  furnishes from its own guess, treating outlines as a
  suggestion rather than a command.
- Walls aligned? YES. Drift checks show the AI's walls
  within a couple of pixels of ours in all 3 options - no
  thin-outline overlay needed. One style note: A kept the
  input's black wall bands, B and C redrew them as thin
  white walls (positions identical, color inconsistent
  call to call).
- Double walls gone? YES - flat prompt plus labels-only
  overlay; no doubling anywhere.
- Lawn? YES. All 3 have lawn + plants with only a short
  path (C added a second rear path where no porch is -
  minor). No text in any raw image, as prompted.

Honest conclusion: furniture outlines alone do not
reliably control the AI (1 of 3 fully compliant). If a
round 3 is wanted, the next thing to try is room-name
labels drawn INTO the input image (the AI can read; the
"label" is input, the "No text" rule still covers the
output), possibly with more distinctive outline shapes
for sofas vs dining sets. STOPPING here for review.

## Render goal rounds (Nov 1) - all rooms right, A+B+C

Baseline (round 2 above): outlines only, 1 of 3 compliant
(A good, B/C improvised). This task: iterate until A, B
and C are all correct in one round. Score = every room has
its own furniture, nothing room-wrong, walls aligned, lawn,
no text. Small extras that belong to the room (fridge in
kitchen, TV in family living, a plant) do not fail a room;
wrong-room furniture (bed in kitchen) or a WC in a store
does. Foyer should stay near-empty (input draws nothing).

### Round 1: room names in the INPUT + shelves (kept: helps)

One change (input annotation): every room's TYPE name in
large letters centered in the input ("Bedroom", "Kitchen",
"Bathroom", "Store", "Wardrobe", "Veranda", ...); prompt
gains one clause (use the written names; OUTPUT still has
no text). Plus the standing small-space rule: stores and
wardrobes get shelf outlines only, never empty (empty boxes
invited spare WCs). Overlay labels cleaned ("Wardrobe",
"Store"). Cost this round: 3 image calls (task total 3/30
image, 0/30 Spark).
- A: CORRECT. 15/15 rooms right: kitchen counter/stove/
  sink/fridge, 3 beds, sofas, dining set, all baths,
  Store = boxes/shelves, Wardrobe = closet, Veranda =
  chairs + plants. Extras: foyer chair + console, +2
  dining chairs, fridge, TV console. Walls aligned
  (white style). Lawn + path, one spare rear path. No
  text in raw.
- B: CORRECT. 15/15 rooms right: kitchen counter, NO bed
  (round-2 failure fixed); living = sofa set (round-2
  failure fixed); baths, Store shelves, Wardrobe closet,
  Veranda patio all right. Extras: foyer console, Store
  reads as utility nook, +chairs. Walls aligned (black
  style). Lawn + path. No text.
- C: CORRECT. 15/15 rooms right: kitchen counter, NO bed;
  NO kitchen island in the living room (round-2 failure
  fixed); family = sofa set; baths, Store, Wardrobe,
  bedrooms all right. Extras: 2 foyer armchairs,
  Wardrobe has a desk. Walls aligned (black). Lawn +
  path. No text.
Verdict: 3/3 CORRECT - SUCCESS in round 1. No further
rounds needed (ideas 2-4 untried, kept in reserve).

### Auto-check + wiring (same task, committed)

Built once round 1 hit 3/3: check_render() sends the
labeled final + room list to Muse Spark vision (Responses
API, input_image block, base64 data URL, JSON verdict per
room) and render_plan_checked() retries the render at most
twice, keeping the most-rooms-ok image (plan_render.py,
renamed from exp_render_plan.py; 8 mocked tests in
test_plan_render.py, all pass). Checker debugging, all
verified live: the model echoed "Name (Type)" list lines,
so the list is now names only; it returned failures only,
so the prompt demands every room; its ~2.5k thinking
tokens ate the first output cap (empty replies), so
max_output_tokens=8000. Live proof: round-1 C scores
all-ok; round-1 A/B flag only real minor extras (foyer
bench, store basin, porch bench, one disputed store WC);
and the known-bad round-2 C scores 5 rooms wrong with
exactly the failures I judged by eye (bed in kitchen,
island in living, dining set in family living, basin in
store, empty wardrobe). Task cost: 3/30 image calls,
12/30 Spark calls.
Wired into the app: per-option "Render this plan" button
(+ "Regenerate" once rendered), spinner, caption "AI
presentation render - check against the plan", auto-check
note under each render, results cached in st.session_state
per plan (old "exteriors" cache abandoned; render.py kept
for history but no longer called). requirements.txt gains
pillow==13.0.0 (else Cloud crashes on the new import).
Tests: 8/8 new mocked pass; layout 34/34 runnable pass
(test_layout.py still aborts at the known stuck
test_front_facing_master, pre-existing, untouched code);
render + voice suites pass; app bare-imports OK.

## Client-friendly wording + simple render (Nov 1; committed, not pushed)

Two parts, one commit ("Client-friendly wording, simple
shape-matched plan render"). No push, no server/browser
smoke (standing rule), no debug leftovers. Image cost: 4
real calls of the 8 allowed (T1-A, T7-A, WIDE-A x2).

PART 1 - wording (app.py only; logic/ranking untouched):
scores, rule numbers, "hard fails", fail/bend, PASS/FAIL,
"wishes 0/0" and model names are gone from the page (a
literal scan of app.py confirms none remain in displayed
strings; "Technical notes/details" expanders stay technical
by design). Each card now shows: a plain title ("Kitchen
on the west side", "Master bedroom at the front, west
side", "L-shaped plan with a garden court", ... all 7
title shapes mapped + veranda suffixes), the badge with
its plain sentences, "Your wishes: X of Y included" only
when wishes were read, and up to 3 translated design
notes (whitelist; builder notes like "dining-second
retry" never show). The rule table is now "Option X:
Architect's checklist" with plain names and Met / Not met
/ Partly, no numbers; wishes read Included / Not
included / Not advised. Also planed: "Generate plans",
"Space check", "Room sizes", "Toilets", plain toilet-use
("Family toilet", "Toilet for X"), plain spinners and
area warning (ai_program.py string only, unpinned).

PART 2 - simple render (plan_render.py + app.py wiring):
input = the client-visible plan redrawn as PNG (walls,
doors, windows, room names + sizes; same geometry as the
SVG; no furniture outlines, dims or road labels so the AI
copies no text), white-padded to a shape-matched size -
landscape 1536x1024 / portrait 1024x1536 / square
1024x1024 by the DRAWN aspect after road rotation (within
10% = square). One Image edit call with the one-paragraph
prompt + the client's extra instructions from a new per-
option text box; plan and render show side by side with
the "check against the plan" caption; results stay in
st.session_state (cache key includes the instructions, so
edited text + Render gives a fresh image). Old path
(furniture outlines, label overlay, vision auto-check +
retries) kept in-file for history; its 8 mocked tests
kept green, 5 new mocked tests added (13/13).

Bug note: the old fixed portrait canvas both clipped
tall-drawn plans (T7's content is taller than 1536px) and
invited rearrangement on wide-drawn ones. New code never
clips (downscale-to-fit, then pad) and the output aspect
always equals the input aspect. T7 draws portrait (road-
East stands the wide plot upright), so the landscape path
is proven live by WIDE-A (60x40 South).

Live verdicts (review/renders/*_simple_*.png, judged by
eye against the inputs; model returns 1.25x upscale at
the same aspect, resized to target):
- T1-A (tall): MATCH with minor nits. All rooms, walls
  and doors in place, no copied text, lawn + plants. Nits:
  the Store/Bath-2 pair subdivided as 1 store + 2 WC
  cubicles instead of 1+1, and Bedroom 1 furnished as a
  study (walls/door correct).
- T7-A (wide plot): MATCH. Every room in place with
  fitting furniture, garden rendered as lawn, no text.
- WIDE-A (landscape): SHAPE FIXED but PARTIAL room match,
  twice the same way (original + 1 retry): bedrooms,
  kitchen, living, baths and verandas all correct, but the
  labeled Dining room misreads as baths + wardrobe while
  the dining table merges into the living space; a garden
  path also appears at the back. Systematic, not variance
  - left as a known limit (the caption + Regenerate stay);
  no prompt change, no more calls spent.

Tests: layout 34/36 (same 2 stuck fails, verified by
running all 34 others explicitly - the file's own runner
still aborts at the first stuck one, pre-existing),
render 3/3, voice 3/3, plan-render 13/13. Total 53/55.

