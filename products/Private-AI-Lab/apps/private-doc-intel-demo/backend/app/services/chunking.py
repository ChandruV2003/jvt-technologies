from __future__ import annotations

import hashlib

from app.core.settings import settings
from app.services.types import ChunkRecord, ExtractedDocument


def chunk_document(document_id: str, filename: str, extracted_document: ExtractedDocument) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    chunk_index = 1

    for segment in extracted_document.segments:
        text = segment.text.strip()
        if not text:
            continue

        start = 0
        while start < len(text):
            target_end = min(start + settings.chunk_size, len(text))
            end = target_end
            if target_end < len(text):
                snap = text.rfind(" ", start + max(40, settings.chunk_size // 2), target_end)
                if snap > start:
                    end = snap

            chunk_text = text[start:end].strip()
            if not chunk_text:
                break

            chunk_id = hashlib.sha1(
                f"{document_id}:{segment.segment_id}:{start}:{end}".encode("utf-8")
            ).hexdigest()[:16]
            citation_label = f"{filename} - {segment.locator} [{start}:{end}]"
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    segment_id=segment.segment_id,
                    locator=segment.locator,
                    start_offset=start,
                    end_offset=end,
                    text=chunk_text,
                    citation_label=citation_label,
                    metadata=dict(segment.metadata),
                )
            )
            chunk_index += 1

            if end >= len(text):
                break

            next_start = max(end - settings.chunk_overlap, start + 1)
            while next_start < len(text) and text[next_start].isspace():
                next_start += 1
            start = next_start

    return chunks
