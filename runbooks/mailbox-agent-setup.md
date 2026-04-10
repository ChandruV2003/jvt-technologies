# Mailbox Agent Setup

This runbook describes how to turn the local mailbox listener into a real receive-only assistant once the JVT domain and mailbox exist.

## Purpose

- watch a real JVT inbox from `m4-mac-mini`
- save inbound mail locally for review
- avoid missed replies
- keep human approval in the loop

## What It Does

- connects over IMAP
- reads only the configured mailbox folder
- imports new messages into `../outreach/inbox/new`
- stores a local UID checkpoint in `../outreach/mailbox-agent/state`

## What It Does Not Do

- it does not send email
- it does not auto-reply
- it does not auto-approve follow-ups
- it does not alter host routing or other services

## Setup Checklist

1. create the real JVT mailbox
2. gather IMAP host, port, username, and password or app password
3. copy `../outreach/mailbox-agent/.env.example` into a local non-repo env file
4. test the mailbox manually first
5. run the listener once:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab/JVT-Technologies/outreach/mailbox-agent
python3 mailbox_listener.py --once
```

6. inspect `../inbox/new`
7. only after that, consider running it on an interval

## Recommended Launch Model

- start with manual `--once`
- then run it on a low-frequency loop or scheduled interval
- do not make it a long-lived autonomous responder until the review workflow is stable
