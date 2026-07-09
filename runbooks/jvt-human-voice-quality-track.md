# JVT Human Voice Quality Track

Updated: 2026-06-25

## Goal

Create a JVT voice experience that sounds natural, calm, and close to Chandru's speaking style while staying honest that callers are interacting with JVT's AI assistant.

This is for inbound JVT demos, intake, and screen-share walkthrough support. It is not for impersonation, robocalling, deception, or outbound sales dialing.

## Non-Negotiable Rules

- Use only Chandru-approved voice samples.
- Do not clone or imitate anyone else's voice without explicit written consent.
- Keep AI disclosure in the call flow.
- Do not use the voice for outbound calls without separate approval and compliance review.
- Do not make legal, tax, medical, financial, pricing, payment, or delivery commitments by voice.
- Keep a human-review handoff for demos, proposals, and sensitive workflows.

## Quality Bar

The target is not just a clear TTS voice. The target is natural speech with:

- realistic pauses and hesitations,
- non-robotic sentence rhythm,
- Chandru-like phrasing without overdoing filler words,
- warm but direct tone,
- stable pronunciation of JVT, email addresses, URLs, names, and phone numbers,
- low latency for live demo flow,
- easy fallback to a simpler voice if the high-quality path fails.

## Workstream

1. Collect a clean consented voice sample pack.
   - 20 to 30 minutes of clean speech is enough for a first serious evaluation.
   - Record in a quiet room with the same mic when possible.
   - Include conversational examples, demo explanation, short email-style replies, spelling names/emails, and natural corrections.

2. Build a voice test corpus.
   - JVT intro.
   - "What does JVT do?"
   - AI receptionist explanation.
   - Inbox/document triage explanation.
   - Meeting-to-action explanation.
   - "Let me send you a written outline."
   - "I need Chandru to review that before I can commit."

3. Evaluate providers or local models without committing spend.
   - Score naturalness, latency, voice similarity, control over pauses, pronunciation, streaming support, cost, data controls, and API reliability.
   - Keep provider signups, paid usage, and production keys approval-gated.

4. Add a JVT voice style layer.
   - Short sentences.
   - One question at a time.
   - Natural confirmation phrases.
   - Explicit guardrails for pricing, contracts, legal/tax/financial advice, and confidential documents.

5. Wire into the inbound voice app only after demo-quality samples pass review.
   - Keep dry-run default.
   - Keep disclosure.
   - Record call transcript and intake packet.
   - Add human handoff language when uncertain.

## Sample Script Pack

Record these in your normal speaking voice:

1. "Hey, this is Chandru from JVT Technologies. The simplest way to explain what we do is this: we take repetitive office workflows and turn them into reviewed AI-assisted systems."
2. "For a law firm, I would not start with anything risky. I would start with intake, document triage, and follow-up drafts that a person reviews before anything goes out."
3. "If that sounds useful, I can either send a short written outline or walk through a quick demo."
4. "I do not want the AI making commitments. The point is to capture the right information, keep the workflow moving, and hand off anything sensitive to a real person."
5. "Let me slow down and say that differently."
6. "Could you spell the email address for me?"
7. "I can capture that, but Chandru would need to review it before we commit to scope or pricing."

## First Validation Step

Build a local voice evaluation folder with:

- `samples/` for approved raw recordings,
- `scripts/` for test lines,
- `renders/` for generated voice outputs,
- `scorecards/` for human scoring,
- `README.md` explaining consent, provider, model, date, and result.

No production voice goes live until at least three side-by-side samples are reviewed and accepted.
