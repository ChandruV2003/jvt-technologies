# Outbound Review Workflow

## Principle

JVT Technologies should use low-volume, high-quality outreach with human review.

## Workflow

1. identify a target
2. record lead data and fit score
3. choose an outreach template
4. add a real contact name and a defensible fit reason
5. generate a personalized draft
6. move the draft to review
7. approve or revise
8. send manually or through a future low-volume reviewed path
9. log reply and follow-up status

## Current Tools

- lead schema and CSV import tooling under `../lead-pipeline`
- draft generator under `../outreach/tools/generate_draft.py`
- reviewed templates under `../outreach/templates`
- styled HTML templates under `../outreach/templates/html`
- queue states under `../outreach/queue`
- inbound capture under `../outreach/inbox`
- mailbox listener scaffold under `../outreach/mailbox-agent`

## Current Rule

The system may generate drafts and ingest inbound mail metadata, but it does not send mail.

## What Not To Do

- do not mass-send
- do not scrape indiscriminately
- do not auto-send high-volume mail
- do not pretend to be a past vendor or client
- do not use fake urgency

## Current Recommended Path

1. import a small set of real leads
2. generate no more than a few reviewed drafts at a time
3. send manually from the eventual real mailbox
4. let the inbound listener watch for replies once mailbox credentials exist
5. review every reply before drafting the next response
