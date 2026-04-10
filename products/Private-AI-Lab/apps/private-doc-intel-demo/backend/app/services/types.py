from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedSegment:
    segment_id: str
    locator: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    parser: str
    full_text: str
    segments: list[ExtractedSegment]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    chunk_index: int
    segment_id: str
    locator: str
    start_offset: int
    end_offset: int
    text: str
    citation_label: str
    metadata: dict[str, object] = field(default_factory=dict)
    embedding: Optional[list[float]] = None


@dataclass
class StoredDocument:
    document_id: str
    filename: str
    content_type: str
    parser: str
    byte_size: int
    created_at: str
    text_preview: str
    stored_path: str
    metadata: dict[str, object] = field(default_factory=dict)
    chunk_count: int = 0


@dataclass
class StoredChunkPreview:
    chunk_id: str
    document_id: str
    chunk_index: int
    segment_id: str
    locator: str
    start_offset: int
    end_offset: int
    text: str
    citation_label: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class SearchHit:
    document_id: str
    filename: str
    content_type: str
    parser: str
    created_at: str
    chunk_id: str
    chunk_index: int
    locator: str
    start_offset: int
    end_offset: int
    citation_label: str
    text: str
    score: float
    document_metadata: dict[str, object] = field(default_factory=dict)
    chunk_metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class GeneratedAnswerResult:
    mode: str
    provider: str
    text: str
    citations: list[str] = field(default_factory=list)
    confidence: Optional[float] = None
    note: Optional[str] = None
