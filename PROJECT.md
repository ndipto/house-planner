# House Planner

**Owner:** Architect (solo builder, no coding background) + AI coding assistance (see Authorship note below).
**Event:** Meta Global AI Developer Hackathon — deadline **Nov 4, 2026**.
**Status:** Day 2 done Oct 29 — typology placer builds 3 options (A/B/C) side by side with scores; 40x60 North 3-bed/3-toilet demo all LIVABLE (B bends kitchen-west).

This file is the project memory. Muse Code should read it at the start of every session and keep the "Built during the hackathon" section up to date.

## What it is

House Planner is a simple web app for **Bangladesh**, designed by a Bangladeshi architect. The user describes the house they want in plain words:

- Plot width and depth (in feet), which side faces the road, and north direction
- Number of bedrooms and number of toilets (1 to bedrooms + 1, no default — the client must enter it)
- Family needs and wishes in plain words (e.g. "home office", "big kitchen for family gatherings", "elderly parent on ground floor")

The app returns a **single-floor 2D floor plan concept**: three layout options (A/B/C) side by side, each drawn as a clean, dimensioned plan with room names and areas, each with its score and rule report.

The design rules are tuned for Bangladesh's tropical monsoon climate and local living patterns: family living as the bedroom hub, separate verandas, kitchen on the west side, breeze-facing windows. Setbacks in the app are simplified, editable defaults — not full RAJUK rules.

This is a **concept tool**, not construction documents. It helps a family see three possible layouts from their brief in seconds.

## How it works (4 steps)

1. **Brief → room program (AI).** Muse Spark, called through the Meta Model API, reads the user's brief and returns structured JSON: for each room its name, type, target area, min/max dimensions, required adjacencies (e.g. kitchen next to dining), orientation preferences (e.g. bedrooms face south/southeast), plus a short "design reasoning" paragraph written in an architect's voice.
2. **Room program → layout (plain Python, no AI).** Simple, well-commented Python builds THREE options (A/B/C) from the architect's own planning typologies (see Zoning strategy), places rooms as non-overlapping rectangles inside the buildable area, and checks every option against the HARD RULES in "Design Rules (from the architect)" below. Each option shows its score and which rules pass, bend or fail; on impossible plots the app says so honestly instead of drawing a broken plan.
3. **Layout → drawing (SVG).** The app draws a clean, dimensioned 2D plan in SVG format with room names, areas, doors, windows, overall dimensions, and a north arrow / scale note.
4. **Stretch goals (only if time allows):**
   - **Muse Image** generates one exterior concept render from the plan/brief.
   - **Muse Voice Transcribe** lets the user speak the brief instead of typing it.

## Design Rules (from the architect)

Authoritative design input, added Oct 29. The app must check every plan against the HARD RULES and report any violation clearly in the UI. DESIGN GOALS are soft: try to achieve them, never block a plan for missing one.

**Units and scope:** Feet and inches. Single floor only. Plot can be any size the client enters.

**Inputs the user gives:** Plot width and depth, which side faces the road, north direction, number of bedrooms, number of toilets (required, no default, 1 to bedrooms + 1), wishes in plain words.

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
5. Every bedroom door opens into family living; if impossible — defined as no shared wall length left for a 3 ft door — into dining; NEVER into the living room. Report which bedrooms used the dining fallback.
6. Every bedroom has at least 1 window (2 preferred).
7. Toilets (client enters 1 to bedrooms + 1, no default): EXACTLY that many bathrooms. Exactly 1 is COMMON with a door to common space (dining, family living, or corridor), reachable without passing through any bedroom. All others are ATTACHED: master (largest) bedroom first, then next largest bedrooms, one each. 1-bedroom home: the single toilet is common; a 2nd toilet attaches to the master. Example: 3 bedrooms + 3 toilets = 2 attached + 1 common.
8. Bathrooms touch an exterior wall (for ventilation). Never place a bathroom on the front (road) wall; if unavoidable, report it as a violation.
9. Bathroom/toilet windows NEVER face the front (road) side.
10. Verandas: up to 2 bedrooms get a veranda each (if fewer than 2 bedrooms, every bedroom gets one), and the kitchen has a veranda. Each veranda is separate — two verandas never connect/touch. Veranda width 3 to 5 ft; length at least 3 ft and never longer than its room's wall.
11. Cross ventilation for living spaces and bedrooms. Hackathon proxy: openings on at least 2 different walls per room; OPPOSITE walls preferred, two adjacent walls is the minimum. Report per room: opposite / adjacent / failed.
12. The plan drawing shows doors and windows (doors and windows are modeled as objects: which rooms/walls they connect, not just drawn boxes).
13. Kitchen exterior wall: the kitchen has at least 6 ft of continuous exterior wall; its veranda sits on that exterior wall (3 ft+ shared). Compass-west wall preferred — missing west BENDS (soft, -1), never fails.
14. Bedroom window walls: every bedroom has at least 6 ft of continuous exterior wall usable for a window (a wall facing its own veranda counts; a wall blocked by a toilet or another room does not). One window wall BENDS (two is better, -1); under 6 ft FAILS.
15. Toilet exterior wall: every toilet has an exterior wall (enforced alongside rule 8 for the verdict).
16. Circulation: the route from every bedroom to the common toilet, and from the foyer to every indoor room except attached baths, passes only through foyer, living room, dining and family living — NEVER through the kitchen, a bedroom or a toilet. Attached baths are entered through their bedroom; porch/verandas through their host room; wardrobe/store filler is not a room (all excluded as targets). Adjacency means a shared wall; door-sized refinement arrives Day 3.
17. Cross-ventilation walls (soft): living room, family living, dining and bedrooms need exterior walls on 2 sides (opposite preferred). One-sided rooms BEND (-1); a room with NO exterior wall FAILS (-100). Reported per room, never flips the verdict (openings modeled Day 3).
Failing any of rules 13-16, or geometry row G (rooms outside the plot / overlaps — unbuildable means unlivable), marks the plan UNLIVABLE (red) in the UI. Score: every FAIL -100, every BEND -1 (rule 1 bends -2 per relaxed room instead), goals/doors break ties.

