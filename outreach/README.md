# Outreach

This is a conservative outbound workspace for `JVT Technologies`.

## Guardrails

- no mass-send engine
- no autonomous bulk outreach
- no invented urgency
- no fake personalization
- no sending without review

## Queue Model

- `draft`: generated but not yet reviewed
- `review`: under human revision
- `approved`: ready to send manually
- `sent`: manually sent and logged
- `replied`: active conversation state

## Inbound Mail Handling

- `inbox/new`: newly imported inbound messages from the mailbox listener
- `inbox/reviewed`: triaged messages that have been handled by a human
- `inbox/closed`: archived conversations or resolved inbound items

The mailbox listener is intentionally receive-only until a real mailbox is configured.

## Draft Workflow

1. choose a real target
2. load lead data from the local lead database
3. pick a template
4. provide a real contact name and a specific fit reason
5. generate a draft into `queue/draft`
6. review and revise
7. move only approved drafts forward

The draft tool can now produce:

- markdown review packets
- plain-text send-ready bodies
- styled HTML email bodies
- JSON metadata for future send/reply tooling

No sending integration is configured here.

## Shared Config

Use `./.env.local` for real local values once the domain and mailbox exist.

Start from:

- [outreach/.env.example](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/.env.example)

Then generate the first reviewed wave with:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/generate_first_wave.sh
```
