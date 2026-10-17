# ALIBI — Design brief

Companion to `ALIBI_SPEC.md`. Note: read this before writing any frontend code,
and re-read section 7 before you think a component is finished.

> **Amended 2026-10-17.** The first direction, an editorial strip-chart HUD in
> near-monochrome, was built and judged bland: correct, but with no personality.
> The board is now an **8-bit mystery**: a pixel house, an RPG case log, a level
> strip, and a pixel-art pocket recorder the operator holds. The target artboard is
> direction 5 in `docs/design/directions/` (serve the repo root, open
> `/docs/design/directions/#5`). The old artboards in `docs/design/*.dc.html` are
> kept for history and are no longer the target. What did not change is the
> thesis in section 1 and every semantic rule in section 7.

---

## 1. The philosophy: the hole is the hero

Alibi's load-bearing data is **temporal interval coverage**, not graph topology. The
question a viewer must be able to answer in two seconds is *which minutes does nothing
account for*. The board shows that twice. On the level strip, a gap is the empty
track between bars. In the house, a suspect whose own account has no entry for the
current minute stands in **the void**, the one dark cell of the floor plan. Absence
is still the most arresting thing on screen.

### Why a game

The mystery is the testbed and the audit is the product, so the game skin has to
carry the audit, not hide it. The references that earn their place are the
inspection games, not the arcade:

- **Papers, Please.** You check records against each other and the game links the
  two fields that disagree. That is the contradiction mechanic, so a contradiction
  here is drawn the same way: a ghost where the claim says, a solid sprite where
  the memory says, and a red link between them.
- **Return of the Obra Dinn.** A deduction game drawn in a strict palette with
  dithering for texture. Dithering is how 8-bit art encodes texture without leaning
  on hue, which is exactly what the fill system needs.

It also says something true about the project: it does not take itself too
seriously, and it has a personality.

### What the game may never become

A verdict machine. Nothing on screen wins, loses, catches or accuses. The audit
reports grounding; the game skin makes that fun to read. A contradiction is an
"!" and a link between two places, never a judgement of a person. See section 7.

---

## 2. Research notes

The first reference hunt (Dribbble's data-viz and mission-control corners, brutalist
and Swiss editorial instrument UI) produced the editorial-HUD direction. It is
recorded in git history and in the four exploration mockups. The game direction
draws on the two inspection games above, on fantasy-console palettes (sixteen fixed
colours), on JRPG menu windows, and on the pocket cassette recorder, because the
board is a replay and the case is literally played back from a tape.

---

## 3. Tokens

Define these once as CSS custom properties on `:root`. No component invents a colour.
The palette is sixteen colours, fixed. There is no light theme.

```css
:root {
  --black:  #000000;  /* the ground, outlines, the void */
  --night:  #1d2b53;  /* window fill */
  --plum:   #7e2553;
  --forest: #008751;
  --brown:  #ab5236;
  --stone:  #5f574f;  /* corridors, dashed outlines; never small text */
  --silver: #c2c3c7;  /* secondary text, the recorder body */
  --cream:  #fff1e8;  /* grounded evidence, primary text */
  --red:    #ff004d;  /* conflict, marks and text on black only */
  --orange: #ffa300;  /* hearsay */
  --yellow: #ffec27;  /* the playhead, focus, window titles */
  --lime:   #00e436;  /* the recorder's LCD and lamps */
  --sky:    #29adff;
  --lav:    #83769c;  /* inner window rule */
  --pink:   #ff77a8;
  --peach:  #ffccaa;  /* skin */
}
```

**Semantic colour, used nowhere decorative:** `--cream` is grounded evidence,
`--orange` is hearsay, `--red` is conflict. The other thirteen dress the house:
floors, sprites, the recorder body. A sprite's coat colour identifies a suspect and
carries no verdict.

**Contrast pairs that pass 4.5:1 for small text:** cream, silver, yellow, orange,
lime, red on `--black`; cream, silver, yellow on `--night`; night on silver. Red text
goes on black only. Stone is never text.

### Type

Two faces, both from Google Fonts, loaded with one `<link>`.

