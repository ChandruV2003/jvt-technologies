from fastapi import APIRouter, File, UploadFile

from app.models.schemas import (
    DemoResetResponse,
    DemoSamplePackResponse,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentReindexResponse,
    HealthResponse,
    QuestionRequest,
    QuestionResponse,
    RetrievalRequest,
    RetrievalResponse,
    UploadResponse,
)
from app.services.document_store import document_store

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return document_store.health_snapshot()


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    contents = await file.read()
    return document_store.store_document(
        filename=file.filename or "upload",
        content_type=file.content_type,
        contents=contents,
    )


@router.get("/documents", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    return document_store.list_documents()


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: str) -> DocumentDetailResponse:
    return document_store.get_document(document_id)


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(document_id: str) -> DocumentDeleteResponse:
    return document_store.delete_document(document_id)


@router.post("/documents/{document_id}/reindex", response_model=DocumentReindexResponse)
def reindex_document(document_id: str) -> DocumentReindexResponse:
    return document_store.reindex_document(document_id)


@router.post("/demo/reset", response_model=DemoResetResponse)
def reset_demo_state() -> DemoResetResponse:
    return document_store.reset_demo_state()


@router.post("/demo/sample-pack", response_model=DemoSamplePackResponse)
def load_demo_sample_pack() -> DemoSamplePackResponse:
    return document_store.load_demo_sample_pack()


@router.post("/retrieval/search", response_model=RetrievalResponse)
def search_documents(payload: RetrievalRequest) -> RetrievalResponse:
    return document_store.search_documents(
        question=payload.question,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )


@router.post("/questions", response_model=QuestionResponse)
def answer_question(payload: QuestionRequest) -> QuestionResponse:
    return document_store.answer_question(
        question=payload.question,
        document_ids=payload.document_ids,
        answer_provider_name=payload.answer_provider,
    )
