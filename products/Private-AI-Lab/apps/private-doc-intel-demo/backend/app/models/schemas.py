from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChunkPreview(BaseModel):
    chunk_id: str
    locator: str
    start_offset: int
    end_offset: int
    citation_label: str
    text: str


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    content_type: str
    parser: str
    byte_size: int
    chunk_count: int
    segment_count: int
    created_at: str
    text_preview: str


class UploadResponse(BaseModel):
    document: DocumentSummary
    chunk_preview: list[ChunkPreview]
    note: str


class HealthResponse(BaseModel):
    status: str
    documents_indexed: int
    chunks_indexed: int
    supported_types: list[str]
    storage_root: str
    vector_data_root: str
    retrieval_backend: str
    configured_answer_provider: str
    active_answer_provider: str
    available_answer_providers: list[str]
    embedding_provider: str
    embedding_cache_root: str
    answer_model_cache_root: str
    local_answer_model_name: str
    local_model_runtime: str
    demo_ui_path: str


class RetrievalRequest(BaseModel):
    question: str = Field(min_length=3)
    document_ids: Optional[list[str]] = None
    top_k: int = Field(default=5, ge=1, le=10)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3)
    document_ids: Optional[list[str]] = None
    answer_provider: Optional[str] = None


class RetrievedChunk(BaseModel):
    document_id: str
    filename: str
    content_type: str
    parser: str
    chunk_id: str
    locator: str
    citation_label: str
    start_offset: int
    end_offset: int
    score: float
    excerpt: str


class CitationHint(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    locator: str
    citation_label: str


class SourceDocumentMetadata(BaseModel):
    document_id: str
    filename: str
    content_type: str
    parser: str
    created_at: str


class GeneratedAnswer(BaseModel):
    mode: str
    provider: str
    text: str
    confidence: Optional[float] = None
    note: Optional[str] = None


class IndexedDocument(BaseModel):
    document_id: str
    filename: str
    content_type: str
    parser: str
    byte_size: int
    chunk_count: int
    segment_count: Optional[int] = None
    created_at: str
    text_preview: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    status: str
    question: str
    retrieval_backend: str
    embedding_provider: str
    documents_considered: int
    results: list[RetrievedChunk]


class QuestionResponse(BaseModel):
    status: str
    question: str
    retrieval_backend: str
    answer_provider_requested: str
    answer_provider_used: str
    documents_considered: int
    matched_document_ids: list[str]
    retrieval_preview: list[RetrievedChunk]
    answer: GeneratedAnswer
    citations: list[CitationHint]
    source_documents: list[SourceDocumentMetadata]


class DocumentListResponse(BaseModel):
    status: str
    documents_count: int
    documents: list[IndexedDocument]


class DocumentDetailResponse(BaseModel):
    status: str
    document: IndexedDocument
    chunk_preview: list[ChunkPreview]


class DocumentDeleteResponse(BaseModel):
    status: str
    document_id: str
    filename: str
    deleted_file: bool
    note: str


class DocumentReindexResponse(BaseModel):
    status: str
    document: IndexedDocument
    chunk_preview: list[ChunkPreview]
    note: str


class DemoResetResponse(BaseModel):
    status: str
    storage_root: str
    vector_data_root: str
    note: str


class DemoSamplePackResponse(BaseModel):
    status: str
    loaded_count: int
    documents: list[DocumentSummary]
    note: str
