# JVT $10k Revenue Engine Implementation Map

Updated: 2026-06-12

## Objective

Create the clearest internal path to `$10,000` in gross cash collected by `2027-03-31` using productized JVT service work, not speculative revenue or approval-gated external actions.

## Operating Rules

- Stay service-led.
- Stop at internal proof, review packets, queue prep, and implementation planning.
- Do not send, post, buy, apply, fund, trade live, create wallets, mine, stake, or make outside commitments.

## Revenue Ladder

| Priority | Lane | First cash unit | Attach path | Current proof state | Main gap after this epic |
| --- | --- | --- | --- | --- | --- |
| 1 | Workflow cleanup | `$1,500` fixed scope | support retainer after the first workflow works | Workflow map existed; this epic adds a sellable proof packet and demo page | Review-only packet batch aimed at real candidate companies |
| 2 | AI receptionist / intake | `$750` setup + `$300-$500/mo` | usage expansion and more call paths | Strong demo page, proof PDF, offer copy, and prospect lane already exist | Review-only packet batch and live setup prerequisites checklist |
| 3 | Meeting-to-action packets | `$75` per packet or `$300/mo` | recurring packet volume and add-on document work | Strong demo page, proof PDF, and prospect lane already exist | Download-ready sample packet and second-angle packet batch |
| 4 | Inbox and document triage | `$1,500` setup + `$500/mo` | more inboxes, draft replies, attachment routing | Internal case study exists | Synthetic before/after sample and public-safe proof surface |
| 5 | Document packet generator | `$1,000` setup + `$500/mo` | template expansion and monthly packet work | Two synthetic packet examples already exist | Packaging and vertical framing comparable to stronger lanes |

## Base-Case Mix To Clear $10k

This mix is illustrative. It is meant to keep the target concrete and service-led.

| Unit mix | Cash contribution |
| --- | --- |
| 2 workflow cleanup projects at `$1,500` | `$3,000` |
| 2 AI receptionist pilots at `$750` setup + `$350` first month | `$2,200` |
| 2 meeting-to-action pilots at `$450` blended first unit | `$900` |
| 1 inbox triage pilot at `$2,000` blended setup + month one | `$2,000` |
| 1 document packet generator setup at `$1,500` | `$1,500` |
| 1 add-on support month or extra packet batch | `$500` |
| Total | `$10,100` |

## Current Priority Order

### 1. Workflow cleanup

Why now:

- lowest delivery dependency
- easiest fixed-scope price point to explain
- strongest path to cash without live phone or mailbox access

### 2. AI receptionist / intake

Why next:

- best existing proof stack
- clear paid-pilot shape
- needs internal packetization, not more abstract planning

### 3. Meeting-to-action packets

Why next:

- cheapest pilot
- easiest attach offer after a workflow cleanup or intake conversation
- reuses transcript and packet assets already built

### 4. Inbox and document triage

Why later in the sequence:

- attractive recurring support
- still behind the top lanes in public-safe proof packaging

### 5. Document packet generator

Why as an attach lane:

- useful once trust exists
- weaker as the first wedge than workflow cleanup or intake

## Execution Map

### Stage 1: Prove

- Keep one review-safe proof artifact per lane.
- Make the workflow obvious.
- Keep boundary language explicit.

### Stage 2: Package

- One narrow paid-pilot shape per lane.
- One proof link or packet.
- One pricing band.
- One review boundary.

### Stage 3: Queue

- Use the local task runner for repeat refreshes and summaries.
- Use the epic agent for multi-file packet batches, proof-gap closure, and lane packaging.

### Stage 4: Manual close path

- Manual review decides which lane gets outbound attention.
- Only after explicit approval should any packet move toward real send or public use.

This epic stops at Stage 3.

## Queue Split

### Queue next in local task runner

- `offer_segment_summary`
- `priority_packet_review_queue`
- `ten_k_execution_digest`

These are recurring refresh tasks. They are safe, internal, and already supported.

### Queue next in epic agent

- review-only paid-pilot packet batch for the strongest candidate lanes
- inbox triage proof packaging
- document packet generator packaging

These are larger multi-artifact stories that benefit from bounded Codex workspace-write execution.

## Success Checkpoints

- 3 lanes have proof plus pricing plus review boundary plus queue path.
- 1 next epic is already queued for review-only packet work.
- local task runner has refresh work staged for the new execution path.
- architect only needs to choose which lane gets manual review priority first.

## Repository References

- Plan anchor: `strategy/jvt-10k-by-mar-2027-plan.md`
- Child-story specs: `strategy/jvt-revenue-engine-child-stories-2026-06-12.md`
- Workflow cleanup proof packet: `client-work/synthetic-examples/workflow-cleanup-review-packet.md`
- Workflow cleanup demo surface: `site/workflow-cleanup-demo.html`
- Next queued epic: `ops/agent-control/epics/queued/2026-06-12-review-only-pilot-packet-batch.json`