- **Press Start 2P** — labels, names, numerals, window titles, keys. Sizes in whole
  pixels from 6 to 26. It is all caps by nature, so caps are the voice, not an effect.
- **VT323** — sentences: case-log lines, speech bubbles. 13px minimum, 18px or more
  for anything a reader has to take in.

### Space and shape

A 4px pixel grid. Positions and sizes snap to it wherever the art can. `border-radius:
0` everywhere; a round thing (a knob, a reel) is pixel art. No box-shadow and no
text-shadow: depth comes from outlines, highlights and pixel shading drawn in the art.
A window is a cream rule outside a black rule outside a lavender rule, built from
nested borders.

---

## 4. The fill system (the core of the design)

Five verdicts, encoded in **fill** so the mark carries the meaning. Nothing rides on hue
alone, so it survives grayscale and colourblindness by construction.

| Verdict | Mark | CSS |
|---|---|---|
| `SUPPORTED` | solid | `background: var(--cream)` |
| `INDETERMINATE` | outline, covered part filled | `border: 2px solid var(--cream)` + inner solid child on the covered span |
| `CONTRADICTED` | struck through | `background: var(--red)` + 2px `var(--black)` strike at the vertical centre |
| `HEARSAY` | dithered, visibly secondhand | `border: 2px solid var(--orange)` + a 2px checker dither of `--orange` |
| `UNSUPPORTED` | hollow, an empty vessel | `border: 2px dashed var(--stone)`, no fill |

Rules:
- **A gap gets no colour.** It is the track showing through. Never a grey fill, a
  pattern, or a "missing" swatch.
