# ALIBI — Design brief

Companion to `ALIBI_SPEC.md`. the coding assistant: read this before writing any frontend code,
and re-read section 7 before you think a component is finished.

---

## 1. The philosophy: the hole is the hero

Alibi's load-bearing data is **temporal interval coverage**, not graph topology. The
question a viewer must be able to answer in two seconds is *which minutes does nothing
account for* — and a force-directed node-link diagram physically cannot show a hole.

So: **the primary view is a time axis, never a node cloud.** Most interfaces show what
is there. This one shows what is missing, and absence is the most visually arresting
thing on screen.

The vernacular is the **strip chart recorder** — polygraph, seismograph, flight data
recorder. It earns its place three ways: it is the best-evolved interface for
intervals-with-gaps; the product literally has a `polygraph` tool; and an instrument
*records* rather than accuses, which is the project's epistemic position made visual.
A confident-looking verdict machine would undercut the whole thesis.

A node-link graph may appear in **one** place: the provenance chain, which is genuinely a
path and is drawn as a path (section 5.6). Never as the main view.

### Where the impact comes from

Density and precision, not effects. Four moves, in order of value:

1. **Legible density.** Seven channels, 300 minutes, 148 claims, all readable at once.
   The feeling to produce is "this person is operating something serious."
2. **Extreme scale contrast.** A 164px numeral against 10px mono labels, on the same
   screen, with nothing in between.
3. **Motion that reveals mechanism.** The recorder *draws itself*. Claims arrive over
   SSE, so the pen advances across the paper in real time. This is the single biggest
   available move and it is nearly free.
4. **One orchestrated reveal.** At the end of a case, ground truth overlays the claims
   and the lie becomes a visible geometric mismatch. One beat, once.

### Chromatic restraint is what keeps it credible

The chart is near-monochrome. **Light is what the graph can account for; darkness is what
nothing explains.** Colour appears only for hearsay and conflict, so when it appears it
lands hard. Three hues, used rarely, is the entire palette budget.

Glass, glow, neon traces, 3D and gradient washes are **forbidden** (section 7). They would
make an audit tool look like it is guessing.

---

## 2. Research notes (what the reference hunt actually found)

- Dribbble's `data-visualization-dashboard` corner is near-uniformly the look to avoid:
  bento grids, neumorphism, crypto/AI SaaS dashboards, identical rounded stat cards.
- Dribbble's `mission-control` corner is saturated and homogeneous — dozens of
  near-identical drone-fleet and SpaceX concepts. Going full sci-fi HUD trades one
  generic for another.
- The useful corner is **brutalist / Swiss editorial applied to data**. Two shots sit
  closest to this brief: *Systemic Archive — Surveillance Data Interface* (0xOVERFLOWX),
  which pairs brutalist typography with instrument UI, and *Frezpo — Neo-Brutalist HUD &
  Editorial Web Architecture* (özer yılmaztekin), whose own stated principles are
  **extreme scale contrast, chromatic restraint, dual surface tension**. Those three are
  adopted here.
- The position to aim for is **editorial HUD**: the density of a console with the
  typographic discipline of Swiss editorial design.

The image CDN could not be reached from the build environment, so these reads come from
shot metadata and the designers' own descriptions, not from rendering the images.

---

## 3. Tokens

Define these once as CSS custom properties on `:root`. No component invents a colour.

```css
:root {
  /* field */
  --field:        #0A1015;  /* page ground. deep blue-black, never pure black */
  --channel:      #121A20;  /* recorder channel, odd rows */
  --channel-alt:  #0F171D;  /* recorder channel, even rows */
  --rule:         #1E2A32;  /* hairlines, grid, borders */

  /* ink */
  --ink:          #E8EEF0;  /* grounded evidence, display numerals */
  --text:         #C8D4D8;  /* body and labels */
  --text-dim:     #6E8189;  /* apparatus, units, secondary */

  /* semantic, used nowhere decorative */
  --hearsay:      #B8923F;  /* ochre. borrowed light */
  --conflict:     #D84A32;  /* fills and marks */
  --conflict-text:#E05A40;  /* text only, for contrast on --field */
}
```

