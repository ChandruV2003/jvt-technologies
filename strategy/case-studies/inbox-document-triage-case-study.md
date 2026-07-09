# Inbox and Document Triage Case Study

Updated: 2026-06-24

## Summary

JVT's own mailbox listener is the proof asset for a small "inbox and document triage" offer. It imports mail, classifies messages, closes obvious noise, and exposes review queues in the control panel.

This is a sanitized internal case study. It does not include private message bodies.

## Target Customer

Small law, accounting, insurance, property-management, and admin-heavy service teams with shared inboxes, attachments, and repeated intake questions.

## Pain

Teams lose time deciding whether an email is a real client/prospect request, system noise, marketing, personal mail, or something that can be closed. The pain gets worse when documents or deadlines are attached and nobody owns the first triage pass.

## JVT Internal Proof

- Imported inbox items: `1795`
- New inbox items currently needing review: `0`
- Reviewed inbox items: `5`
- Closed inbox items: `1790`
- Effective triage buckets across imported mail:
- Direct/business messages: `20`
- Promotional/noise: `1530`
- System/security/vendor messages: `97`
- Personal/defer: `143`
- Internal tests: `5`

## Offer

One shared-inbox pilot:

- Connect one mailbox or exported mailbox feed.
- Classify messages into direct, review, system, promotional, personal, and internal/test buckets.
- Extract sender, subject, snippet, likely action, and priority.
- Prepare draft replies only for human review.
- Surface counts and recent items in a lightweight dashboard.

## Pricing Hypothesis

`$1,500` setup for one inbox plus `$500/mo` support for monitoring, rules tuning, and reviewed reply drafts.

## Delivery Complexity

Medium. The hard parts are mailbox permissions, private attachments, false positives, and maintaining conservative rules so client/prospect messages do not get auto-closed.

## Risks

- Misclassifying a real client request as noise.
- Attachment privacy and retention expectations.
- Mailbox-provider authentication friction.
- Client expecting autonomous replies instead of reviewable drafts.

## Next Validation Step

Use the public synthetic sample in outreach to admin-heavy teams.

Public proof page: `site/inbox-document-triage-demo.html`
