# Mailbox Agent

This folder contains the conservative inbound-email listener scaffold for `JVT Technologies`.

## Purpose

- watch a real mailbox only after domain and mailbox setup are complete
- save new inbound mail into a local review queue
- avoid auto-replying or auto-sending
- keep a simple state file so the same messages are not re-imported repeatedly

## Current Scope

- IMAP polling only
- local JSON + `.eml` capture for review
- no outbound send path
- no auto-triage beyond metadata normalization
- launchd template included, but not installed
- local reply-draft helper included, but not auto-triggered

## Safe Usage

1. copy `.env.example` to a local non-repo `.env` or export vars in the shell
2. verify the mailbox manually first
3. run the listener in `--once` mode to confirm it can read mail safely
4. review imported messages under `../inbox/new`
5. decide later whether to turn it into a scheduled local service

## Optional Next Step

To draft a reply from an imported inbox item without sending anything:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/mailbox-agent
python3 draft_reply.py --message-json ../inbox/new/2026-04-09/example.json
```
