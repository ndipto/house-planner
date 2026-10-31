# House Planner

A concept house planner for Bangladesh, designed by an architect. A client
describes their plot and their wishes in plain words; House Planner turns
the brief into three concept floor plans — with solid walls, doors,
windows, dimensions and a north arrow — each checked against the
architect's own livability rules.

Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).

## How it works

1. **Brief → room program (AI).** Muse Spark reads the brief and returns
   structured JSON: rooms, sizes, adjacencies, orientation wishes, plus a
   short design reasoning in an architect's voice. Plain Python then
   checks sizes, the toilet rule and the area budget.
2. **Room program → layout (plain Python, no AI).** A typology placer
   lays out THREE options (A/B/C) from planning patterns of the
   architect's own practice: three-strip (public spine + side rooms),
   two-strip for narrow plots, L-shape with court and shallow bands for
   wide plots. Client wishes shape the plan and override zoning
   (combined/open spaces, garden buffer, south-facing master even on the
   road side). Geometry is a hard constraint: nothing ever lands outside
   the buildable area.
3. **Layout → drawing (our own SVG code).** Each option is drawn as a
   clean black-on-white plan: 10 in exterior / 5 in interior walls, doors
   with swing arcs, windows, room names, sizes, areas, dimensions, road
   label and north arrow. Open-plan pairs share one open space (no wall).
4. **Checker.** Every option is scored against 20 rules plus geometry G
   and shown as 'All key rules met' or 'Needs review' (one plain
   sentence per issue) — the same
   door/window gaps the drawing shows are the ones the checker verifies,
   so no rule stays unchecked.

## Meta models used

- **Muse Spark (`muse-spark-1.3`)** through the Meta Model API
  (`https://api.meta.ai/v1`, OpenAI-compatible client) — brief to room
  program, the only AI call in the pipeline. Placement, drawing and
  checking are plain Python so every plan is reproducible and
  rule-traceable.
- **Muse Image (`muse-image-1.0`)** — one colored presentation
  render per option, from a "Render this plan" button: the plan
  goes out with furniture outlines + room names, comes back as a
  flat top-down render, and Muse Spark auto-checks every room's
  furniture (retries twice, keeps the best). A "Regenerate"
  button re-renders on demand.
- **Muse Voice Transcribe (`muse-voice-transcribe-1.0`)** — speak the
  brief into the microphone; the transcript fills the wishes box
  (code + mocked tests done, needs one live microphone test).

## How to run it

```bash
pip install -r requirements.txt
cp .env.example .env        # then put your key in .env (never committed)
streamlit run app.py        # open the local address it prints
```

Run the checks (49 automated tests, no key needed):

```bash
python test_layout.py         # 35 placer/checker/drawing tests (T1-T8 included)
python test_render.py         # 3 mocked Muse Image tests
python test_voice.py          # 3 mocked Muse Voice tests
python test_plan_render.py    # 8 mocked render auto-check tests
```

Re-save the review set after placer/drawing changes:

```bash
python save_review.py       # writes review/*.svg + review/NOTES.txt
```

## Built during the hackathon (Oct 26 – Nov 4)

From the git history:

- **Oct 29** — project spec + the architect's design rules; Day 1: brief
  to room program with Muse Spark, area budget, feet-inch display;
  Day 2 starts: room layout and plan drawing, then strict livability
  checks (kitchen/bedroom/toilet exterior walls, circulation never
  through kitchen/bedroom/toilet).
- **Oct 30** — typology placer with 3 options; fit-to-plot, real toilet
  sizes, wishes shape layout; road-relative inputs, wide plots,
  orientation wishes; plot preview with rotatable north arrow; master
  size + family-living hub + wishes override zoning; night queue:
  T1–T6 regression set with review SVGs, then walls/doors/windows with a
  real checker (zero unchecked rules).
- **Oct 31** — architect review rounds 1+2 (rules 22–33, kitchen-dining
  hard rule, T5 compact two-strip, T6 all livable, pantry stores);
  night queue: kitchen-veranda variants (jali screen / side-back /
  windowed), exterior concept renders with Muse Image, Streamlit Cloud
  deploy guide, demo polish (example brief, one-line summaries,
  friendly errors), voice brief with Muse Voice Transcribe.
- **Nov 1** — wide-shallow plots (leftover width as garden/court,
  dining-second retry, T7); foyer as a zone inside living + veranda
  doors swinging out (rules 34–35); big-master-toilet wish (T8);
  friendly verdict labels ('All key rules met'/'Needs review' with
  plain sentences, OK/REVIEW review files); strict master-role swap
  attempt per option; pre-deploy check; results kept in session
  state; rendered floor plans with Muse Image (furniture outlines
  + room-name labels in, flat top-down render out) with a Muse
  Spark vision auto-check per room, wired into the app as "Render
  this plan" + "Regenerate".

## Authorship note

The code was written with AI coding assistance (Muse Code) under my
direction as the architect and designer: every zoning pattern, rule,
size and threshold in this repository is my own practice, and every plan
the app draws is checked against those rules. No API key is stored in
this repository — bring your own Meta Model API key in a local `.env`.