- The checker dither is hearsay's and nothing else's. (It replaces the first
  direction's 45° hatch: a dither is the pixel-native way to say "half there".)
- In the house the same encoding applies to people. A suspect placed by a supported
  claim is a solid sprite. A suspect placed by a contradicted claim is a **ghost**: a
  cream sprite drawn in a checker dither, with a red "!" and a red link to the place
  the conflicting memory names. A suspect with no account for the minute stands in
  the void.
- One sentence still explains the whole system: *the fill tells you where the
  claim's support came from.*

---

## 5. Components

### 5.1 HUD
One line across the top: the `ALIBI` title, the case id, the clock at the
playhead, an `AUDITED` meter with the real audited/claims count, the seed.

### 5.2 Windows
JRPG menu windows: night fill, nested cream, black and lavender rules, a black title
tab in yellow Press Start 2P breaking the top edge.

### 5.3 The house
The public floor plan, top-down, hand-placed on a 3×4 grid so every corridor runs
along a gutter. The twelfth cell is **the void**. Rooms have pixel floor patterns and
a name plate. Corridors are dashed stone paths with their walk in minutes in a small
box. The incident room has a red frame and its window on a red plate; the frame
blinks while the playhead is inside the incident window.

Each suspect stands where **their own account** places them at the playhead minute
(section 4 for solid, ghost and void). A suspect's claim about someone else, at that
minute, can appear as one speech bubble per room: the sentence in VT323, and a
Press Start tag saying how it is held (`HEARD, NOT SEEN`, `SEEN`, `PARTLY SEEN`).
Sprites and bubbles are buttons that select the claim behind them.

### 5.4 Case log
The selected claim: the speaker's portrait, what they say, what their own memory
holds, the verdict badge drawn with its own fill. Then what other suspects said
about the same person in the same window: who saw it, and who heard it, with each
hearsay trail as a row of chips (section 5.5). With nothing selected, it directs:
`SELECT A CLAIM ON THE TIMELINE, OR A SUSPECT IN THE HOUSE.`

### 5.5 Trails (the provenance chain)
One row per hearsay claim: the carrier's chip, a pixel arrow, the end of the trail,
and the outcome in VT323. The end chip follows the chain's terminal state, and an
unresolved chain never names an origin:

| Terminal | End chip | Outcome |
|---|---|---|
| `ORIGIN_WITNESSED` | origin, cream rule | `TRAIL ENDS AT X, WHO SAW IT` |
| `ORIGIN_UNSUPPORTED` | origin, red rule | `TRAIL ENDS AT X, NOTHING BEHIND IT` |
| `ORIGIN_CONTRADICTED` | origin, red rule | `TRAIL ENDS AT X` |
| `CHAIN_BROKEN` | `???`, dashed | `NO SUCH RECORD` |
| `CHAIN_TEMPORAL_VIOLATION` | cited agent, dashed | `TOLD N MIN EARLY` |
| `CHAIN_CYCLE` | cited agent, dashed | `GOES IN A CIRCLE` |
| `CHAIN_TOO_DEEP` | `...`, dashed | `TOO LONG TO FOLLOW` |

### 5.6 Inventory (the verdict tally)
Five item slots, each holding its verdict's fill with the count under it. It teaches
the fill system, so there is no separate legend anywhere.

### 5.7 Level strip (the recorder)
One row per suspect: a one-scale pixel head, the name, and a track holding that
suspect's **claims about themselves**, lane-packed so no two bars overlap. Under them,
`RE: <NAME>` holds what everyone else said about the selected claim's subject. The
axis is always the full case window, 18:00–23:00; never auto-fit it. Positions go
through `tickToPercent` and nowhere else. The playhead is a yellow rule with a pixel
magnifier riding on top; everything right of it is under a black checker **fog** that
lifts as the playhead passes. An INDETERMINATE bar carries the red open bracket under
its uncovered span (with the minute count when there is room).

### 5.8 The pocket recorder
The hardware toy, redrawn as pixel art in the same sixteen colours and holding the
replay. It is the real control surface, not decoration.

| Part | What it is |
|---|---|
| Piano keys | REC, PLAY, REW, FF, STOP, PAUSE. PLAY and PAUSE drive the replay; REW goes back to 18:00; FF goes to 23:00; the pressed key sits down. |
| Cassette | The reels turn while playing; each tape pack is sized from the playhead. The label is the seed: same tape, same evening. |
| LCD | The playhead clock, the mode and speed, and a marquee of the selected claim. |
| Counter | The playhead tick. |
| RX lamp and antenna | Light when a claim has just been drawn. |
| Polygraph slip | A pixel trace fed under a needle as the replay runs. The needle swings by how many suspects have no account for each minute. The pips are the detective's budget of two traces. |
| Speed knob | 1x, 2x, 4x. |
| Sticker | `HEARD != SEEN`. |

### 5.9 Claim inspection (6.2, not yet built)
The floor-plan route and the travel arithmetic carry over from the first direction
in meaning: draw the route `algo.SPpaths` returned, never a straight line, and show
the subtraction. They are redrawn in this palette on the house map.

---

## 6. Views and motion

**6.1 Case board.** HUD, the house (left), the case log (right), the level strip
(bottom left), the pocket recorder (bottom right). One screen, no scrolling at
1280×820. **6.2 Claim inspection** and **6.3 Results** follow.

### Motion

Every animation runs on `steps()`. Things jump between frames the way 8-bit
hardware drew them; nothing eases, fades or slides. What moves:

1. **The playhead advances**, continuous and linear, driven by the replay clock.
   Bars appear as it passes them, with no transition.
2. **The house idles.** Sprites bob a frame. A ghost flickers between its two dither
   phases. The contradiction link marches. The incident frame blinks while the
   playhead is inside the incident window.
3. **The fog boils** by shifting its dither a pixel.
4. **The recorder runs.** Reels turn in three frames, the LCD marquee scrolls, the
   REC lamp blinks, the RX lamp lights on a new claim, the polygraph slip feeds.
   Pause stops all of it.

`prefers-reduced-motion: reduce` pins the replay to 23:00, paused, and stops every
animation.

---

## 7. Forbidden (re-read before calling a component done)

Visual:
- Rounded corners, box-shadow, text-shadow, blur, glow, glassmorphism, neumorphism
- Smooth gradients of any kind; a hard-stop repeating gradient is allowed only to
  draw a pixel pattern (a dither, a floor, a grid)
- Transitions, easing, or any animation not on `steps()`
- Rotated, skewed or fractionally scaled pixel art **inside the board**. The board
  as a whole is scaled to fill the window (section 10), which keeps every position
  exact where reflowing would not; no part of it is ever scaled alone
- Any colour not in section 3; any semantic colour (cream, orange, red) used decoratively
- A grey fill or pattern standing in for a gap
- Force-directed node-link diagrams; the house is hand-placed

Typographic:
- Any face but Press Start 2P and VT323; in particular Inter, Roboto, Arial, Open
  Sans, system-ui
- Press Start 2P below 6px, VT323 below 13px
- Meta strings joined with middle dots (`A · B · C`)
- `→` appended to link or button text
- Emoji anywhere, including as icons; every icon is pixel art

Semantic:
- The word "lie", "liar", "lying" or "deception" **anywhere in the UI.** The interface
  reports grounding, never intent.
- Game words that judge a person: `GUILTY`, `CAUGHT`, `BUSTED`, `CULPRIT`, `KILLER`,
  `MURDERER`, `SUSPICIOUS`, `OBJECTION`, `WANTED`, `GAME OVER`
- Win or lose states, lives, health bars or a guilt score on a suspect. The ranking
  is a reading order, not a high-score table.
- Ground truth on screen. It is referee-only; the board shows what was proved.
- An easter egg that reveals or hints at ground truth
- A legend explaining the fills (the inventory does that job)
- Confidence scores or percentages the audit engine does not actually compute

---

## 8. Accessibility floor

Real `<button>`, `<a href>`, `<input>` + `<label>`; never `role`/`onClick` on a div.
Visible keyboard focus: 2px `--yellow` outline, 2px offset. `aria-label` on every
icon-only control, including each piano key and the knob. Decorative SVG
`aria-hidden="true"`. Text at 4.5:1 using only the pairs in section 3. The fill
system means no information is carried by hue alone; keep it that way.

The level strip needs a text equivalent: each row carries an `aria-label` naming the
suspect, their claim count and their uncovered minutes. Claim bars are data marks
and stay smaller than 44px; every one is also reachable by keyboard, and every
sprite and bubble is a button for the same claim.

Keyboard: `Space` plays and pauses (when focus is not on a control), `Esc` clears the
selection. The key hints on the strip name these real keys.

---

## 9. Setting and voice

**Setting.** The house is the world generator's floor plan, drawn as a game map.
No fictional chrome beyond what the data has: rooms, corridors, suspects, an incident.

Suspect names come from the case file and are shown in caps, because the face is.

**Voice.** Deadpan, game-world, precise. Report what was found and what was not.

- Good: `NO ACCOUNT FROM 19:52` · `HEARD, NOT SEEN` · `TRAIL ENDS AT DARA` ·
  `TOLD 1 MIN EARLY` · `CHEATS OFF. THE AUDIT ONLY TAKES EVIDENCE.`
- Bad: `LIAR!` · `CAUGHT YOU` · `GUILTY` · `87% SUSPICIOUS` · `GAME OVER, DARA`

(Those examples are quoted in this brief only; the middle dots between them are this
document's, not the UI's.)

Empty states direct rather than apologise: `SELECT A CLAIM ON THE TIMELINE, OR A
SUSPECT IN THE HOUSE.`

---

## 10. Implementation notes

- React + TypeScript + Vite. Tokens as CSS custom properties in one `tokens.css`;
  no Tailwind, no component library.
- The board is **DOM and inline SVG**, not canvas. Pixel art is SVG with
  `shape-rendering="crispEdges"` on a whole-number grid.
- One `<Channel>`, one `<ClaimBar>`. The five fills live in `ClaimBar` and nowhere
  else; anything else that shows a fill (the inventory, the badge) asks `ClaimBar`
  for it.
- Time maps to percentage once, in a single `tickToPercent(t)` helper.
- The replay clock is the only source of the playhead. The recorder drives it; SSE
  will drive it later.
- The board is laid out at 1280×820 and **fills the window**: the whole board is
  scaled as one piece to whatever the window gives, down on a small one and up on a
  large one, until one side of the board meets one side of the window. Whatever is
  left on the other side is split evenly, so the board is centred on the screen in
  its own black. It still never reflows, because a broken map or time axis is worse
  than one at another size. The scale is `--fit`, measured in `App` from the window
  and the board's own size, and applied as `zoom` on `.board`. Nothing else reads
  it, and nothing inside the board is ever scaled on its own.

**Deliverable order:** the case board first, claim inspection next, results last.
