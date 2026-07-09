# JVT Company Next Steps

This is the practical next-step list for JVT after the current site, demo, outreach, and control-panel foundation.

## Already In Place

- public website
- local demo product
- reviewed outbound workflow
- inbound mailbox path
- local model path on the Mac mini
- local control panel
- live Tailscale remote access for the control panel

## Immediate Human Blockers

### 1. Confirm legal entity and EIN readiness

Before business banking and payment processing can be fully real:

- exact entity name
- formation docs
- EIN

### 2. Confirm commercial send/receive readiness

The mailbox path is live, but it still needs one clean validation pass before widening volume:

- verify inbound polling stays healthy
- run one successful reviewed outbound send
- confirm reply handling stays local and review-driven

## Best Next Company Moves

### A. Commercial readiness

- confirm legal entity and EIN
- open Mercury
- open Stripe
- run one self-test invoice

### B. Core service reliability

- keep the control panel reachable over Tailscale
- keep the private-doc-intel backend installed as a local launchd service
- harden the mailbox listener around empty or unexpected IMAP responses

### C. Outreach scaling

- keep reviewed send batches small
- expand national lead research in curated tranches
- improve follow-up scheduling

### D. Control-panel evolution

- add background task controls
- add an operator inbox pane
- add daily status and exception views

## Recommended Order

1. entity and EIN confirmation
2. Mercury and Stripe setup
3. one clean inbound and outbound mailbox validation pass
4. next reviewed outreach tranche
5. follow-up scheduling and reply handling improvements
