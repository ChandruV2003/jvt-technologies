# Private Document Intelligence Demo

This project is now a locally runnable, operator-usable demo for the `JVT Technologies` private document assistant on `m4-mac-mini`.

## What It Can Do Now

- ingest `PDF`, `DOCX`, and `TXT` documents
- extract text with real parsers
- chunk and index documents locally
- retrieve grounded chunks through local embeddings
- answer questions in three modes:
  - `extractive` fallback
  - `openai-compatible`
  - `mlx-local`
- return cited answers with source document metadata
- manage indexed documents:
  - list
  - inspect
  - delete
  - reindex
- serve a minimal operator UI from the backend at `/demo`

## Current Demo Shape

- backend: FastAPI
- retrieval: local embeddings via `fastembed`
- local answer runtime: `mlx-lm`
- first local answer model: `mlx-community/Qwen2.5-1.5B-Instruct-4bit`
- storage: local files plus SQLite
- operator UI: backend-served static page, no Node toolchain required

## Business Context

This is the first outward-facing `JVT Technologies` offer:

- private document search
- cited answers
- local-first or controlled deployment positioning
- configurable provider path
- secure internal-use story for document-heavy businesses

## Local Boundaries

- keep client documents, local indexes, and generated demo state out of Git
- keep model files and caches out of the repo
- keep secrets in local `.env` files only
- treat `backend/data` as local runtime state only
- treat `MODEL_ARTIFACT_ROOT` as the home for model and cache artifacts
- treat `VECTOR_DATA_ROOT` as the place to move durable index state later if needed

## Run The Full Demo Locally

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- API docs and health: `http://127.0.0.1:8000/health`
- operator demo UI: `http://127.0.0.1:8000/demo`

## Answer Modes

### 1. Extractive fallback

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
ANSWER_PROVIDER=extractive uvicorn app.main:app --reload
```

### 2. OpenAI-compatible provider

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
ANSWER_PROVIDER=openai-compatible \
ANSWER_MODEL_NAME=your-model-name \
ANSWER_API_BASE_URL=http://127.0.0.1:11435/v1 \
ANSWER_API_KEY= \
uvicorn app.main:app --reload
```

For local plumbing tests without secrets:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
python tools/mock_openai_compatible_server.py
```

### 3. Real local MLX mode

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend
source .venv/bin/activate
ANSWER_PROVIDER=mlx-local uvicorn app.main:app --reload
```

The first `mlx-local` answer call downloads the selected instruct model into the configured answer-model cache root.

## Operator UI Flow

The backend-served UI at `/demo` can:

- upload a document
- show indexed documents
- inspect chunk previews
- select documents to scope a question
- choose answer mode per question
- show cited answers and source snippets
- reindex a document
- delete a document from local demo storage

## API Surface

- `GET /health`
- `GET /documents`
- `GET /documents/{document_id}`
- `POST /documents/upload`
- `POST /documents/{document_id}/reindex`
- `DELETE /documents/{document_id}`
- `POST /retrieval/search`
- `POST /questions`
- `GET /demo`

## Local Smoke Test

```bash
curl http://127.0.0.1:8000/health

curl -X POST \
  -F 'file=@/absolute/path/to/sample.pdf;type=application/pdf' \
  http://127.0.0.1:8000/documents/upload

curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"question":"What do the documents say about confidentiality and billing?","answer_provider":"extractive"}' \
  http://127.0.0.1:8000/questions

curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"question":"What do the documents say about confidentiality and billing?","answer_provider":"mlx-local"}' \
  http://127.0.0.1:8000/questions
```

## Storage Strategy

Current local storage:

- uploads and local runtime data: `STORAGE_ROOT`
- SQLite / vector-style index state: `VECTOR_DATA_ROOT` if set, otherwise `STORAGE_ROOT`
- embedding cache: `EMBEDDING_CACHE_ROOT` if set, otherwise `MODEL_ARTIFACT_ROOT/embeddings`
- local answer model cache: `ANSWER_MODEL_CACHE_ROOT` if set, otherwise `MODEL_ARTIFACT_ROOT/answers`

Future Debian offload targets:

- `VECTOR_DATA_ROOT`
- `EMBEDDING_CACHE_ROOT`
- `ANSWER_MODEL_CACHE_ROOT`
- large durable artifacts under `MODEL_ARTIFACT_ROOT`

The app code does not assume Debian is the inference host. The current intent is:

- `m4-mac-mini` = live inference and serving
- `macmini-i7-debian` = long-term storage, mirrors, artifacts, and optional offloaded vector/model state

## Why This First Local Model

Chosen local model:

- `mlx-community/Qwen2.5-1.5B-Instruct-4bit`

Why:

- small enough for a first practical local demo on this Mac
- better instruction following than the tiniest toy models
- reasonable fit for citation-shaped JSON output and grounded summaries
- works directly with `mlx-lm` on Apple silicon without adding a separate local model server

## Next Build Step

1. add reranking on top of embedding retrieval
2. improve citation rendering with richer page and paragraph context
3. add document collections or client/matter scoping
4. only then consider a richer frontend shell
