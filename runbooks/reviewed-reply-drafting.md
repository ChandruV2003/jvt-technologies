# Reviewed Reply Drafting

This is the safe second half of the mailbox workflow.

## Principle

- inbound mail can be imported automatically
- reply drafts can be generated locally
- sending still stays human-controlled

## Current Tool

- `../outreach/mailbox-agent/draft_reply.py`
- `../outreach/tools/reviewed_outreach.sh`

## Input

- one imported mailbox JSON record from `../outreach/inbox/new`

## Output

- one reviewable reply draft in `../outreach/queue/review`
- output filenames include the profile suffix:
  - `*-reply-draft-fast.md`
  - `*-reply-draft-strong.md`

## Recommended Use

1. read the inbound note yourself first
2. run the fast draft helper first:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
./outreach/tools/reviewed_outreach.sh draft-reply-fast outreach/inbox/new/2026-04-09/example.json
```

3. use the stronger draft helper when the reply quality matters more than speed:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
./outreach/tools/reviewed_outreach.sh draft-reply-strong outreach/inbox/new/2026-04-09/example.json
```

4. if needed, override the exact model path with `LOCAL_DRAFT_MODEL_PATH`
5. edit the draft for accuracy and tone
6. send manually from the real mailbox

## Why This Matters

This gives you a real “agent on the Mac” workflow without crossing into autonomous outbound behavior.
