# House Planner

**Owner:** Architect (solo builder, no coding background) + AI coding assistance (see Authorship note below).
**Event:** Meta Global AI Developer Hackathon — deadline **Nov 4, 2026**.
**Status:** Architect review round 1 done Oct 30 (12 rules from the T1 plans; Day 3 done Oct 30 — solid walls (10 in ext / 5 in int), real doors (entry 3'6", room 3'0", toilet 2'6", veranda 2'6") and windows (bed 4'0" x2 preferred, living 5'0", kitchen 3'0", bath 2'0" never road-side); every door/window rule really checked, zero PENDING, new soft rule 20 (living-space windows + west-glass report); T1-T6 regression set green (26/26) with review/ SVGs re-saved. T6 4-bed west stays honestly UNLIVABLE (needs a new typology move — architect decision pending).

This file is the project memory. Muse Code should read it at the start of every session and keep the "Built during the hackathon" section up to date.

**Git rule:** Muse Code must never try to push to GitHub or fix GitHub login. Only commit when asked; the owner always pushes from their own terminal.

## What it is

House Planner is a simple web app for **Bangladesh**, designed by a Bangladeshi architect. The user describes the house they want in plain words:

- Road frontage and plot depth from road (in feet; road-relative, not compass), and north direction (0-360 slider; the road side is derived from it)
- Number of bedrooms and number of toilets (1 to bedrooms + 1, no default — the client must enter it)
- Family needs and wishes in plain words (e.g. "home office", "big kitchen for family gatherings", "elderly parent on ground floor")

The app returns a **single-floor 2D floor plan concept**: three layout options (A/B/C) side by side, each drawn as a clean, dimensioned plan with room names and areas, each with its score and rule report.

The design rules are tuned for Bangladesh's tropical monsoon climate and local living patterns: family living as the bedroom hub, separate verandas, kitchen on the west side, breeze-facing windows. Setbacks in the app are simplified, editable defaults — not full RAJUK rules.

This is a **concept tool**, not construction documents. It helps a family see three possible layouts from their brief in seconds.

## How it works (4 steps)

1. **Brief → room program (AI).** Muse Spark, called through the Meta Model API, reads the user's brief and returns structured JSON: for each room its name, type, target area, min/max dimensions, required adjacencies (e.g. kitchen next to dining), orientation preferences (e.g. bedrooms face south/southeast), plus a short "design reasoning" paragraph written in an architect's voice.
2. **Room program → layout (plain Python, no AI).** Simple, well-commented Python builds THREE options (A/B/C) from the architect's own planning typologies (see Zoning strategy), shaped by the client's wishes (combined spaces placed adjacent as one open space; a wished garden buffers the living room; facing wishes place bedrooms on the correct real-world side, overriding zoning — a road-side south master goes in a front corner). Geometry is a HARD constraint: nothing is ever placed outside the buildable area — an option that cannot fit is skipped with a clear reason. Every option is checked against the HARD RULES in "Design Rules (from the architect)" below and shows its score plus pass/bend/fail per rule, plus a Client-wishes table (each wish MET / NOT MET / SKIPPED; missed wishes rank the option lower).
3. **Layout → drawing (SVG).** The app draws a clean, dimensioned 2D plan in SVG format with room names, areas, doors, windows, overall dimensions, and a north arrow / scale note.
4. **Stretch goals (only if time allows):**
   - **Muse Image** generates one exterior concept render from the plan/brief.
   - **Muse Voice Transcribe** lets the user speak the brief instead of typing it.

## Design Rules (from the architect)

Authoritative design input, added Oct 29. The app must check every plan against the HARD RULES and report any violation clearly in the UI. DESIGN GOALS are soft: try to achieve them, never block a plan for missing one.

**Units and scope:** Feet and inches. Single floor only. Plot can be any size the client enters.

**Inputs the user gives:** Road frontage and plot depth from road (road-relative: frontage is the side facing the road), north direction slider 0-360 deg (0 = north away from the road; the road side is the closest cardinal, shown under the slider), number of bedrooms, number of toilets (required, no default, 1 to bedrooms + 1), wishes in plain words. A live plot preview beside the inputs redraws on every change: to-scale rectangle with frontage/depth dims, road band + ROAD label, north arrow at the slider angle.

**Setbacks (defaults, user can edit in the app):** Front 6 ft, each side 1.5 ft, back 4 ft. Simplified, editable defaults — NOT full RAJUK rules. Real setbacks depend on road width and plot area.

**Walls:** Exterior 10 in thick, interior 5 in thick. Room sizes below are clear internal dimensions; walls are added in the drawing.

**Room sizes (BOTH sides of each room must fall within its range, and a room is NEVER square: its two sides must differ by at least 1 ft):**

- Bedroom: 10 to 15 ft per side.
- Kitchen: 8 to 15 ft per side.
- Living room: 12 to 15 ft per side.
- Family living: 12 to 15 ft per side.
- Dining: 10 to 14 ft per side.
- Bathroom: 6 to 10 ft per side; one side being 7 ft is preferred but not required.
- Corridor: minimum 3 ft 6 in wide (long and thin is expected, not subject to the never-square rule).
- Porch, foyer, veranda sizes: to be fixed during build (veranda rules below); propose defaults and confirm with architect.
- Day 2 proposal (architect to confirm): foyer 6-12 ft per side with never-square; porch 6-12 ft wide x 4-6 ft deep; veranda projection 3-5 ft; porch and veranda exempt from never-square (outdoor projections, like corridors).

### HARD RULES (must check + report violations)

1. Room sizes: both sides in range, never square (sides differ by >= 1 ft). Corridors exempt from never-square, min width 3 ft 6 in. Relaxed absolutes only to fit: family living 10-15 ft, living room 12-17 ft — a room inside relaxed but outside preferred BENDS (score -2 each, noted), never fails. Wardrobe/store filler beside side-strip baths is leftover space, exempt from size rules.
2. NO central corridor with rooms on both sides. Checkable definition: no corridor segment may have rooms touching both of its long sides. The placer avoids corridors by using family living as the circulation hub.
3. Corridors total 25% or less of built area.
4. Kitchen has exactly one inner door, opening into dining, plus ONE allowed exception: a second door to its own veranda (decided Oct 29).
5. Every bedroom door opens into family living; if impossible — defined as no shared wall length left for a 3 ft door — into dining; NEVER into the foyer or living room (a bedroom that can only open there marks the plan UNLIVABLE). Family living sits between/at the center of the bedrooms, never at an end away from them. Report which bedrooms used the dining fallback.
6. Every bedroom has at least 1 window (2 preferred).
7. Toilets (client enters 1 to bedrooms + 1, no default): EXACTLY that many bathrooms. Exactly 1 is COMMON with a door to common space (dining, family living, or corridor), reachable without passing through any bedroom. All others are ATTACHED: master (largest) bedroom first, then next largest bedrooms, one each. 1-bedroom home: the single toilet is common; a 2nd toilet attaches to the master. Example: 3 bedrooms + 3 toilets = 2 attached + 1 common. HARD rule: failing it marks the plan UNLIVABLE.
8. Bathrooms touch an exterior wall (for ventilation). Never place a bathroom on the front (road) wall; if unavoidable, report it as a violation.
9. Bathroom/toilet windows NEVER face the front (road) side.
10. Verandas: up to 2 bedrooms get a veranda each (if fewer than 2 bedrooms, every bedroom gets one), and the kitchen has a veranda. Each veranda is separate — two verandas never connect/touch. Veranda width 3 to 5 ft; length at least 3 ft and never longer than its room's wall.
11. Cross ventilation for living spaces and bedrooms. Hackathon proxy: openings on at least 2 different walls per room; OPPOSITE walls preferred, two adjacent walls is the minimum. Report per room: opposite / adjacent / failed.
12. The plan drawing shows doors and windows (doors and windows are modeled as objects: which rooms/walls they connect, not just drawn boxes).
13. Kitchen exterior wall: the kitchen has at least 6 ft of continuous exterior wall; its veranda sits on that exterior wall (3 ft+ shared). Compass-west wall preferred — missing west BENDS (soft, -1), never fails.
14. Bedroom window walls: every bedroom has at least 6 ft of continuous exterior wall usable for a window (a wall facing its own veranda counts; a wall blocked by a toilet or another room does not). One window wall BENDS (two is better, -1); under 6 ft FAILS.
15. Toilet exterior wall: every toilet has an exterior wall (enforced alongside rule 8 for the verdict).
16. Circulation: the route from every bedroom to the common toilet, and from the foyer to every indoor room except attached baths, passes only through foyer, living room, dining and family living — NEVER through the kitchen, a bedroom or a toilet. Attached baths are entered through their bedroom, directly or via the dressing wardrobe; porch/verandas through their host room; wardrobe/store filler is not a room (all excluded as targets). Adjacency means a shared wall; Day 3 places real 3 ft doors on those walls and checks them (rules 4/5/7/12).
17. Cross-ventilation walls (soft): living room, family living, dining and bedrooms need exterior walls on 2 sides (opposite preferred). One-sided rooms BEND (-1); a room with NO exterior wall FAILS (-100). Reported per room, never flips the verdict (Day 3 also checks real openings on 2+ walls: rule 11, soft).
18. Toilet real sizes (architect's own practice): common and attached toilets 4'-0" to 6'-0" wide (road-parallel side) by 6'-0" to 8'-6" long; the master toilet (attached to the largest bedroom) may be up to 6'-6" x 10'-0". Never-square still applies. Toilets are NEVER stretched to fill a strip: attached baths sit on the outer wall with a wardrobe/store beside them; the common bath sits on the spine with an open notch outside it.
19. Master bedroom (architect's practice, Oct 30): the master (name-master, else Bedroom 1, else first bedroom) is ALWAYS the largest bedroom — at least 10% more area than any other bedroom — and keeps the largest attached toilet. Never shrink the master to equal the others; shrink other rooms first. Failing it marks the plan UNLIVABLE.
22. Doors hug corners (about 4-6 in return), hinged on the corner side, swinging against the wall; never centered in a wall.
23. Kitchen and toilet windows NEVER face the road (rule 9 + rule 21); bedrooms MAY face the road.
24. Every wardrobe/store opens to its bedroom as a dressing lobby; the attached toilet is reached through it. No sealed boxes (a wardrobe with no bedroom wall opens to a hub space instead, noted).
25. ROOMS vs SPACES: bedrooms, toilets, kitchen, store, wardrobe are enclosed ROOMS with doors. Foyer, living, dining, family living are open SPACES in one continuous area, joined by wide openings with short (2 ft) wall stubs, never doors. Ventilation is judged for the whole open area at once.
26. The kitchen is ALWAYS an enclosed room (Bangladeshi cooking) and never connects to the living room. An open/combined kitchen wish joins dining or family living with a glass/sliding partition instead, explained in the design notes (the wish reads SKIPPED, never ranked down).
27. The kitchen door sits at the kitchen corner farthest from the living room.
28. The foyer may extend into unused front space and takes glazing on its side walls for daylight; foyer and living flow together.
29. No rigid rows: side-strip rooms may stagger off the spine room lines.
30. Leftover space inside the setback (especially front corners) is drawn as garden/landscape (green), never a void.
31. Front bedrooms take a road-side window for cross ventilation (pairs with the back window).
32. (Optional) one of the 3 options joins dining and family living with a glass partition + sliding glass door, for variety.
33. Family living gets a large (5 ft) window on its back/exterior wall.
Failing any of rules 5, 7, 13-16, 19, or geometry row G (rooms outside the plot / overlaps — unbuildable means unlivable), marks the plan UNLIVABLE (red) in the UI. Score: every FAIL -100, every BEND -1 (rule 1 bends -2 per relaxed room instead), met wishes +10 each, missed wishes -15 each (a plan missing a clear wish ranks lower), goals/doors break ties.

**Zoning strategy (the architect's own planning typologies, Oct 29):** local frame with the road at the bottom; all dimensions rounded to 6 inches; side strips 10-15 ft, center strip 10-15 ft.
- THREE-STRIP (main pattern): CENTER strip = public spine front-to-back (foyer/entry with porch outside toward the road, living room, dining, family living; NO corridor; family may take a back veranda). LEFT/RIGHT strips = rooms needing exterior walls (bedrooms, kitchen, toilets), each touching the outer side wall. Bedrooms take corners when possible (master at a back corner); toilets sit between bedrooms against the outer wall (leftover width becomes wardrobe/store); kitchen mid-strip next to dining, door into dining; every side room's door opens into the adjacent center room (bedrooms into family/dining never foyer/living, common toilet off dining/family). Side strips narrow to 10 ft when a common bath needs a full-width spine door. Stacking tries bath-above-bed orders, a floated common toilet (never an explicitly placed one), and a master-size second pass (others shrink first; small back notches keep doors) — ranked fewest fatal misses, then rule 19, then doors.
- NARROW plots (buildable width under 30 ft): TWO strips (center spine + one side strip).
- L-SHAPE WITH COURT (buildable width 45 ft+ and only when it fits): front wing for foyer/living/dining/kitchen joined to a side wing for family living + bedrooms; landscape/court fills the open corner.
- WIDE SHALLOW plots (frontage over depth, strips need more depth): SHALLOW TWO-BAND fallback — front band (foyer, living, dining, kitchen side by side, kitchen at an end) + back band (family in the middle with a bedroom each side, baths outer, common toilet under dining or beside family, store slice for slack). Toilets keep real widths (rule 18, orientation-free); attached baths sit at the back with wardrobes in front, the common at the front of its slice onto dining; the family overlaps a non-kitchen front room so circulation never crosses the kitchen. A front-position bedroom wish flips A/B into front-master mode (wished bed in a front corner, kitchen to a back corner under dining, family under the master; symmetric 12 ft bands so rule 19 can hold; classic retry when the corner cannot fit); C stays classic for comparison.
- THREE OPTIONS side by side: A = kitchen west end (real orientation); B = mirrored; C = L-shape when it fits, else a third variant (common toilet on the kitchen side when facing wishes collapse the strips). Genuinely different; each shows score + pass/bend/fail.
- FITTING LADDER (geometry is hard; skip + message instead of broken plans): full buildable width minus 3 ft veranda margins each side when width allows; living room to a FRONT corner of a side strip next to the foyer (architect's own pattern) so the spine holds only foyer, dining, family; small foyer (about 6 ft deep); wished merges shorten the spine; then min-depths.
- WISHES SHAPE THE PLAN (and override zoning): "combined X and Y" / "open X and Y" / "X and Y as one space" / "open-plan X Y" places both adjacent as one open gathering space (living+kitchen repositions; other pairs verified, 6 ft+ shared); "garden with the living room" places a small garden (dashed in the drawing) buffering the living front. Bedrooms never combine (privacy). Orientation wishes ("south facing master bedroom", "bedroom facing east") place that bedroom with a window-able (6 ft+) exterior wall on the correct real-world side — even on the road side (front corner beside foyer/living, veranda ordered to that wall best-effort); the common toilet moves opposite a front-most bedroom so it keeps its door; other rooms stay where the typology puts them, noted. Proximity wishes ("a bedroom near family living") are evaluated, not placed (MET when a door-able 3 ft+ wall is shared). Each option shows a Client-wishes table (MET / NOT MET / SKIPPED — skipped wishes are refused ones, never ranked); missing a clear wish costs -15 (met wishes +10).

**Orientation preferences (Bangladesh tropical monsoon climate — placer follows in order, reports results):** Bedrooms and living prefer windows facing south/southeast (prevailing breeze); avoid large west-facing openings in bedrooms and living (afternoon heat); the kitchen prefers the WEST side (common Bangladeshi practice: option A takes the west strip, B mirrors it, misses bend rule 13). All orientation picks use the real north angle: whichever plot side is closest to the required direction wins (ties prefer the side strips). Day 3 ranks window walls S/SE first, west last, and rule 20 reports west-facing glass.

### DESIGN GOALS (try, don't block)

- A good entry approach with a proper porch and foyer.
- The building outline is NOT a plain rectangle or square; a small break/jog in the plan is good. Handling: porch + separate verandas break the outline; check passes if the outline has more than 4 corners.
- On a big plot, don't fill the whole site; size the house from the rooms and leave landscape.
- Use the north direction for good daylight and cross ventilation (via the orientation preferences above).

### Resolved decisions (Oct 29, architect approved)

- Kitchen gets one extra door to its own veranda (only exception to the dining-only rule).
- Bathrooms are never placed on the front wall; unavoidable cases are reported as violations.
- Verandas: up to 2 bedrooms get one each (all bedrooms if fewer than 2), plus the kitchen.
- Toilets: client enters 1 to bedrooms + 1 (no default, required); exactly 1 common, rest attached master-first (replaces the old attached-attempt rule).
- Area budget: buildable = plot minus setbacks; program = rooms + wall estimates (10 in exterior, 5 in interior); AI shrinks rooms once to fit, else a clear warning shows.
- Room features: wishes that are not separate rooms live in each room's "features" list for the drawing step.
- Display: all dimensions in feet and inches (14'-0", 3'-6"); areas in sq ft.
- "Bedroom door impossible into family living" = no shared wall length left for a 3 ft door; fallback to dining, reported per bedroom.
- Cross ventilation proxy: openings on 2+ walls, opposite preferred, adjacent minimum.
- Non-rectangular outline: porch + separate verandas break the outline; check passes if outline has more than 4 corners.
- No central corridor: no corridor segment with rooms on both long sides; family living is the circulation hub.
- Orientation: south/southeast windows for breeze, no large west openings in bedrooms/living, kitchen west.
- Overall approach approved: checker (pass/fail per rule, always shown) + placer (priority order); on impossible plots show the best attempt plus the failed rules.
- Typologies (Oct 29, from the architect's own practice): three-strip main pattern, two-strip under 30 ft buildable, L-shape with court at 45 ft+ when it fits; options A/B/C as above.
- Bends (Oct 29): soft misses (relaxed sizes, kitchen-west, one window wall, one-sided vent) cost -1 (rule 1: -2/room) and never flip the verdict; only FAILs on 7, 13-16 and G mark UNLIVABLE.
- Fit + wishes (Oct 29, architect's practice): geometry G is a placement constraint (skip + reason, never overflow); toilet real sizes are rule 18 (not stretched); rule 7 is verdict-hard; living-out front corner, merges, and garden-from-wishes as above. Combined spaces share one open rectangle (Day 3 omits the dividing wall, no door between them).
- Road-relative inputs (Oct 29): frontage x depth-from-road; the road side only rotates the drawing and sets real orientation (kitchen west, south rooms, west-wall checks all road-aware). Shallow-band fallback for wide plots (front/back bands as above); facing wishes place bedrooms (front-most bedrooms push stacks off the front wall per rule 8 and keep standard baths per rule 18).
- North angle (Oct 30): N/S/E/W select replaced by a 0-360 "North direction" slider + live plot preview (to-scale rect, dims, road band, rotating arrow); closest cardinal becomes the road side. Orientation (kitchen west, facing wishes, west wall/goal) uses the real angle via closest side; final plans show the arrow at the same angle. Cardinal angles reproduce the old road sides exactly.
- Master size + family hub + wishes override (Oct 30): rule 19 (master 10%+ biggest + biggest attached toilet, hard); rules 5 and 19 join the verdict (bedroom door into foyer/living = UNLIVABLE); family living hubs every bedroom (bands: middle or under the front master; strips: fatal-miss-ranked stacking); wishes override zoning (front-corner master, veranda ordered to the wished wall); per-option wishes table + ranking (met +10, missed -15, skipped never ranked); options differ by master/family/kitchen positions.
- Night TASK 1 (Oct 30): T1-T6 regression briefs as tests (22/22 pass) + review/ SVGs via save_review.py (15 files + NOTES.txt); near-wishes parsed and tabled ("X near Y", door-able wall test). T1-T4 all LIVABLE with wishes MET; T5 honest skip (54 ft needed, 40 ft have); T6 4-bed west honest UNLIVABLE (5/16/19, wishes MET) — needs a new typology move, architect decision pending.
- Night TASK 2 / Day 3 (Oct 30): walls, doors, windows (openings.py: door table entry 3.5/room 3.0/toilet 2.5/veranda 2.5, 4 in off true corners with a T-junction exception, mirrored two-side fit, hub spanning over real shared walls, kitchen door-bearing nudge; windows bed 4.0 x2/living 5.0/common 4.0/kitchen 3.0/bath 2.0 never road-side, S/SE first, west last). Rules 4/5/6/7/9/11/12 really check the drawn gaps (one placement, two readers) + soft rule 20 (living-space windows, west-glass report); zero PENDING everywhere (26/26 pass). Honest new FAILs, all non-verdict: band kitchens away from dining (wide C, T4C: rules 4+12), 3 ft corner store (wide: rule 12), T6 kitchen/bedroom doors (4+12). review/ SVGs re-saved with walls/doors/windows.
- Architect review round 1 (Oct 30, from the T1 plans): 12 new rules (22-33) - corner-hinged doors, kitchen/toilet never road-facing, dressing-lobby chains, rooms-vs-spaces with stubbed openings, enclosed kitchen (glass, never living), far-corner kitchen door, foyer side glazing, staggered strips, green leftover, front-bedroom road windows, variety glass in one option, big family back window. Kitchen-living combines refused (SKIPPED + glass-to-dining note); C still compares (garden kept). 27/27 pass.
- Known honest limits (Oct 30): middle-spine dining is often windowless (rule 17 FAILs soft, verdict unaffected); side margins under 3 ft block E/W verandas (kitchen relies on S/N walls; rule 10/13 report); narrow 2-bed overconstrains one strip (UNLIVABLE, option C saves 1-bed); a front corner needs symmetric 12 ft bands (classic retry when it cannot fit, noted).

## Tech stack

- **Language:** Python (kept simple, heavily commented so a non-programmer can follow).
- **Web UI:** Streamlit (free hosting on Streamlit Community Cloud).
- **AI:** Meta Model API (see API section below). No other paid services.
- **Drawing:** SVG generated by our own Python code (no CAD library needed).

Project files:

- `app.py` — Streamlit user interface (Day 1 brief form; Day 2 three options side by side + detail expanders).
- `ai_program.py` — calls Muse Spark, gets the room program JSON (Day 1).
- `layout.py` — shared geometry (buckets, rects, porch/verandas) + strict rule checker 1-20/G + scorer + verdict (Day 2, doors/windows Day 3).
- `typology.py` — typology placer: three-strip / two-strip / L-shape / shallow-band fallback, facing wishes, options A/B/C via `build_options` (Day 2, door-bearing nudge Day 3).
- `draw.py` — draws one option's SVG plan (solid walls, doors, windows) + the live plot preview `svg_plot_preview` (Day 2, walls/doors/windows Day 3).
- `openings.py` — door/window placement + wall bands + gap audit, shared by the drawing and the checker (Day 3).
- `test_layout.py` — typology options + minis + drawing checks, run `python test_layout.py` (Day 2, T1-T6 + Day 3 checks).
- `save_review.py` — re-saves the T1-T6 review/ SVGs + NOTES.txt (run after placer/drawing changes).
- `review/` — one SVG per review-brief option + NOTES.txt (verdicts, fails, wishes).
- `requirements.txt` — Python packages needed.
- `.env` — holds the API key locally, NEVER committed (see below).
- `.streamlit/secrets.toml` — holds the API key on Streamlit Cloud, NEVER committed.

## Meta Model API — what we will call (checked Oct 29, 2026)

Docs portal: `https://dev.meta.ai/docs/` (quickstart + models pages). The API is in public preview and is OpenAI-compatible, so we use the standard OpenAI Python client and just change the base URL and key. There is no Meta-published Python SDK to install.

- **Base URL:** `https://api.meta.ai/v1`
- **Auth:** `Authorization: Bearer <key>` header, key read from our `META_API_KEY` variable (Meta's docs call the same key `MODEL_API_KEY` — same value, our project just uses the name `META_API_KEY`).
- **Text endpoint (room program):** `POST /v1/responses` (Responses API, the current default) with model `muse-spark-1.3`. Fallback: `POST /v1/chat/completions` with the same model if a library only supports Chat Completions.
- **Text model:** `muse-spark-1.3` (latest hosted Spark; 1M-token context). Older options if needed: `muse-spark-1.2`, `muse-spark-1.1`. Cheaper Contributor variants (`muse-spark-1.3-contributor`, `muse-spark-1.2-contributor`) exist but carry contributor terms — avoid unless budget requires it.
- **Image endpoint (stretch):** `POST /v1/images/generations` with model `muse-image-1.0`.
- **Voice endpoint (stretch):** `POST /v1/asr/transcribe` with model `muse-voice-transcribe-1.0` for recorded audio (realtime option `wss://api.meta.ai/v1/asr/realtime` is out of scope for this project).
- **Do NOT use:** `api.llama.com` (retired July 6, 2026), `api.ai.meta.com` (old pre-launch endpoint), or open-weight models `Muse Spark Open` / `Muse Glimmer` (they run on your own hardware, not on the Model API).
- **Approx. price (Standard tier, from Meta price card):** Muse Spark about $1.25 / 1M input tokens + $4.25 / 1M output tokens. Keep prompts short and cache nothing sensitive.

## API key rules (must always hold)

1. The key is read from the environment variable **`META_API_KEY`** or a local **`.env`** file containing `META_API_KEY=...`.
2. The key must **NEVER** be written into any committed file (no key in `.py`, `.md`, `.toml`, screenshots, or the demo video).
3. `.env` is already in `.gitignore` (verified Oct 29), along with `.streamlit/secrets.toml`. Never force-add them.
4. On Streamlit Community Cloud the key goes in the app's Secrets settings as `META_API_KEY`, never in the code.

## Day-by-day build plan (Oct 29 → Nov 4)

- **Thu Oct 29 — Setup + AI step.** Project file (this doc), test the Meta Model API key with one tiny call, design the room-program JSON format, write and test the architect-style prompt. Done = prompt reliably returns valid JSON for 2–3 sample briefs.
- **Fri Oct 30 — Layout engine.** Write `layout.py`: rectangle placement inside buildable area + the full hard-rule checker from "Design Rules". Done = sample programs produce valid layouts or clear violation reports.
- **Sat Oct 31 — Drawing.** Write `draw.py`: clean SVG plan with room names, areas, doors, windows, dimensions. Done = one sample layout renders as a good-looking plan.
- **Sun Nov 1 — Web app wiring.** Write `app.py`: brief form → AI → layout → drawing on screen, plus the design-reasoning text. Done = full flow works locally end to end.
- **Mon Nov 2 — Polish + deploy.** Fix edge cases (tiny plots, many rooms, missed adjacencies), simple styling, deploy to Streamlit Community Cloud with the key in Secrets. Done = public link works without the key leaking.
- **Tue Nov 3 — Stretch or buffer.** If core is solid: add ONE stretch feature (exterior image OR voice brief). Otherwise use the day to fix bugs and polish the demo story. Done = feature frozen by evening.
- **Wed Nov 4 — Demo + submit.** Record the demo video (keep key out of frame), write the submission text, submit before the deadline. No new features this day.

## Built during the hackathon

Update this list as we go (each item: date + one line).

- [x] Oct 29: Brief → room program with Muse Spark (requirements.txt, ai_program.py, app.py, .env.example).
- [x] Oct 29 (update): area budget, room features, feet-inch display, toilet rule.
- [x] Oct 29 (Day 2): room layout + plan drawing (layout.py, draw.py, app plan section, test_layout.py); 40x60 South 3-bed/3-toilet demo passes all checkable rules, impossible plots show best attempt + failed rules.
- [x] Oct 29 (Day 2 update): strict livability checks 13-17 + UNLIVABLE verdict (checker only, placer frozen); demo UNLIVABLE on 13, 14, 16.
- [x] Oct 29 (Day 2 update): three-strip typology placer + 3 options side by side (typology.py replaces the band placer; bends, relaxed sizes, G joins verdict); 40x60 North 3/3 all LIVABLE.
- [x] Oct 29 (Day 2 update): fit to plot (G hard, living-out, small foyer, skip + message), real toilet sizes (rule 18), rule 7 hard, wishes shape layout (open plan, garden); 45x55 South 2/2 + 40x60 North 3/3 all LIVABLE.
- [x] Oct 29 (Day 2 update): road-relative plot inputs, wide plots, orientation wishes (frontage x depth-from-road; shallow-band fallback; facing wishes place bedrooms; C variant on collapse); 40x60 East 2/2 + 60x40 South 2/2 + 45x55 South + 40x60 North all LIVABLE.
- [x] Oct 30: plot preview with rotatable north arrow (preview + 0-360 slider replace N/S/E/W; angle-aware closest-side orientation; plans show the same angle); tested at 0/90/30 deg.
- [x] Oct 30 (Day 2 update): master size, family living hub, wishes override zoning (rule 19 hard; rules 5+19 join verdict; two-pass strip stacking with fatal-miss ranking; front-master bands; per-option wishes table + ranking; wish-ordered verandas); 50x40 South 2/2 + 40x60 North 3/3 + 45x55 South 2/2 + 40x60 East 2/2 all LIVABLE, 16/16 tests pass.
- [x] Oct 30: `layout.py` — placement + rule checks working (done Oct 29, Day 2).
- [x] Oct 31: `draw.py` — SVG plan rendering (done Oct 29, Day 2).
- [ ] Nov 1: `app.py` — full local flow (brief → plan on screen).
- [ ] Nov 2: Deployed to Streamlit Community Cloud (public link: _tbd_).
- [ ] Nov 3: Stretch feature (_tbd_) or polish.
- [ ] Nov 4: Demo video recorded + hackathon submitted.

## Authorship note

The code for this project is written with AI coding assistance (Muse Code, powered by Meta Muse Spark) under my direction as the architect and designer. I make all design decisions; the AI helps me write and understand the code.
