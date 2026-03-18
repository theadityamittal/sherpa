"""RAG pipeline: scrape -> S3 -> chunk -> embed -> store -> query.

Orchestrates the full ingestion and retrieval workflow.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rag.chunker import chunk_text
from rag.confidence import ConfidenceResult, calculate_confidence

if TYPE_CHECKING:
    from rag.storage import S3Storage
    from rag.vectorstore import PineconeVectorStore, SearchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryResult:
    """Immutable query result with search results and confidence."""

    query: str
    results: list[SearchResult]
    confidence: ConfidenceResult


class RAGPipeline:
    """Orchestrates document ingestion and RAG retrieval.

    Ingestion: text -> chunk -> Pinecone + raw HTML -> S3
    Query: query -> Pinecone search -> confidence scoring
    """

    def __init__(
        self,
        *,
        vectorstore: PineconeVectorStore,
        storage: S3Storage,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> None:
        self._vectorstore = vectorstore
        self._storage = storage
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def ingest_page(
        self,
        *,
        workspace_id: str,
        url: str,
        text: str,
        raw_html: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Ingest a single page: store raw HTML, chunk text, upsert to Pinecone.

        Args:
            workspace_id: Workspace namespace for isolation.
            url: Source URL of the page.
            text: Extracted clean text.
            raw_html: Raw HTML for archival in S3.
            metadata: Optional metadata (category, team, etc.).

        Returns:
            Number of chunks indexed.
        """
        # Store raw HTML in S3
        s3_key = self._storage.store_page(
            workspace_id=workspace_id, url=url, raw_html=raw_html
        )

        content_hash = hashlib.md5(raw_html.encode()).hexdigest()
        self._storage.update_manifest(
            workspace_id=workspace_id,
            url=url,
            s3_key=s3_key,
            content_hash=content_hash,
        )

        # Chunk text
        base_metadata = {"source_url": url, **(metadata or {})}
        chunks = chunk_text(
            text,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            metadata=base_metadata,
        )

        if not chunks:
            logger.warning("No chunks produced for %s", url)
            return 0

        # Upsert to Pinecone
        chunk_ids = [
            f"{workspace_id}_{hashlib.md5(url.encode()).hexdigest()[:8]}_{c.index}"
            for c in chunks
        ]

        self._vectorstore.upsert(
            texts=[c.text for c in chunks],
            ids=chunk_ids,
            namespace=workspace_id,
            metadata_list=[c.metadata for c in chunks],
        )

        logger.info("Ingested %d chunks from %s", len(chunks), url)
        return len(chunks)

    def query(
        self,
        *,
        query: str,
        workspace_id: str,
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Query the knowledge base and return results with confidence.

        Args:
            query: Natural language query.
            workspace_id: Workspace namespace to search.
            top_k: Maximum results to return.
            filter_metadata: Optional metadata filter.

        Returns:
            QueryResult with results and confidence score.
        """
        results = self._vectorstore.search(
            query=query,
            namespace=workspace_id,
            top_k=top_k,
            filter_metadata=filter_metadata,
        )

        keywords = _extract_keywords(query)
        confidence = calculate_confidence(
            similarity_scores=[r.score for r in results],
            query_keywords=keywords,
            result_texts=[r.text for r in results],
            max_expected_results=top_k,
        )

        return QueryResult(
            query=query,
            results=results,
            confidence=confidence,
        )


def _extract_keywords(query: str) -> set[str]:
    """Extract keywords from a query by removing stop words."""
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
        "between",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "what",
        "how",
        "where",
        "when",
        "who",
        "which",
        "that",
        "this",
        "it",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
    }
    words = re.findall(r"\w+", query.lower())
    return {w for w in words if w not in stop_words and len(w) > 2}
