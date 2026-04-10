# Reviewed Reply Drafting

This is the safe second half of the mailbox workflow.

## Principle

- inbound mail can be imported automatically
- reply drafts can be generated locally
- sending still stays human-controlled

## Current Tool

- `../outreach/mailbox-agent/draft_reply.py`

## Input

- one imported mailbox JSON record from `../outreach/inbox/new`

## Output

- one reviewable reply draft in `../outreach/queue/review`

## Recommended Use

1. read the inbound note yourself first
2. run the draft helper
3. edit the draft for accuracy and tone
4. send manually from the real mailbox

## Why This Matters

This gives you a real “agent on the Mac” workflow without crossing into autonomous outbound behavior.
