from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

from app.core.paths import (
    BACKEND_ROOT,
    resolve_answer_model_cache_root,
    resolve_embedding_cache_root,
    resolve_jvt_demo_sample_root,
    resolve_storage_root,
    resolve_vector_data_root,
)
from app.core.settings import settings
from app.models.schemas import (
    ChunkPreview,
    CitationHint,
    DemoResetResponse,
    DemoSamplePackResponse,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentReindexResponse,
    DocumentSummary,
    GeneratedAnswer,
    HealthResponse,
    IndexedDocument,
    QuestionResponse,
    RetrievalResponse,
    RetrievedChunk,
    SourceDocumentMetadata,
    UploadResponse,
)
from app.services.chunking import chunk_document
from app.services.extraction import DocumentParseError, DocumentExtractor, SUPPORTED_TYPES
from app.services.providers.answer_providers import ProviderUnavailableError, build_answer_provider
from app.services.providers.embedding_providers import build_embedding_provider
from app.services.repository import DocumentRepository
from app.services.retrieval import RetrievalService
from app.services.types import GeneratedAnswerResult, StoredDocument


class DocumentStore:
    def __init__(self) -> None:
        self.storage_root = resolve_storage_root()
        self.vector_data_root = resolve_vector_data_root()
        self.uploads_dir = self.storage_root / settings.uploads_dir_name
        self.database_path = self.vector_data_root / settings.database_filename
        self.extractor = DocumentExtractor()
        self.repository = DocumentRepository(self.database_path)
        self.embedding_provider = build_embedding_provider(settings.embedding_provider)
        self.retrieval_service = RetrievalService(self.repository, self.embedding_provider)
        self._ensure_storage()

    def health_snapshot(self) -> HealthResponse:
        document_count, chunk_count = self.repository.counts()
        active_answer_provider = build_answer_provider(settings.answer_provider).name
        return HealthResponse(
            status="ok",
            documents_indexed=document_count,
            chunks_indexed=chunk_count,
            supported_types=sorted(SUPPORTED_TYPES),
            storage_root=str(self.storage_root),
            vector_data_root=str(self.vector_data_root),
            retrieval_backend=self.retrieval_service.backend_name,
            configured_answer_provider=settings.answer_provider,
            active_answer_provider=active_answer_provider,
            available_answer_providers=["extractive", "openai-compatible", "mlx-local"],
            embedding_provider=self.embedding_provider.name,
            embedding_cache_root=str(resolve_embedding_cache_root()),
            answer_model_cache_root=str(resolve_answer_model_cache_root()),
            local_answer_model_name=settings.local_answer_model_name,
            local_model_runtime=settings.local_model_runtime,
            demo_ui_path="/demo",
        )

    def store_document(self, filename: str, content_type: Optional[str], contents: bytes) -> UploadResponse:
        safe_name = Path(filename).name
        extension = Path(safe_name).suffix.lower()
        if extension not in SUPPORTED_TYPES:
            raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are accepted.")
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        document_id = uuid4().hex[:12]
        created_at = datetime.now(timezone.utc).isoformat()
        stored_name = f"{document_id}{extension}"
        stored_path = self.uploads_dir / stored_name
        stored_path.write_bytes(contents)

        stored_document, chunks, segment_count = self._index_document(
            document_id=document_id,
            filename=safe_name,
            content_type=content_type or SUPPORTED_TYPES[extension],
            contents=contents,
            stored_path=stored_path,
            created_at=created_at,
        )
        self.repository.store_document(stored_document, chunks)
        return self._build_upload_response(stored_document, chunks, segment_count)

    def list_documents(self) -> DocumentListResponse:
        stored_documents = self.repository.list_documents()
        documents = [self._to_indexed_document(document) for document in stored_documents]
        return DocumentListResponse(
            status="ok",
            documents_count=len(documents),
            documents=documents,
        )

    def get_document(self, document_id: str) -> DocumentDetailResponse:
        stored_document = self.repository.get_document(document_id)
        if stored_document is None:
            raise HTTPException(status_code=404, detail="Document was not found.")

        chunk_preview = self.repository.list_document_chunks(document_id=document_id, limit=5)
        return DocumentDetailResponse(
            status="ok",
            document=self._to_indexed_document(stored_document),
            chunk_preview=[self._to_chunk_preview(chunk) for chunk in chunk_preview],
        )

    def delete_document(self, document_id: str) -> DocumentDeleteResponse:
        stored_document = self.repository.delete_document(document_id)
        if stored_document is None:
            raise HTTPException(status_code=404, detail="Document was not found.")

        stored_path = Path(stored_document.stored_path)
        deleted_file = False
        if stored_path.exists():
            stored_path.unlink()
            deleted_file = True

        return DocumentDeleteResponse(
            status="ok",
            document_id=stored_document.document_id,
            filename=stored_document.filename,
            deleted_file=deleted_file,
            note="Document metadata, chunks, and stored file were removed from local demo storage."
            if deleted_file
            else "Document metadata and chunks were removed. Stored file was already absent.",
        )

    def reindex_document(self, document_id: str) -> DocumentReindexResponse:
        stored_document = self.repository.get_document(document_id)
        if stored_document is None:
            raise HTTPException(status_code=404, detail="Document was not found.")

        stored_path = Path(stored_document.stored_path)
        if not stored_path.exists():
            raise HTTPException(status_code=409, detail="Stored source file is missing and cannot be reindexed.")

        contents = stored_path.read_bytes()
        refreshed_document, chunks, segment_count = self._index_document(
            document_id=stored_document.document_id,
            filename=stored_document.filename,
            content_type=stored_document.content_type,
            contents=contents,
            stored_path=stored_path,
            created_at=stored_document.created_at,
            existing_metadata=stored_document.metadata,
        )
        self.repository.replace_document(refreshed_document, chunks)
        return DocumentReindexResponse(
            status="ok",
            document=self._to_indexed_document(refreshed_document),
            chunk_preview=[self._to_chunk_preview(chunk) for chunk in chunks[:3]],
            note=(
                f"Document reindexed with {refreshed_document.parser} into "
                f"{self.retrieval_service.backend_name}."
            ),
        )

    def reset_demo_state(self) -> DemoResetResponse:
        backend_data_root = (BACKEND_ROOT / "data").resolve()
        candidate_paths = []
        for path in [self.storage_root, self.vector_data_root]:
            resolved_path = path.resolve()
            if not self._is_relative_to(resolved_path, backend_data_root):
                raise HTTPException(
                    status_code=409,
                    detail="Refusing to reset demo state outside the backend data directory.",
                )
            candidate_paths.append(resolved_path)

        for path in sorted({str(path): path for path in candidate_paths}.values(), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()

        self._refresh_runtime()
        return DemoResetResponse(
            status="ok",
            storage_root=str(self.storage_root),
            vector_data_root=str(self.vector_data_root),
            note="Demo storage was reset to a clean recording state.",
        )

    def load_demo_sample_pack(self) -> DemoSamplePackResponse:
        sample_root = resolve_jvt_demo_sample_root()
        if not sample_root.exists():
            raise HTTPException(status_code=500, detail="JVT sample document pack was not found.")

        manifest_path = sample_root / "recording-pack.txt"
        selected_names: list[str] = []
        if manifest_path.exists():
            selected_names = [
                line.strip()
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

        selected_paths: list[Path]
        if selected_names:
            selected_paths = []
            for name in selected_names:
                candidate = sample_root / name
                if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in SUPPORTED_TYPES:
                    selected_paths.append(candidate)
        else:
            selected_paths = [
                sample_path
                for sample_path in sorted(sample_root.iterdir())
                if sample_path.is_file() and sample_path.suffix.lower() in SUPPORTED_TYPES
            ]

        uploaded_documents: list[DocumentSummary] = []
        for sample_path in selected_paths:
            response = self.store_document(
                filename=sample_path.name,
                content_type=SUPPORTED_TYPES[sample_path.suffix.lower()],
                contents=sample_path.read_bytes(),
            )
            uploaded_documents.append(response.document)

        return DemoSamplePackResponse(
            status="ok",
            loaded_count=len(uploaded_documents),
            documents=uploaded_documents,
            note="Loaded the prepared JVT sample document pack into the current demo state.",
        )

    def search_documents(self, question: str, document_ids: Optional[list[str]], top_k: int) -> RetrievalResponse:
        documents_considered = self.repository.count_documents(document_ids)
        if documents_considered == 0:
            raise HTTPException(status_code=404, detail="No matching documents are available for questioning.")

        hits = self.retrieval_service.search(question=question, document_ids=document_ids, top_k=top_k)
        return RetrievalResponse(
            status="ok",
            question=question,
            retrieval_backend=self.retrieval_service.backend_name,
            embedding_provider=self.embedding_provider.name,
            documents_considered=documents_considered,
            results=[self._to_retrieved_chunk(hit) for hit in hits],
        )

    def answer_question(
        self,
        question: str,
        document_ids: Optional[list[str]],
        answer_provider_name: Optional[str] = None,
    ) -> QuestionResponse:
        documents_considered = self.repository.count_documents(document_ids)
        if documents_considered == 0:
            raise HTTPException(status_code=404, detail="No matching documents are available for questioning.")

        hits = self.retrieval_service.search(
            question=question,
            document_ids=document_ids,
            top_k=settings.retrieval_top_k,
        )

        provider_requested = (answer_provider_name or settings.answer_provider).strip() or "extractive"
        answer_provider, answer_provider_used = self._get_answer_provider(provider_requested)
        if hits:
            try:
                answer_result = answer_provider.generate(question=question, hits=hits)
            except ProviderUnavailableError as exc:
                fallback_provider = build_answer_provider("extractive")
                answer_result = fallback_provider.generate(question=question, hits=hits)
                answer_provider_used = fallback_provider.name
                fallback_note = f"Requested provider '{provider_requested}' was unavailable: {exc}"
                answer_result.note = (
                    f"{answer_result.note} {fallback_note}".strip()
                    if answer_result.note
                    else fallback_note
                )
        else:
            answer_result = GeneratedAnswerResult(
                mode="no-match",
                provider=answer_provider_used,
                text="No grounded passages were retrieved for that question yet.",
                confidence=0.0,
                note="No citations available because retrieval returned no matches.",
            )

        citation_hits = self._select_citation_hits(hits, answer_result.citations)
        source_documents = self._build_source_documents(citation_hits or hits)
        citations = [self._to_citation(hit) for hit in citation_hits]
        return QuestionResponse(
            status="ok" if hits else "no_matches",
            question=question,
            retrieval_backend=self.retrieval_service.backend_name,
            answer_provider_requested=provider_requested,
            answer_provider_used=answer_provider_used,
            documents_considered=documents_considered,
            matched_document_ids=sorted({hit.document_id for hit in hits}),
            retrieval_preview=[self._to_retrieved_chunk(hit) for hit in hits],
            answer=GeneratedAnswer(
                mode=answer_result.mode,
                provider=answer_result.provider,
                text=answer_result.text,
                confidence=answer_result.confidence,
                note=answer_result.note,
            ),
            citations=citations,
            source_documents=source_documents,
        )

    def _ensure_storage(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.vector_data_root.mkdir(parents=True, exist_ok=True)

    def _refresh_runtime(self) -> None:
        self.storage_root = resolve_storage_root()
        self.vector_data_root = resolve_vector_data_root()
        self.uploads_dir = self.storage_root / settings.uploads_dir_name
        self.database_path = self.vector_data_root / settings.database_filename
        self.repository = DocumentRepository(self.database_path)
        self.retrieval_service = RetrievalService(self.repository, self.embedding_provider)
        self._ensure_storage()

    def _is_relative_to(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _index_document(
        self,
        document_id: str,
        filename: str,
        content_type: str,
        contents: bytes,
        stored_path: Path,
        created_at: str,
        existing_metadata: Optional[dict[str, object]] = None,
    ) -> tuple[StoredDocument, list, int]:
        extension = Path(filename).suffix.lower()
        try:
            extracted_document = self.extractor.extract(filename=filename, contents=contents)
        except DocumentParseError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": str(exc),
                    "filename": filename,
                    "file_type": extension,
                },
            ) from exc

        chunks = chunk_document(
            document_id=document_id,
            filename=filename,
            extracted_document=extracted_document,
        )
        chunks = self.retrieval_service.index_chunks(chunks)

        merged_metadata = dict(existing_metadata or {})
        merged_metadata.update(extracted_document.metadata)
        merged_metadata["segment_count"] = len(extracted_document.segments)
        if existing_metadata is not None:
            merged_metadata["reindexed_at"] = datetime.now(timezone.utc).isoformat()

        stored_document = StoredDocument(
            document_id=document_id,
            filename=filename,
            content_type=content_type or SUPPORTED_TYPES[extension],
            parser=extracted_document.parser,
            byte_size=len(contents),
            created_at=created_at,
            text_preview=extracted_document.full_text[:200],
            stored_path=str(stored_path),
            metadata=merged_metadata,
            chunk_count=len(chunks),
        )
        return stored_document, chunks, len(extracted_document.segments)

    def _build_upload_response(self, stored_document: StoredDocument, chunks: list, segment_count: int) -> UploadResponse:
        return UploadResponse(
            document=DocumentSummary(
                document_id=stored_document.document_id,
                filename=stored_document.filename,
                content_type=stored_document.content_type,
                parser=stored_document.parser,
                byte_size=stored_document.byte_size,
                chunk_count=stored_document.chunk_count,
                segment_count=segment_count,
                created_at=stored_document.created_at,
                text_preview=stored_document.text_preview,
            ),
            chunk_preview=[self._to_chunk_preview(chunk) for chunk in chunks[:3]],
            note=f"Document parsed with {stored_document.parser} and indexed into {self.retrieval_service.backend_name}.",
        )

    def _get_answer_provider(self, configured_provider: str):
        provider = build_answer_provider(configured_provider)
        try:
            provider.ensure_available()
            return provider, provider.name
        except ProviderUnavailableError:
            fallback_provider = build_answer_provider("extractive")
            return fallback_provider, fallback_provider.name

    def _select_citation_hits(self, hits, citation_chunk_ids: list[str]):
        if not hits:
            return []

        hits_by_chunk_id = {hit.chunk_id: hit for hit in hits}
        selected_hits = []
        for chunk_id in citation_chunk_ids:
            hit = hits_by_chunk_id.get(chunk_id)
            if hit and hit not in selected_hits:
                selected_hits.append(hit)

        if selected_hits:
            return selected_hits
        return hits[:3]

    def _to_indexed_document(self, stored_document: StoredDocument) -> IndexedDocument:
        segment_count = stored_document.metadata.get("segment_count")
        if not isinstance(segment_count, int):
            segment_count = None
        return IndexedDocument(
            document_id=stored_document.document_id,
            filename=stored_document.filename,
            content_type=stored_document.content_type,
            parser=stored_document.parser,
            byte_size=stored_document.byte_size,
            chunk_count=stored_document.chunk_count,
            segment_count=segment_count,
            created_at=stored_document.created_at,
            text_preview=stored_document.text_preview,
            metadata=stored_document.metadata,
        )

    def _to_chunk_preview(self, chunk) -> ChunkPreview:
        return ChunkPreview(
            chunk_id=chunk.chunk_id,
            locator=chunk.locator,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            citation_label=chunk.citation_label,
            text=chunk.text,
        )

    def _to_retrieved_chunk(self, hit) -> RetrievedChunk:
        return RetrievedChunk(
            document_id=hit.document_id,
            filename=hit.filename,
            content_type=hit.content_type,
            parser=hit.parser,
            chunk_id=hit.chunk_id,
            locator=hit.locator,
            citation_label=hit.citation_label,
            start_offset=hit.start_offset,
            end_offset=hit.end_offset,
            score=hit.score,
            excerpt=hit.text[:240],
        )

    def _to_citation(self, hit) -> CitationHint:
        return CitationHint(
            document_id=hit.document_id,
            filename=hit.filename,
            chunk_id=hit.chunk_id,
            locator=hit.locator,
            citation_label=hit.citation_label,
        )

    def _build_source_documents(self, hits) -> list[SourceDocumentMetadata]:
        seen: set[str] = set()
        source_documents: list[SourceDocumentMetadata] = []
        for hit in hits:
            if hit.document_id in seen:
                continue
            seen.add(hit.document_id)
            source_documents.append(
                SourceDocumentMetadata(
                    document_id=hit.document_id,
                    filename=hit.filename,
                    content_type=hit.content_type,
                    parser=hit.parser,
                    created_at=hit.created_at,
                )
            )
        return source_documents


document_store = DocumentStore()
