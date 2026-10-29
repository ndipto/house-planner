# House Planner

**Owner:** Architect (solo builder, no coding background) + AI coding assistance (see Authorship note below).
**Event:** Meta Global AI Developer Hackathon — deadline **Nov 4, 2026**.
**Status:** Day 1 done Oct 29 (brief → room program with area budget + toilet rule). Layout step next.

This file is the project memory. Muse Code should read it at the start of every session and keep the "Built during the hackathon" section up to date.

## What it is

House Planner is a simple web app for **Bangladesh**, designed by a Bangladeshi architect. The user describes the house they want in plain words:

- Plot width and depth (in feet), which side faces the road, and north direction
- Number of bedrooms and number of toilets (1 to bedrooms + 1, no default — the client must enter it)
- Family needs and wishes in plain words (e.g. "home office", "big kitchen for family gatherings", "elderly parent on ground floor")

The app returns a **single-floor 2D floor plan concept**: rooms placed on the plot, drawn as a clean, dimensioned plan with room names and areas.

The design rules are tuned for Bangladesh's tropical monsoon climate and local living patterns: family living as the bedroom hub, separate verandas, kitchen on the west side, breeze-facing windows. Setbacks in the app are simplified, editable defaults — not full RAJUK rules.

This is a **concept tool**, not construction documents. It helps a family see one possible layout from their brief in seconds.

## How it works (4 steps)

1. **Brief → room program (AI).** Muse Spark, called through the Meta Model API, reads the user's brief and returns structured JSON: for each room its name, type, target area, min/max dimensions, required adjacencies (e.g. kitchen next to dining), orientation preferences (e.g. bedrooms face south/southeast), plus a short "design reasoning" paragraph written in an architect's voice.
2. **Room program → layout (plain Python, no AI).** Simple, well-commented Python places rooms as non-overlapping rectangles inside the buildable area of the plot, adds circulation, and checks every plan against the HARD RULES in "Design Rules (from the architect)" below. Any violation is reported clearly in the UI; on impossible plots the app shows its best attempt plus the list of failed rules.
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

### HARD RULES (must check + report violations)

1. Room sizes: both sides in range, never square (sides differ by >= 1 ft). Corridors exempt from never-square, min width 3 ft 6 in.
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

**Zoning strategy (placement order, road side inward):** Porch and foyer/entry first, then living room (public zone); then dining, kitchen and family living (semi-private zone); bedrooms at the back and sides (private zone), clustered around family living.

**Orientation preferences (Bangladesh tropical monsoon climate — placer follows in order, reports results):** Bedrooms and living prefer windows facing south/southeast (prevailing breeze); avoid large west-facing openings in bedrooms and living (afternoon heat); the kitchen prefers the WEST side (common Bangladeshi practice, applied within the semi-private band).

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

## Tech stack

- **Language:** Python (kept simple, heavily commented so a non-programmer can follow).
- **Web UI:** Streamlit (free hosting on Streamlit Community Cloud).
- **AI:** Meta Model API (see API section below). No other paid services.
- **Drawing:** SVG generated by our own Python code (no CAD library needed).

Planned files (not created yet):

- `app.py` — Streamlit user interface.
- `ai_program.py` — calls Muse Spark, gets the room program JSON.
- `layout.py` — places rectangles, checks rules.
- `draw.py` — draws the SVG plan.
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
- [ ] Oct 30: `layout.py` — placement + rule checks working.
- [ ] Oct 31: `draw.py` — SVG plan rendering.
- [ ] Nov 1: `app.py` — full local flow (brief → plan on screen).
- [ ] Nov 2: Deployed to Streamlit Community Cloud (public link: _tbd_).
- [ ] Nov 3: Stretch feature (_tbd_) or polish.
- [ ] Nov 4: Demo video recorded + hackathon submitted.

## Authorship note

The code for this project is written with AI coding assistance (Muse Code, powered by Meta Muse Spark) under my direction as the architect and designer. I make all design decisions; the AI helps me write and understand the code.
