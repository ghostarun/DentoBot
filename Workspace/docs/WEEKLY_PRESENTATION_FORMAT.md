# Weekly meeting presentation format

Agreed with Tarun on 6 October 2026. Use this guide when preparing future DentoBot weekly meeting presentations.

## Purpose and reference

Communicate what was accomplished, show the evidence and identify what needs team discussion. Keep the presentation simple enough to explain verbally.

Visual reference: `/home/tarun/Downloads/Tarun_weeklyupdate_Oct6.pptx`, reviewed across all six slides. Use a copy when assembling a new deck. Preserve the familiar style, while correcting its overlapping titles and clipped captions. Its technical results are historical examples, not reusable current claims.

## Visual format

- Use 16:9 slides, a white background and black text.
- Use large, consistent headings and bold opening phrases in bullets.
- Keep slide 1 text only. Use concise bullets or numbered points.
- For evidence slides, favour one large screenshot with a short takeaway caption. Use a simple table when comparing cases is clearer.
- Reserve separate space for title, image and caption. Keep all content inside the slide edges.
- Crop screenshots to the relevant anatomy, robot pose or diagnostic result. Avoid shrinking the entire application until its text is unreadable.
- Use a simple arrow or outline only when it helps locate the collision, changed geometry or key value.
- Avoid decorative graphics, complex layouts and unnecessary animation. Use actual retained evidence images.
- Start around 32–40 pt for titles and 22–28 pt for body text, then judge readability at presentation size. Shorten content before reducing the font.

## Default six-slide structure

The six-slide structure is the current default. Adjust it for a future meeting only when the content or operator request warrants it.

| Slide | Purpose | Content |
|---|---|---|
| 1 | Weekly accomplishments | Text only. About 5–7 outcome-level bullets, normally one or two lines each. Cover main and secondary accomplishments. |
| 2 | Main problem or objective | Explain the starting condition and the constraint being addressed. Include one useful setup image. |
| 3 | What changed | Explain the correction or investigation and why it matters. Show focused evidence or a simple before/after comparison. |
| 4 | Results and case comparison | Present the strongest current results, relevant failures and each case's takeaway. Use a simple table or evidence image. |
| 5 | Verification and remaining limits | Show why the result is credible and what remains unproven. Keep detailed diagnostics in notes/report. |
| 6 | Questions and next steps | List the few decisions needed from the team in priority order, followed by the next evidence to collect. |

Do not add a separate title slide when six slides are requested with the overview first. Avoid turning the last slide into a dense numerical results page.

## Writing each slide

Give each slide a specific title that conveys its result or question. Avoid repeating “Current week progress” on every slide.

Examples of useful titles:

- “FDI14: shortened drilling achieved at 40 mm”
- “Template–spindle contact limits drilling depth”
- “Team decision: which clearance change should we evaluate?”

For a typical evidence slide, use **one specific title, one clear evidence image and one takeaway**. Under the image, separate observation from explanation when needed:

- **Observed:** approach planning failed at this configuration.
- **Finding:** diagnostics identified a colliding intermediate approach goal.

Use “hypothesis” or “under investigation” when the cause is unproven. Describe the result in plain language. Keep function names, test inventories and implementation details in speaker notes unless they are necessary for the team's decision.

## Preparing the weekly overview

1. Review the development logbooks for the stated reporting dates and follow relevant task evidence.
2. Compile a retrospective checklist of completed deliverables, including secondary work such as persistence, usability, templates, performance, integration and evidence tooling.
3. Consolidate repeated attempts and related fixes into meaningful outcomes. Do not present failed attempts or proposals as completed features.
4. Compress the checklist into the slide's 5–7 strongest bullets. Keep the detailed checklist linked from the report rather than squeezing it onto the slide.
5. Distinguish implemented, host-checked, runtime-demonstrated and operator-accepted work. Preserve pending acceptance under the existing task/backlog owner.

An overview bullet should say what improved and why it matters. Include a measured number only when its conditions and provenance are established.

## Results and evidence wording

- State the case and relevant configuration: target tooth, opening, Base adjustment and collision-policy exceptions where applicable.
- Distinguish a diagnostic route, a guarded preview and a complete cycle. A waypoint count alone does not establish full workflow success.
- Explicitly report shortened drilling and achieved/requested depth. A completed shortened cycle does not mean full requested depth.
- State whether spindle collision checking was active when that changes the interpretation.
- Separate case series and configurations. Do not combine them into one implied uniform reliability trial.
- Label historical, reconstructed and ghost views. Replace superseded results or show their dates and historical role clearly.
- Qualify fixture-specific or mixed-build performance measurements. Do not generalize them to other configurations or platforms.
- Keep simulation results separate from controller, hardware and physical/clinical validation.
- Keep source/run references and detailed caveats in the report or speaker notes, while retaining any condition needed to interpret the slide correctly on the slide itself.

## Discussion slide

Ask questions that lead to a decision, measurement or agreed boundary. State what input is needed from the team. Keep priorities visible and avoid presenting the entire backlog.

Example pattern:

- **Decision needed:** which template/tool clearance change should be evaluated first?
- **Evidence needed:** compare useful drilling depth and collision results under the agreed change.

The slide summarizes existing plans. It does not create a second pending-work queue or authorize new runtime/hardware activity.

## Before presenting

- [ ] Reporting dates and case names are correct.
- [ ] Slide 1 covers both main and secondary accomplishments without excessive detail.
- [ ] Each slide has one clear point and a specific title.
- [ ] Screenshots show the relevant evidence at readable size.
- [ ] Titles, images and captions do not overlap or extend outside the slide.
- [ ] Captions explain what the audience should notice.
- [ ] Claims match the latest evidence and identify important configuration limits.
- [ ] Shortened depth, diagnostic-only results and pending acceptance are explicit where relevant.
- [ ] Detailed numbers and source references are available in notes/report.
- [ ] The final slide makes the team's requested decisions clear.
- [ ] Every slide has been rendered and visually inspected at presentation size.
- [ ] The reference deck remains unchanged and the new deck has a distinct filename.

Current example: `data/dentobot-runs/2026-10-06/weekly-report-20261006-S6-LIVE-01/SLIDE_CONTENT_DRAFT.md` in the Ubuntu overlay. This guide records the reusable format; dated reports hold case facts and results.
