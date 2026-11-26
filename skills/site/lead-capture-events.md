# Lead capture and instrumentation — `ui-engineering-qa.md` §G (moved 2026-09-24, IDs G1–G10 unchanged)

Loaded on demand, not by `paths:`. Read it when building or changing a form, a public/selling page or
analytics events; `/site` stage 8 and `rules/task-lifecycle.md` (selling-surface spec: §G7 events) point here.
Engineering floor: `~/.claude/rules/ui-engineering-qa.md` §A–§D; selling rules: `design-rules.md` (this dir).

## G. Lead capture and instrumentation
1. Field budget: ask only for what the next human step consumes; every field is justified in the
   spec by the name of its consumer. Optional fields sit behind one named disclosure, never block
   submit, and are validated only if the user started typing.
2. No password field unless an account is really created in that step. Invite-only and waitlist
   flows collect no password. Reason: field analytics put password first for abandonment, time and
   error rate (Zuko); only ~45 % of form visitors ever finish a form.
3. Validation timing: on blur, never before first blur; a shown error clears on keystroke as soon as
   the value becomes valid; submit focuses the first invalid field and a summary links to the fields;
   the message says what to do and never just "Неверно".
4. Every submit outcome is designed: loading (controls disabled, aria-busy) · success (what happens
   next, in what time, who does it, where the answer arrives) · failure (a second channel to a human
   plus the entered data preserved). Success text may not promise anything we do not do.
5. Honest availability: if the product AT RELEASE is invite-only, waitlisted or partly unbuilt (the
   owner's product decision), that sentence sits above the form and the CTA label matches it. Dev-time
   gaps (backend in progress, payment/legal pending) never produce such copy (`design-ui-ux.md` §4).
6. Anti-spam without cognitive cost: honeypot + rate limit + submission-timing check. No puzzle
   CAPTCHA, no blocked paste, no blocked password managers (WCAG 2.2 SC 3.3.8).
7. Instrumentation ships with the surface: first-party, no PII in any payload, stable snake_case
   names — page_view(path, referrer_host, viewport_bucket) · section_view(section_id; ≥50 % visible
   ≥1 s) · cta_click(cta_id, label, section_id) · form_start(form_id, first_field) ·
   form_field_error(form_id, field, rule) · form_abandon(form_id, last_field) · form_submit(form_id) ·
   form_result(form_id, ok|error, code) · outbound_contact(channel) · pricing_tier_view(tier_id) ·
   faq_open(question_id). Reason: without form_start and form_field_error you cannot tell "no demand"
   from "the form is broken".
8. Analysis contract: weekly funnel — sessions → section reach in page order → form_start →
   form_submit → accepted lead — plus per-field error and abandon counts and the source path of every
   real lead. A page change is judged against this funnel or it is not judged. Never claim a lift
   without sample size and significance; below a few hundred conversions it is an observation.
9. Privacy: first-party and cookieless by default, IP never stored raw, no session recording on pages
   carrying a PII form, a consent banner only if we actually set non-essential storage, and the
   privacy page lists every event collected.
10. Machine-readable page: every public page ships JSON-LD (Organization / Product / Offer / FAQPage)
    matching the visible text 1:1 — a claim in JSON-LD that is not on the page is a defect.