Verified contrast on `--field`: `--text` 12.8:1, `--text-dim` 4.7:1, `--hearsay` 6.7:1,
`--conflict-text` 5.3:1. `--conflict` at 4.56:1 is for **fills and marks only, never
text** — use `--conflict-text` for type. Do not darken any of these.

A light theme is a straight token swap and nothing else:
`--field:#E9EDEC; --channel:#DCE3E1; --channel-alt:#E4EAE8; --rule:#C3CECB;
--ink:#16242B; --text:#3D4F55; --text-dim:#5A6B70; --hearsay:#6E5B2E;
--conflict:#8A2B20; --conflict-text:#8A2B20;` In the light theme the polarity inverts —
ink is dark on pale stock — so **grounded evidence is the heavy mark either way**. Ship
dark as the default; the demo video is shot in dark.

### Type

Two families, both from Google Fonts. Self-host or load with one `<link>`.

- **Archivo** — 400 body, 500 UI and headings, 600 display numerals. Grotesque, holds up
  condensed and dense.
- **Geist Mono** — 400, 500. For clock values, tick counts, IDs, verdict enum names.

Mono is **earned, not decorative**: clock times and counts are genuinely tabular numeric
data. Do not set prose, buttons or section labels in mono.

```
display   164px / 0.78 / 600 / -0.055em   the one big number
h1         34px / 1.22 / 500 / -0.015em
h2         22px / 1.3  / 500 / -0.01em
body     14.5px / 1.6  / 400
small    12.5px / 1.55 / 400
label      11px        / 400   Geist Mono
micro    10.5px        / 400   Geist Mono — apparatus only
```

Prose lines stay under 80 characters. One display numeral per screen, maximum.

### Space and shape

4px base. Gaps from `{4, 8, 12, 16, 20, 28, 48, 56}`. Page padding 28–48px.

**`border-radius: 0` everywhere.** No shadows. No blur. Separation comes from 1px
`--rule` hairlines and from the channel/channel-alt banding. There is exactly one
exception: nothing.

---

## 4. The fill system (the core of the design)

Five verdicts, encoded in **fill** so the mark carries the meaning. Nothing rides on hue
alone, so it survives grayscale and colourblindness by construction.

| Verdict | Mark | CSS |
|---|---|---|
| `SUPPORTED` | solid, dense | `background: var(--ink)` |
| `INDETERMINATE` | outline, covered part filled | `border: 1px solid var(--ink)` + inner solid child on the covered span |
| `CONTRADICTED` | struck through | `background: var(--conflict)` + 2px `var(--field)` strike at the vertical centre |
| `HEARSAY` | diagonal hatch, visibly secondhand | `border: 1px solid var(--hearsay)` + `repeating-linear-gradient(45deg, var(--hearsay) 0 2px, transparent 2px 7px)` |
| `UNSUPPORTED` | hollow, an empty vessel | `border: 1px dashed var(--text-dim)`, no fill |

Rules:
- **A gap gets no colour.** It is the channel showing through. Absence is rendered as
  absence — never as a grey fill, a pattern, or a "missing" swatch.
- The hatch angle is 45°, always. The hatch is never used for anything but hearsay.
- One sentence must explain the whole system to a judge: *the fill tells you where the
  claim's support came from.* If a mark needs more explanation, it is wrong.

---

## 5. Components

### 5.1 Recorder channel
One row per suspect. Label column 92px, mono 11px, right-aligned. Track fills the rest.
Track height 34px; bars 22px tall, inset 6px top. Hour grid as
`repeating-linear-gradient(to right, var(--rule) 0 1px, transparent 1px 10%)`. Odd rows
`--channel`, even rows `--channel-alt`.

Position is `left: (t0/300)*100%`, width `((t1-t0)/300)*100%`. The axis is always the full
case window, 18:00–23:00, so bars are comparable across channels. Never auto-fit the axis
to the data.

