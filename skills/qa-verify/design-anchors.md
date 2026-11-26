# Design calibration anchors (read FIRST by design-critic and design-judge; owner-rated set, 2026-09-30)

> **Anchor images are not shipped.** The owner's calibration screenshots (his products and third-party sites) are private, so the table below keeps only the scores and the reasons, and the `anchors/` and `calibration/` paths it mentions do not exist in this plugin. To use this method, build your own anchor set: screenshot 15-25 screens you have rated yourself on the 1-10 scale below (cover every score band, one image per row), keep them in `skills/qa-verify/anchors/` with your scores, replace the table rows with your own, and stitch a few into 2x2 sheets so agents can read them cheaply. Keep a held-out half unrated by the agents for checking drift.

Why: the old anchors (2026-09-26) were our panel's scores and rewarded distinctiveness; measured against the owner's
own 1–10 ratings of 58 screens they did not track him at all (Spearman ρ 0.02, within-1 35 %; analysis
in the owner's private calibration notes). The owner rates a screen by whether it WORKS for its user: you understand what
it is and what to do, it is full of real content, nothing is broken or covering anything. A familiar layout is not
a minus; a distinctive style is not a plus. These anchors are HIS scores on the train half of the calibration set
(test half held out — never add those screens here, the private calibration split). Score by comparing with the
images, not in the abstract. Images: your own anchor screenshots (not shipped, see the note at the top); agents read them as sheets (first screen + score).

## Axes (design-critic step 5; 0–10 each)
- **clarity** — «понятно, что это и что делать»: in 5 s you can say what the product/screen is and the next action;
  the headline says the job in plain words; the primary action is labelled with what happens and sits where the eye
  ends, attached to what it acts on. Low: abstract slogan, jargon, style as the message (monospace or ALL-CAPS mono
  as body/headline, lowercase mono buttons), an art object that does not show what the product does.
- **content** — «реальные данные, не заглушка»: share of the screen that carries real, specific, useful content
  (records, the product's actual output, real templates, prices, commands). Dense and organised beats airy.
  ≤3: stub, 404, empty or guard page, one lone form in a void, placeholder glyphs/tokens, demo filler.
  >35 % of the first viewport empty → ≤5. A focused flow step (sign-in, checkout, install) is judged by its
  specifics, not its density: compact, with the real price / commands / steps → 7–9 (owner: checkout 390
  and install steps 9); the same step lost in a void → ≤3 (connect-form anchor 1). NOT content: logo walls / tech-stack logos, badges, stars, avatar rows,
  marquees, stock or AI imagery, decorative mock visuals — only the product's own output and data count.
- **defects** — 10 = none a user would notice. −3 each: a FOREIGN overlay covering content (cookie bar, toast,
  notification, support/chat bubble, promo popup — an in-product panel shown on purpose as part of the product
  demo is content, not a defect: Linear hero with its agent panel over the app = owner 8, Attio with a cookie box
  over the app = 6), raw template tokens (`{email}`, `{tax_id}`), overlapping text, columns visibly misaligned,
  disabled-looking primary button. −5 each (the owner reads these as "broken"): ANY text cut by a container or
  viewport edge — even a few characters of one code line —, content glued to or bleeding off the viewport edge,
  a primary button placed away from the text it acts on (floating in another column) or visibly broken.
- **scanability at 390** — on phone widths dense is NOT good: rows with >3 lines of small meta text, many chips and
  counters per row → clarity −2 (owner: dense 390 run list 5; calm 390 steps / widget 9).
- **craft** — execution: alignment, spacing rhythm, hierarchy, readable type size and contrast, consistent
  components. Familiar, conventional patterns (admin table, template grid, three-tier pricing) are NOT a craft minus.
- **uniqueness** — "would a similar prompt for another product land here?" Reported for information only; it has
  weight 0 in overall (owner ratings: ρ ≈ 0 with the judge's uniqueness; distinctive dev-style heroes got 1–3).

**overall = min(round(0.35·content + 0.35·clarity + 0.30·craft), defects)** — then the anchor check (mandatory):
name the anchor the screen most resembles (same screen, same product family, same kind); the overall must be within
±1 of that anchor's owner score unless you name, in the `why`, the concrete difference that moves it. The SAME
image as an anchor gets the anchor's score. The owner's median is 6: outside marketing heroes centre on 5–7; 9–10
only for the kind of screens in the 9–10 rows.

**Owner-rejected visual families (overall ≤5 whatever the content, train evidence):** (a) developer-cool —
monospace or ALL-CAPS mono as headline/body, lowercase mono buttons, abstract grids/diagrams instead of the product
(warp 1, factory.ai 3); (b) warm off-white "editorial" canvas + stylised thin display grotesk + black pill buttons
(one product family: home 1, home 390 5, 404 3). Dark is NOT a family: dark working screens got 8–10.

## Scale (owner's scores, train half; his reason in his terms)
| owner | anchor | why (owner's terms) |
|---|---|---|
| 10 | `anchors/owner/10-card-editor-1440.png` (product card editor) | working editor: the real product card on the canvas, every tool, layer and property visible — you can work right now |
| 10 | `anchors/owner/10-admin-outbox-1440.png` (admin outbox) | plain admin list, but every draft is real text with an obvious «Send / Reject»; the error is shown honestly |
| 10 | `anchors/owner/10-canva-templates-1440.png` (Canva product templates) | generic gallery layout, yet it is instantly clear what it is, search + filters, real templates fill the screen |
| 9 | `anchors/owner/9-tile-b-report-hero-1440.png` (style tile B) | plain headline + a real verification report filling half the screen + price on the button |
| 9 | `anchors/owner/9-assistant-widget-390.png` (assistant widget, 390) | you know at once what to ask: ready questions about this page, input at the bottom |
| 8 | `anchors/owner/8-site-hero-r3-1440.png` (site hero) | clear offer, the product's real pipeline as the object; dense but readable |
| 8 | `anchors/good/good-linear-app-1440.png` (Linear app — the "8" scale hint the owner rated against) | the real app, real issues, nothing without information |
| 6 | `anchors/owner/6-attio-cookie-over-1440.png` (attio.com) | fine product page, but the cookie box sits on top of the product (overlay covering content) |
| 5 | `anchors/owner/5-cursor-sparse-1440.png` (cursor.com) | small headline, a painting behind the product, the first screen mostly air |
| 5 | `anchors/owner/5-dense-run-list-390.png` (run list, 390) | real data, but every row crams 4–5 lines of tiny meta, chips and counters — hard to scan on a phone |
| 4 | `anchors/owner/4-shipfast-logo-soup-1440.png` (shipfa.st) | a highlighted word, a blob of tech logos, stars and avatars — no product of its own on the screen |
| 4 | `anchors/owner/4-tile-a-text-wall-390.png` (style tile A, 390) | dark text wall: a long paragraph, no product visible on the first screen |
| 3 | `anchors/owner/3-404-placeholders-1440.png` (404 stub) | a stub, half empty, raw `{email}` / `{tax_id}` tokens in the footer |
| 2 | `anchors/owner/2-price-band-bleeds-1320.png` (price band) | content glued to the left edge, the right card cut off by the viewport — looks broken |
| 1 | `anchors/owner/1-warp-mono-abstract-1440.png` (warp.dev) | monospace everything, lowercase mono buttons, an abstract grid of squares — nothing to understand, "developer-cool" |
| 1 | `anchors/owner/1-product-home-1440.png` (product home) | stylised type, the «Попробовать бесплатно» button floats on the right away from its text (on round 1 of this page: «сломанная кнопка … не в том месте») |
| 1 | `anchors/owner/1-connect-form-void-1440.png` (connect step) | one small form in a dark void, 60 % empty, a muddy disabled-looking main button, a letter as the logo |

## How to use
- Read every anchor above before scoring. Per screen: find the two anchors it most resembles, score the five axes,
  compute overall, and sanity-check it against those anchors' owner scores. "Higher than the anchor" needs one
  sentence saying what this screen does that the anchor does not.
- Working app screens with real data and no defects belong at 8–10 even when the layout is standard; a stylish
  hero that does not say what the product is or shows no real content belongs at 1–4.
- Correctness floors are not taste and stay separate (a11y, overflow, target size: `ui-engineering-qa.md`,
  `ui-qa-protocol.md` §E) — a defect above is ALSO a finding in the panel report.
- Refresh: add screens the owner rates or comments on (his score + his words), never from our taste; keep ≤18;
  never add screens from the calibration test half (it stops being held out).
