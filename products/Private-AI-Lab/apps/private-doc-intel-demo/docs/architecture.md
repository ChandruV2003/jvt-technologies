# Architecture Sketch

- `backend/`: API, local model orchestration, and backend-served operator UI
- `frontend/`: dormant future standalone frontend scaffold, not required for the current demo
- `ingestion/`: parsers and chunking pipeline
- `vector_store/`: retrieval backend integration

Target answer flow:

1. user uploads a document set
2. ingestion extracts text and metadata
3. chunking creates retrieval units
4. embedding retrieval returns top grounded passages
5. answer layer runs in one of three modes:
   - extractive
   - openai-compatible
   - mlx-local
6. operator UI shows answer, citations, and source snippets
