from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Optional, Sequence

from app.services.types import ChunkRecord, SearchHit, StoredChunkPreview, StoredDocument


class DocumentRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_available = False
        self.retrieval_backend = "sqlite-lexical"
        self._initialize()

    def counts(self) -> tuple[int, int]:
        with self._connect() as connection:
            document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return int(document_count), int(chunk_count)

    def count_documents(self, document_ids: Optional[Sequence[str]] = None) -> int:
        with self._connect() as connection:
            if not document_ids:
                return int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            placeholders = ",".join("?" for _ in document_ids)
            sql = f"SELECT COUNT(*) FROM documents WHERE document_id IN ({placeholders})"
            return int(connection.execute(sql, list(document_ids)).fetchone()[0])

    def list_documents(self) -> list[StoredDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    document_id, filename, content_type, parser, byte_size,
                    created_at, text_preview, stored_path, metadata_json, chunk_count
                FROM documents
                ORDER BY created_at DESC, filename ASC
                """
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def get_document(self, document_id: str) -> Optional[StoredDocument]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    document_id, filename, content_type, parser, byte_size,
                    created_at, text_preview, stored_path, metadata_json, chunk_count
                FROM documents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_document(row)

    def list_document_chunks(self, document_id: str, limit: int = 5) -> list[StoredChunkPreview]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    chunk_id, document_id, chunk_index, segment_id, locator,
                    start_offset, end_offset, text, citation_label, metadata_json
                FROM chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC
                LIMIT ?
                """,
                (document_id, limit),
            ).fetchall()
        return [self._row_to_chunk_preview(row) for row in rows]

    def store_document(self, document: StoredDocument, chunks: list[ChunkRecord]) -> None:
        with self._connect() as connection:
            self._insert_document(connection, document, chunks)

    def replace_document(self, document: StoredDocument, chunks: list[ChunkRecord]) -> None:
        with self._connect() as connection:
            self._delete_document_rows(connection, document.document_id)
            self._insert_document(connection, document, chunks)

    def delete_document(self, document_id: str) -> Optional[StoredDocument]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    document_id, filename, content_type, parser, byte_size,
                    created_at, text_preview, stored_path, metadata_json, chunk_count
                FROM documents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
            if row is None:
                return None
            stored_document = self._row_to_document(row)
            self._delete_document_rows(connection, document_id)
        return stored_document

    def search_chunks(self, query: str, document_ids: Optional[Sequence[str]], top_k: int) -> list[SearchHit]:
        if self.fts_available:
            hits = self._search_with_fts(query, document_ids, top_k)
            if hits:
                return hits
        return self._search_with_lexical_fallback(query, document_ids, top_k)

    def search_chunks_by_embedding(
        self,
        query_embedding: list[float],
        document_ids: Optional[Sequence[str]],
        top_k: int,
    ) -> list[SearchHit]:
        sql = """
            SELECT
                d.document_id,
                d.filename,
                d.content_type,
                d.parser,
                d.created_at,
                d.metadata_json AS document_metadata_json,
                c.chunk_id,
                c.chunk_index,
                c.locator,
                c.start_offset,
                c.end_offset,
                c.text,
                c.citation_label,
                c.metadata_json AS chunk_metadata_json,
                c.embedding_json
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE c.embedding_json IS NOT NULL
        """
        params: list[object] = []
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            sql += f" AND d.document_id IN ({placeholders})"
            params.extend(list(document_ids))

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        scored_rows: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            score = self._cosine_similarity(query_embedding, embedding)
            scored_rows.append((score, row))

        scored_rows.sort(key=lambda item: item[0], reverse=True)
        return [self._row_to_hit(row, score) for score, row in scored_rows[:top_k]]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    parser TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    text_preview TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    segment_id TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    citation_label TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    embedding_json TEXT,
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                )
                """
            )
            self._ensure_column(connection, "chunks", "embedding_json", "TEXT")
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        document_id UNINDEXED,
                        filename UNINDEXED,
                        locator UNINDEXED,
                        text,
                        tokenize='porter unicode61'
                    )
                    """
                )
                self.fts_available = True
                self.retrieval_backend = "sqlite-fts5"
            except sqlite3.OperationalError:
                self.fts_available = False
                self.retrieval_backend = "sqlite-lexical"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _insert_document(
        self,
        connection: sqlite3.Connection,
        document: StoredDocument,
        chunks: list[ChunkRecord],
    ) -> None:
        connection.execute(
            """
            INSERT INTO documents (
                document_id, filename, content_type, parser, byte_size,
                created_at, text_preview, stored_path, metadata_json, chunk_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.document_id,
                document.filename,
                document.content_type,
                document.parser,
                document.byte_size,
                document.created_at,
                document.text_preview,
                document.stored_path,
                json.dumps(document.metadata),
                document.chunk_count,
            ),
        )

        for chunk in chunks:
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, chunk_index, segment_id, locator,
                    start_offset, end_offset, text, citation_label, metadata_json, embedding_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.chunk_index,
                    chunk.segment_id,
                    chunk.locator,
                    chunk.start_offset,
                    chunk.end_offset,
                    chunk.text,
                    chunk.citation_label,
                    json.dumps(chunk.metadata),
                    json.dumps(chunk.embedding) if chunk.embedding is not None else None,
                ),
            )
            if self.fts_available:
                connection.execute(
                    """
                    INSERT INTO chunks_fts (chunk_id, document_id, filename, locator, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        document.filename,
                        chunk.locator,
                        chunk.text,
                    ),
                )

    def _delete_document_rows(self, connection: sqlite3.Connection, document_id: str) -> None:
        if self.fts_available:
            connection.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        connection.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))

    def _search_with_fts(
        self,
        query: str,
        document_ids: Optional[Sequence[str]],
        top_k: int,
    ) -> list[SearchHit]:
        match_query = self._build_match_query(query)
        if not match_query:
            return []

        sql = """
            SELECT
                d.document_id,
                d.filename,
                d.content_type,
                d.parser,
                d.created_at,
                d.metadata_json AS document_metadata_json,
                c.chunk_id,
                c.chunk_index,
                c.locator,
                c.start_offset,
                c.end_offset,
                c.text,
                c.citation_label,
                c.metadata_json AS chunk_metadata_json,
                bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            JOIN documents d ON d.document_id = c.document_id
            WHERE chunks_fts MATCH ?
        """
        params: list[object] = [match_query]
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            sql += f" AND d.document_id IN ({placeholders})"
            params.extend(list(document_ids))
        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_hit(row, self._rank_to_score(float(row["rank"]))) for row in rows]

    def _search_with_lexical_fallback(
        self,
        query: str,
        document_ids: Optional[Sequence[str]],
        top_k: int,
    ) -> list[SearchHit]:
        sql = """
            SELECT
                d.document_id,
                d.filename,
                d.content_type,
                d.parser,
                d.created_at,
                d.metadata_json AS document_metadata_json,
                c.chunk_id,
                c.chunk_index,
                c.locator,
                c.start_offset,
                c.end_offset,
                c.text,
                c.citation_label,
                c.metadata_json AS chunk_metadata_json
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
        """
        params: list[object] = []
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            sql += f" WHERE d.document_id IN ({placeholders})"
            params.extend(list(document_ids))
        sql += " ORDER BY d.created_at DESC, c.chunk_index ASC"

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        query_terms = self._tokenize(query)
        ranked_rows: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            chunk_terms = self._tokenize(row["text"])
            if not chunk_terms:
                continue
            overlap = len(query_terms.intersection(chunk_terms))
            if overlap == 0 and query_terms:
                continue
            score = float(overlap) / float(max(len(query_terms), 1))
            ranked_rows.append((score, row))

        ranked_rows.sort(key=lambda item: item[0], reverse=True)
        selected = ranked_rows[:top_k] if ranked_rows else [(0.0, row) for row in rows[:top_k]]
        return [self._row_to_hit(row, score) for score, row in selected]

    def _build_match_query(self, query: str) -> str:
        terms = self._tokenize(query)
        if not terms:
            return ""
        return " OR ".join(f'"{term}"' for term in sorted(terms))

    def _tokenize(self, text: str) -> set[str]:
        return {
            term
            for term in re.findall(r"[a-z0-9]+", text.lower())
            if len(term) > 1
        }

    def _rank_to_score(self, rank: float) -> float:
        return round(1.0 / (1.0 + abs(rank)), 6)

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot_product = sum(left_item * right_item for left_item, right_item in zip(left, right))
        left_norm = sum(value * value for value in left) ** 0.5
        right_norm = sum(value * value for value in right) ** 0.5
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return round(dot_product / (left_norm * right_norm), 6)

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def _row_to_hit(self, row: sqlite3.Row, score: float) -> SearchHit:
        return SearchHit(
            document_id=row["document_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            parser=row["parser"],
            created_at=row["created_at"],
            chunk_id=row["chunk_id"],
            chunk_index=row["chunk_index"],
            locator=row["locator"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            citation_label=row["citation_label"],
            text=row["text"],
            score=round(score, 6),
            document_metadata=json.loads(row["document_metadata_json"]),
            chunk_metadata=json.loads(row["chunk_metadata_json"]),
        )

    def _row_to_document(self, row: sqlite3.Row) -> StoredDocument:
        return StoredDocument(
            document_id=row["document_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            parser=row["parser"],
            byte_size=row["byte_size"],
            created_at=row["created_at"],
            text_preview=row["text_preview"],
            stored_path=row["stored_path"],
            metadata=json.loads(row["metadata_json"]),
            chunk_count=row["chunk_count"],
        )

    def _row_to_chunk_preview(self, row: sqlite3.Row) -> StoredChunkPreview:
        return StoredChunkPreview(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            segment_id=row["segment_id"],
            locator=row["locator"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            text=row["text"],
            citation_label=row["citation_label"],
            metadata=json.loads(row["metadata_json"]),
        )
