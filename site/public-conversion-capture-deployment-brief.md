# Public Conversion Capture Deployment Brief

## What changed

- The public site now contains a first-party workflow-intake form that posts to `/api/workflow-intake`.
- `site/functions/api/workflow-intake.js` is a Cloudflare Pages Function for the same route.
- The function stores form view/start events, completed submissions, duplicate markers, and attribution in Cloudflare KV.
- The M4 reconciliation adapter is `ops/agent-control/public_conversion_intake.py`; it writes local durable submission records, creates an inbox-style handoff, and upserts into the canonical account/contact/opportunity/commercial pipeline.

## Required Cloudflare configuration

The existing Cloudflare Pages project `jvt-technologies-site` needs one KV namespace binding:

- Binding name: `JVT_CONVERSION_INTAKE`
- Used by: `site/functions/api/workflow-intake.js`
- Stored key prefixes:
  - `event:view:<submission_id>`
  - `event:start:<submission_id>`
  - `submission:<submission_id>`
  - `dedupe:<sha256>`
  - `event-log:<iso_timestamp>:<event_type>:<submission_id>`

No deployment was run, no paid service was created, and no Cloudflare account setting was changed.

## Production activation gate

The current implementation is a locally validated capture and reconciliation
capability. It is not production-complete until all of these are in place:

- create and bind the `JVT_CONVERSION_INTAKE` KV namespace
- add abuse protection and a bounded rate limit for event and submission writes
- add an authenticated, idempotent M4 import job for new KV submission records
- prove that one production-like submission reaches the canonical opportunity
  ledger once and is visible in the control panel

Do not deploy the public form before this gate is complete. A KV record that
never reaches the M4 pipeline would create an invisible lead.

The production importer is `ops/agent-control/public_conversion_kv_sync.py`.
It uses Wrangler's authenticated OAuth session, reads only the form event and
submission prefixes, checkpoints hashed KV keys after successful local
reconciliation, and leaves failed records uncheckpointed for retry. E.G.G.,
the watchdog, and the control panel treat stale, failed, or unreconciled sync
state as operational work.

Cloudflare KV is eventually consistent, so the edge rate counter and initial
dedupe marker are best-effort under a tightly concurrent burst. The canonical
M4 intake adapter remains authoritative: it uses process/file locking and a
content dedupe index so concurrent or repeated KV records create one qualified
opportunity. A future abuse-hardening phase may add Turnstile or a transactional
edge store if form traffic justifies it.

## M4 reconciliation path

For local testing or KV-export reconciliation, submit the same JSON payload shape to:

```bash
python3 ops/agent-control/public_conversion_intake.py submit --payload-json /path/to/payload.json --refresh-reports
```

To run the authenticated production synchronization:

```bash
python3 ops/agent-control/public_conversion_kv_sync.py --max-records 100
```

The five-minute M4 service is installed with:

```bash
ops/agent-control/install_public_conversion_kv_sync_launch_agent.sh
```

For a local HTTP adapter:

```bash
python3 ops/agent-control/public_conversion_intake.py serve --host 127.0.0.1 --port 8094
```

Then POST JSON to `http://127.0.0.1:8094/api/workflow-intake`.

## Guardrails

- No email is sent.
- No outbound packet is approved or staged.
- No public posting, spend, account change, financial action, or external commitment occurs.
- The form and endpoint reject file uploads, sensitive details, placeholder/test emails, JVT internal addresses, malformed addresses, and duplicate submissions from conversion metrics.