**Zoning strategy (the architect's own planning typologies, Oct 29):** local frame with the road at the bottom; all dimensions rounded to 6 inches; side strips 10-15 ft, center strip 10-15 ft.
- THREE-STRIP (main pattern): CENTER strip = public spine front-to-back (foyer/entry with porch outside toward the road, living room, dining, family living; NO corridor; family may take a back veranda). LEFT/RIGHT strips = rooms needing exterior walls (bedrooms, kitchen, toilets), each touching the outer side wall. Bedrooms take corners when possible (master at a back corner); toilets sit between bedrooms against the outer wall (leftover width becomes wardrobe/store); kitchen mid-strip next to dining, door into dining; every side room's door opens into the adjacent center room (bedrooms into family/dining never living, common toilet off dining/family). Side strips narrow to 10 ft when a common bath needs a full-width spine door.
- NARROW plots (buildable width under 30 ft): TWO strips (center spine + one side strip).
- L-SHAPE WITH COURT (buildable width 45 ft+ and only when it fits): front wing for foyer/living/dining/kitchen joined to a side wing for family living + bedrooms; landscape/court fills the open corner.
- THREE OPTIONS side by side: A = three-strip, kitchen WEST in real orientation; B = three-strip mirrored (kitchen other side, master other back corner); C = L-shape when it fits, else a third three-strip variant. Genuinely different; each shows score + pass/bend/fail.

**Orientation preferences (Bangladesh tropical monsoon climate — placer follows in order, reports results):** Bedrooms and living prefer windows facing south/southeast (prevailing breeze); avoid large west-facing openings in bedrooms and living (afternoon heat); the kitchen prefers the WEST side (common Bangladeshi practice: option A takes the west strip, B mirrors it, misses bend rule 13).

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
- Bends (Oct 29): soft misses (relaxed sizes, kitchen-west, one window wall, one-sided vent) cost -1 (rule 1: -2/room) and never flip the verdict; only FAILs on 13-16 and G mark UNLIVABLE.
- Known honest limits (Oct 29): spine living/dining are often 0-1-sided (rule 17 reports, verdict unaffected); corner bedrooms lose verandas when side margins run under 3 ft (rule 10 reports); narrow 2-bed overconstrains one strip (UNLIVABLE, option C saves 1-bed); shallow plots need the L (three-strip overflows honestly).

## Tech stack

- **Language:** Python (kept simple, heavily commented so a non-programmer can follow).
- **Web UI:** Streamlit (free hosting on Streamlit Community Cloud).
- **AI:** Meta Model API (see API section below). No other paid services.
- **Drawing:** SVG generated by our own Python code (no CAD library needed).

Project files:

- `app.py` — Streamlit user interface (Day 1 brief form; Day 2 three options side by side + detail expanders).
- `ai_program.py` — calls Muse Spark, gets the room program JSON (Day 1).
- `layout.py` — shared geometry (buckets, rects, porch/verandas) + strict rule checker 1-17/G + scorer + verdict (Day 2).
- `typology.py` — typology placer: three-strip / two-strip / L-shape, options A/B/C via `build_options` (Day 2).
- `draw.py` — draws one option's SVG plan (Day 2).
- `test_layout.py` — typology options + minis + drawing checks, run `python test_layout.py` (Day 2).
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
- [x] Oct 30: `layout.py` — placement + rule checks working (done Oct 29, Day 2).
- [x] Oct 31: `draw.py` — SVG plan rendering (done Oct 29, Day 2).
- [ ] Nov 1: `app.py` — full local flow (brief → plan on screen).
- [ ] Nov 2: Deployed to Streamlit Community Cloud (public link: _tbd_).
- [ ] Nov 3: Stretch feature (_tbd_) or polish.
- [ ] Nov 4: Demo video recorded + hackathon submitted.

## Authorship note

The code for this project is written with AI coding assistance (Muse Code, powered by Meta Muse Spark) under my direction as the architect and designer. I make all design decisions; the AI helps me write and understand the code.
