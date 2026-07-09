# JVT Service-Line Execution Board

Updated: 2026-06-24

Goal: create sellable proof assets and real conversation paths for JVT's near-term service wedges.

Success metric: 5 real owner/operator conversations per week and at least 1 paid-pilot proposal path.

## Active Wedges

| Priority | Wedge | First proof asset | Pricing test | Next action |
| --- | --- | --- | --- | --- |
| 1 | AI receptionist / voice intake | Public dry-run intake demo page with three synthetic scenarios and paid-pilot homepage panel | $750 setup + $300-$500/mo support, usage billed separately | Send and monitor the proof-backed follow-up packets queued for verified public inboxes |
| 2 | Meeting-to-action packets | Public synthetic transcript-to-action packet demo page + proof PDF | $300/mo or $75 per meeting packet | Send and monitor the proof-backed follow-up packets queued for verified accounting/advisory prospects |
| 3 | Workflow automation cleanup | Before/after map using JVT's own ops | $1,500 fixed project | Turn the workflow map into a one-page public case study |
| 4 | Inbox and document triage | Public proof page plus sanitized JVT mailbox listener case study | $1,500 setup + $500/mo support | Use the deployed proof page in outreach to shared-inbox-heavy offices |
| 5 | Document packet generator | Synthetic CPA and law-firm packets | $1,000 setup + $500/mo support | Package examples for website or PDF download |

## Completed Today

- Sent 10 quality-gated follow-up emails to older no-reply prospects.
- Fixed sender daily-limit accounting so follow-ups count by `sent_at`, not filename date.
- Raised sender defaults to 5 packets/run and 10 total outbound/day.
- Confirmed the new cold-wave generator currently has no eligible undeduped public-email leads.
- Added smart crypto mining as a speculative feasibility track, not an active JVT service wedge.
- AI receptionist / voice intake: created 3 synthetic caller scenarios and ran them through the dry-run `/api/test-intake` endpoint.
- Generated intake packets for missed-sales-call, existing-client-admin-request, and wrong-fit-caller scenarios.
- Published public demo pages for AI receptionist / voice intake and meeting-to-action packets.
- Added watchdog and follow-up status surfaces to the control panel.
- Added follow-up packet generation for older no-reply sent outreach.
- Created downloadable proof PDFs for AI receptionist and meeting-to-action demos.
- Built offer-specific candidate lists for AI receptionist and meeting-to-action.
- Wrote the inbox/document triage case study.
- Wrote the lead-to-follow-up workflow automation map.
- Created synthetic CPA onboarding and law-firm intake packet examples.
- Added a concrete AI receptionist paid-pilot panel to the homepage.
- Created the `ai-receptionist-paid-pilot.md` outreach variant.
- Published `site/inbox-document-triage-demo.html` and linked it from the homepage service and demo sections.
- Created downloadable `site/proof-assets/inbox-document-triage-proof.pdf`.
- Updated the inbox/document triage case study with the 1,795-item mailbox run and synthetic public proof boundary.
- Generated five proof-backed, quality-gated outreach packets for verified public business inboxes.
- Held the extra five-packet send because the configured daily sender cap had already reached 16 of 20 messages.
- Fixed lead-research cadence docs/install defaults to hourly so the watchdog threshold matches the live agent.
- Isolated lead-screening model stderr into per-candidate status instead of polluting global logs.
- Added TCP pressure and auto-send summaries to the control panel status and watchdog views.
- Deployed the new site build to Cloudflare Pages and verified the inbox triage proof page on production.

## Red Lines

- No autonomous legal, tax, medical, financial, or investment advice.
- No outbound AI calls without opt-in/compliance review.
- No prospect emails without explicit authorization.
- No spending or provider signup without approval.
- No crypto mining hardware purchase, miner process, live trading, or custody setup without separate approval.

## Speculative Revenue Tracks

| Track | Status | Next validation |
| --- | --- | --- |
| Smart crypto mining / profitability monitor | Research only | Build a read-only profitability calculator before considering any hardware or mining process |
