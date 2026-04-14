# Local Model Recommendation

## Installed Now

- `mlx-community/Qwen2.5-1.5B-Instruct-4bit`
- `mlx-community/Qwen2.5-3B-Instruct-4bit`
- `mlx-community/Qwen2.5-7B-Instruct-4bit`

## Recommended Default

For this `16 GB` M4 Mac mini, the cleanest always-on default is:

- `mlx-community/Qwen2.5-3B-Instruct-4bit`

Why:

- it stays on the same `mlx-lm` runtime path you are already using
- it is light enough for background drafting and mailbox-assistant work
- it gives you a real step up from the smallest demo model without making latency the first problem
- current MLX package footprint is about `1.74 GB`

## Recommended Working Split

- document embeddings: keep `BAAI/bge-small-en-v1.5` for now
- demo answer generation: keep the current `mlx-local` path working
- mailbox/agent drafting: move to a `4B` class MLX instruct model first

## Recommended Stronger Review Model

When you want stronger drafting quality and better customer-facing answers:

- `mlx-community/Qwen2.5-7B-Instruct-4bit`

Current MLX package footprint is about `4.28 GB`.

## Working Split On This Mac

- `1.5B` stays available for the lightest product experimentation
- `3B` stays the fast default for always-on mailbox drafting
- `7B` should be the stronger reviewed-reply and higher-quality local-answer path

## Later Option

Only after the operational flow is stable and you want a stronger local assistant:

- `mlx-community/Qwen2.5-14B-Instruct-4bit`

That is more of a “later” option for this machine, not the first always-on default.
Its current MLX package footprint is about `8.31 GB`.

## Runtime Recommendation

- keep using `mlx-lm` as the direct local path on this Mac
- if you later want a single local OpenAI-compatible endpoint for multiple tools, add that deliberately after the mailbox and outreach workflow is stable

## Recommended Near-Term Move

1. keep the current demo running on the existing local model path
2. add `Qwen2.5-3B-Instruct-4bit` for the always-on mailbox and drafting agent
3. evaluate `Qwen2.5-7B-Instruct-4bit` for the main interactive answer path
4. only move up to `Qwen2.5-14B-Instruct-4bit` if the quality bump is worth the extra latency and memory pressure
