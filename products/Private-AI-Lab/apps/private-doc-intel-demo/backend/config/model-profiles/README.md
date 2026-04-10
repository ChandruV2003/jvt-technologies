# Model Profiles

Keep lightweight provider configuration and local model profile templates here.

- store only small config files in this directory
- keep secrets out of these files
- keep large model weights and caches outside the repo through `MODEL_ARTIFACT_ROOT`
- use this directory for future runtime-specific profiles such as `mlx.local.json` or `api.local.json`
- the default embedding profile for this project is `fastembed-local` with `BAAI/bge-small-en-v1.5`
- the first local answer profile is `mlx-local` with `mlx-community/Qwen2.5-1.5B-Instruct-4bit`
- prefer these storage hooks over hardcoded paths:
  - `EMBEDDING_CACHE_ROOT`
  - `ANSWER_MODEL_CACHE_ROOT`
  - `VECTOR_DATA_ROOT`
- long term, those roots can point at Debian-backed storage without changing app logic
