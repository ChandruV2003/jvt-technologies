# Operator Flow

## Fast Demo Flow

1. open the local operator UI
2. upload the prepared sample documents
3. confirm the indexed document list populated
4. ask one high-signal question in `extractive` mode
5. ask the same or a follow-up question in `mlx-local` mode
6. optionally show `openai-compatible` mode if configured for the session
7. show citations and source snippets
8. end with deployment/privacy explanation

## Clean Sample Path

- start with:
  - `sample-engagement-terms.txt`
  - `sample-billing-policy.txt`
  - `sample-records-retention-policy.txt`
- first question:
  - “What does the billing policy say about disputed invoices?”
- second question:
  - “What confidentiality obligations survive termination?”
- optional third question:
  - “Which documents mention retention requirements?”

## Operator Notes

- start with the simplest answer mode first if you want a quick baseline
- use `mlx-local` when you want to show that the system can answer locally on this Mac
- keep the document set small for a short demo
- narrate why citations matter while the answer is on screen
- avoid speculative or advice-like prompts in a first prospect demo