### 5.2 Gap bracket
Under the uncovered span of an `INDETERMINATE` bar: a 6px-tall open bracket
(`border-left`, `border-right`, `border-bottom`, 2px `var(--conflict)`), positioned at the
bar's bottom edge. Add a mono micro label with the minute count when there is room. This
is the most important mark in the product — never let it be subtle.

### 5.3 The pen
A 2px `var(--ink)` vertical rule at the current tick, spanning the whole channel stack
plus 8px of overhang, with a 10px square head at the top. Everything to the right of the
pen is covered by a `var(--field)` veil at `opacity: 0.74` — the paper that has not been
written on yet. The pen is the only element allowed to move on its own.

### 5.4 Scale-contrast readout
The display numeral (164px, 600, -0.055em, `--ink`) with its unit and context set in mono
micro beside it, top-aligned to the numeral's cap height. Nothing between those two
sizes. The number is the selected claim's uncovered minutes, or the case total when
nothing is selected.

### 5.5 Verdict tally
Five rows: mono label 118px, a 240px bar track in `--channel` holding a bar **drawn with
that verdict's own fill**, then the count in mono. The tally teaches the fill system
without a legend, so there is no separate legend anywhere in the product.

### 5.6 Provenance chain
The one place a graph is drawn as a graph, because it is genuinely a path. Agents as
1px-bordered mono chips, joined by 44px 1px connectors, left to right in transmission
order. The chain's terminal state (`ORIGIN_UNSUPPORTED`, `CHAIN_BROKEN`,
`CHAIN_TEMPORAL_VIOLATION`) sets the first chip's border: `--conflict` for an unsupported
origin, `--hearsay` for carriers, dashed `--text-dim` for the final repetition. Connectors
take `--hearsay`; the connector past a broken link takes `--rule`.

### 5.7 Floor plan and route
Rooms as 100×50 boxes, 2px `--ink` border for on-route, 1px `--rule` for off-route.
Corridors as 3px `--ink` bars for the shortest path, 1px `--rule` otherwise, each labelled
with its weight in mono. Endpoints get a filled box with reversed text. Draw the route
`algo.SPpaths` actually returned — never a straight line between endpoints.

### 5.8 Travel arithmetic
Drafting-style dimension bars: a 2px horizontal rule with 2px end ticks, width
proportional to minutes at a fixed scale, labelled in mono. Three rows — available,
shortest path, short by — with the last on a 2px `--conflict` top rule, 3px bars and a
17px mono figure. Show the subtraction; never just state the conclusion.

---

## 6. Views and motion

Three views. Build 6.1 first; it carries the demo.

**6.1 Case board.** Header apparatus strip, scale-contrast readout, verdict tally, the
recorder with its pen, provenance chain at the foot. One screen, no scrolling at 1280×820.

**6.2 Claim inspection.** Selecting a bar fills the readout, materialises its
`SUPPORTED_BY` evidence as a column of mono rows, and lists its gaps. For an
`impossible_travel` contradiction, the floor plan and travel arithmetic take over the
right half.

**6.3 Results.** The benchmark: confusion matrix of five verdicts against four
ground-truth labels, and audit precision/recall. Same tokens, same marks. Build last; a
plain table is acceptable.

### Motion — exactly two things move

1. **The pen advances.** Continuous, linear, matched to the replay clock. Bars appear as
   the pen passes them, with no transition — they are being drawn, not animated in. This
   is the whole personality of the product.
2. **The ground-truth reveal.** Once, at the end: true route segments fade up over the
   claimed ones at 180ms, and mismatches get the `--conflict` strike. One beat.

Everything else is instant. No fade-and-slide on mount, no hover transitions on rows, no
staggered entrances, no skeleton shimmer. `prefers-reduced-motion: reduce` pins the pen to
its final position and makes the reveal a cut.

---

## 7. Forbidden (re-read before calling a component done)

