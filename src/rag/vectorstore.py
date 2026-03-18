"""Pinecone vectorstore client with namespace isolation and integrated inference.

Uses Pinecone's built-in Inference for embeddings (free 5M tokens/mo)
and integrated search with reranking (500 free/mo).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pinecone import Pinecone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    """Immutable search result from Pinecone."""

    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PineconeVectorStore:
    """Pinecone client using Starter-tier features.

    - Single index, multiple namespaces (one per workspace)
    - Built-in Inference embeddings via upsert_records
    - Integrated search (embeds query + searches)
    - Metadata filtering for team/role scoping
    """

    def __init__(self, *, api_key: str, index_name: str) -> None:
        self._pc = Pinecone(api_key=api_key)
        self._index = self._pc.Index(index_name)

    def upsert(
        self,
        *,
        texts: list[str],
        ids: list[str],
        namespace: str,
        metadata_list: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert text chunks into Pinecone with integrated embeddings.

        Pinecone Inference embeds the text automatically via upsert_records.
        """
        records = []
        for i, (text, doc_id) in enumerate(zip(texts, ids, strict=True)):
            record: dict[str, Any] = {
                "_id": doc_id,
                "chunk_text": text,
            }
            if metadata_list and i < len(metadata_list):
                record.update(metadata_list[i])
            records.append(record)

        self._index.upsert_records(namespace=namespace, records=records)
        logger.info("Upserted %d records to namespace %s", len(records), namespace)

    def search(
        self,
        *,
        query: str,
        namespace: str,
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search Pinecone using integrated inference (embeds query + searches).

        Args:
            query: Natural language search query.
            namespace: Workspace namespace to search within.
            top_k: Maximum number of results.
            filter_metadata: Optional metadata filter dict.

        Returns:
            List of SearchResult ordered by relevance score.
        """
        search_kwargs: dict[str, Any] = {
            "namespace": namespace,
            "query": {"top_k": top_k, "inputs": {"text": query}},
        }
        if filter_metadata:
            search_kwargs["filter"] = filter_metadata

        response = self._index.search(**search_kwargs)
        hits = response.get("result", {}).get("hits", [])

        return [
            SearchResult(
                id=hit["_id"],
                score=hit["_score"],
                text=hit.get("fields", {}).get("chunk_text", ""),
                metadata={
                    k: v for k, v in hit.get("fields", {}).items() if k != "chunk_text"
                },
            )
            for hit in hits
        ]

    def delete_namespace(self, *, namespace: str) -> None:
        """Delete all vectors in a namespace."""
        self._index.delete(delete_all=True, namespace=namespace)
        logger.info("Deleted namespace %s", namespace)
