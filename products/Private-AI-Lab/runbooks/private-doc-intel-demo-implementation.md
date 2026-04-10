# Private Document Intelligence Demo Runbook

## Goal

Stand up a local-first demo that can ingest business documents, answer questions against them, and show citations for every response.

This runbook now supports the outward-facing `JVT Technologies` demo story as well as the product build itself.

## Current State

The current operator-demo milestone is implemented:

1. FastAPI boots locally
2. the backend serves a usable operator UI at `/demo`
3. uploads are accepted for PDF, DOCX, and TXT
4. PDF parsing uses `pypdf`, DOCX parsing uses `python-docx`, and TXT parsing stays direct
5. chunking stores stable chunk IDs, source locators, and offsets for citations
6. documents and chunks persist locally with document management endpoints
7. retrieval runs through local embeddings with lexical fallback still available underneath
8. question answering supports:
   - extractive fallback
   - OpenAI-compatible provider mode
   - real local `mlx-local` model mode

The operator demo is now also packaged as the first `JVT Technologies` business demo for law firms and similar document-heavy teams.

## Local Run

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open the operator demo at:

```bash
open http://127.0.0.1:8000/demo
```

## Answer Modes

### Extractive fallback mode

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
ANSWER_PROVIDER=extractive uvicorn app.main:app --reload
```

### OpenAI-compatible mode

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
ANSWER_PROVIDER=openai-compatible \
ANSWER_MODEL_NAME=your-model-name \
ANSWER_API_BASE_URL=http://127.0.0.1:11435/v1 \
ANSWER_API_KEY= \
uvicorn app.main:app --reload
```

For local provider-path smoke tests without secrets:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
python tools/mock_openai_compatible_server.py
```

### Real local MLX mode

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
ANSWER_PROVIDER=mlx-local uvicorn app.main:app --reload
```

## Local Test Commands

```bash
curl http://127.0.0.1:8000/health

curl -X POST \
  -F 'file=@/absolute/path/to/sample.pdf;type=application/pdf' \
  http://127.0.0.1:8000/documents/upload

curl http://127.0.0.1:8000/documents

curl http://127.0.0.1:8000/documents/<document_id>

curl -X POST http://127.0.0.1:8000/documents/<document_id>/reindex

curl -X DELETE http://127.0.0.1:8000/documents/<document_id>

curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"question":"What obligations are described?","top_k":3}' \
  http://127.0.0.1:8000/retrieval/search

curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"question":"What obligations are described?","answer_provider":"extractive"}' \
  http://127.0.0.1:8000/questions

curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"question":"What obligations are described?","answer_provider":"openai-compatible"}' \
  http://127.0.0.1:8000/questions

curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"question":"What obligations are described?","answer_provider":"mlx-local"}' \
  http://127.0.0.1:8000/questions
```

All three answer modes use the same `/questions` route. The request can optionally override the provider per question.

## Provider Layout

- extraction: `backend/app/services/extraction.py`
- chunking: `backend/app/services/chunking.py`
- storage and retrieval: `backend/app/services/repository.py` and `backend/app/services/retrieval.py`
- embedding providers: `backend/app/services/providers/embedding_providers.py`
- answer providers: `backend/app/services/providers/answer_providers.py`
- mock provider test harness: `backend/tools/mock_openai_compatible_server.py`
- backend-served operator UI: `backend/app/static/demo.html`, `demo.css`, `demo.js`

## Embedding Retrieval Notes

- default embedding provider: `fastembed-local`
- default embedding model: `BAAI/bge-small-en-v1.5`
- retrieved chunk similarity is cosine over locally stored embeddings
- lexical sqlite search remains as a fallback if embeddings are unavailable
- embedding cache lives under `EMBEDDING_CACHE_ROOT` if set, otherwise `MODEL_ARTIFACT_ROOT/embeddings`

## Local Model Notes

- keep model profile templates under `backend/config/model-profiles`
- keep large model artifacts outside the repo through `MODEL_ARTIFACT_ROOT`
- installed local runtime: `mlx-lm`
- current first local answer model: `mlx-community/Qwen2.5-1.5B-Instruct-4bit`
- current cache footprint on this Mac: about `839M`
- answer-model cache root lives under `ANSWER_MODEL_CACHE_ROOT` if set, otherwise `MODEL_ARTIFACT_ROOT/answers`
- this Mac remains the intended inference host
- Debian is the intended long-term storage target for:
  - model caches
  - embedding caches
  - vector/index data
  - durable artifacts
- do not treat Debian as the live inference host without explicit performance testing

## Next Milestone

1. add reranking for longer document sets
2. add richer citation context such as page and paragraph emphasis in the UI
3. add client/matter collections so documents are grouped for real demos
4. only after that consider expanding the UI beyond the current operator flow

## Guardrails

- keep secrets in local `.env` files only
- keep client documents and generated indexes out of Git
- treat `m4-mac-mini` as the stable control host, not the scratch dev box