Visual:
- Rounded corners, box-shadows, blur, glassmorphism, neumorphism
- Gradient washes or gradient text; glow, neon, bloom, scanlines; 3D or isometric
- Bento grids; identical rounded stat cards in a 4-up row
- Force-directed node-link diagrams as a primary view
- Any colour not in section 3; any hue used decoratively
- A grey fill or pattern standing in for a gap

Typographic:
- Inter, Roboto, Arial, Open Sans, system-ui as the brand face
- Tracked-out ALL-CAPS eyebrow labels above headings
- Meta strings joined with middle dots (`A · B · C`)
- `WORD — fragment` constructions with a spaced em dash
- A single word in a headline italicised, bolded or recoloured for emphasis
- `→` appended to link or button text
- Mono for prose, buttons or section headings
- Emoji anywhere

Semantic:
- The word "lie", "liar", "lying" or "deception" **anywhere in the UI.** The interface
  reports grounding, never intent. `UNSUPPORTED` means nothing was found, not that
  someone lied. This is the project's central claim; a copy slip undoes it.
- A legend explaining the fills (the tally does that job)
- Confidence scores or percentages the audit engine does not actually compute

---

## 8. Accessibility floor

Real `<button>`, `<a href>`, `<input>` + `<label>`; never `role`/`onClick` on a div.
Visible keyboard focus: 2px `--ink` outline, 2px offset. `aria-label` on every icon-only
control. Decorative SVG `aria-hidden="true"`, meaningful SVG `role="img"` + label.
Touch targets ≥44px. Text 4.5:1, or 3:1 at 24px+. The fill system means no information is
ever carried by hue alone — keep it that way.

The recorder needs a text equivalent: each channel row carries an `aria-label` naming the
suspect, their claim count and their uncovered minutes.

---

## 9. Setting and voice

**Setting: institutional and neutral.** Mundane architectural place names — gallery,
pantry, landing, stair, study, hall. No manor-house dressing, no sci-fi facility, no
fictional chrome in the interface. Two reasons: the country-house reading makes it look
like a themed game rather than a tool, and the research-station reading walks straight
into Dribbble's saturated sci-fi corner. The instrument carries all the character, and
that is consistent with the spec's own framing — the mystery is the testbed, the product
is the audit layer.

Suspect names are plain surnames: reyes, okonjo, vance, sato, mbeki, ferrar, calder.
Lower case in the UI, because they are identifiers in a record.

**Voice.** Flat, precise, declarative. Report what was found and what was not.

- Good: `12 minutes unaccounted` · `support is secondhand` ·
  `nothing in this agent's memory bears on it` · `short by 4 min`
- Bad: `Suspicious!` · `Looks like someone's lying` · `87% confidence` ·
  `Uh oh, we found a contradiction`

Empty states direct rather than apologise: `no claims yet — start an interview`.
Errors state what happened and what to do, in the interface's voice, without apology.

---

## 10. Implementation notes

- React + TypeScript + Vite. Tokens as CSS custom properties in one `tokens.css`; no
  Tailwind, no component library — both pull hard toward the forbidden list.
- The recorder is **DOM, not SVG or canvas.** Absolutely-positioned divs with percentage
  offsets are simpler, inspectable, accessible and fast enough at this scale. Reach for
  D3 only for the floor-plan layout, and even there hand-place the rooms.
- One `<Channel>`, one `<ClaimBar>` taking `verdict` and the coverage spans. The five
  fills live in `ClaimBar` and nowhere else.
- Time maps to percentage once, in a single `tickToPercent(t)` helper. No component does
  its own arithmetic.
- SSE drives the pen and appends bars. The pen's position is the only piece of animated
  state.
- Target 1280×820 for the demo. Below 900px the channel stack scrolls horizontally in an
  `overflow-x: auto` box; it does not reflow or stack, because a broken time axis is
  worse than a scrollbar.

**Deliverable order, matched to the spec's milestones:** the case board and the fill
system during M5, claim inspection next, results last. If M5 runs short, cut the results
view and keep the recorder perfect. A single flawless instrument beats three rough views.
