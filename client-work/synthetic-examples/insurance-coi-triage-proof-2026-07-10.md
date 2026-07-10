# Synthetic Proof Asset: Insurance COI Request Triage

Generated: 2026-07-10T22:44:29+00:00

Status: synthetic internal proof. Do not present as a real client deployment.

## Scenario

A commercial client emails an agency asking for a certificate of insurance for a landlord and needs it today.

## Synthetic Incoming Email

From: `operations@example-contractor.test`

Subject: `Need COI for new job site today`

Body:

> Hi, can you send a certificate of insurance to the property manager for our new job at 100 Market Street? They need general liability and workers comp listed. Certificate holder is Market Street Holdings LLC, 100 Market Street, Newark, NJ 07102. Please send it to certificates@example-property.test and copy me. We need it today if possible.

## Extracted Fields For Staff Review

| Field | Extracted Value | Review Status |
| --- | --- | --- |
| Request type | Certificate of insurance | Needs licensed/staff review |
| Insured/client | Example Contractor | Needs account match |
| Certificate holder | Market Street Holdings LLC | Review |
| Holder address | 100 Market Street, Newark, NJ 07102 | Review |
| Coverage requested | General liability, workers compensation | Review policy availability |
| Delivery recipient | certificates@example-property.test | Review recipient |
| Client copy | operations@example-contractor.test | Review |
| Urgency | Today | Review feasibility |

## Missing-Information Checklist

- Confirm account/client identity.
- Confirm active policies and carrier rules.
- Confirm whether any special wording, additional insured, waiver, or endorsement is required.
- Confirm certificate holder spelling and address.
- Confirm approved delivery recipient.

## Staff Task Packet

Task title: `Review COI request for Example Contractor - Market Street Holdings`

Assigned role: licensed CSR / account manager

Priority: same-day

Recommended next action: review policy and certificate requirements before issuing anything.

## Draft Client Response For Human Review

> Thanks. We received the COI request for Market Street Holdings LLC. We are reviewing the account and certificate requirements now. If the property manager requires special wording, additional insured language, or waiver wording, please forward those instructions so our team can review them before issuing.

## Boundaries

- JVT does not issue COIs.
- JVT does not bind, alter, advise on, or confirm coverage.
- The workflow only extracts, routes, drafts, and logs material for staff review.
- Agency staff remain responsible for policy review and final communication.

## Sales Use

This proof asset supports a narrow paid pilot: one intake inbox, one request type, review-only packets, no AMS writeback until trust is proven.
