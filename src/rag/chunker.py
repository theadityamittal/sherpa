"""Document chunking with configurable size, overlap, and sentence-aware splitting."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Chunk:
    """An immutable text chunk with positional index and metadata."""

    text: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


# Sentence boundary pattern: period/question/exclamation followed by space or end
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_text(
    text: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks, preferring sentence boundaries.

    Args:
        text: The source text to chunk.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Number of characters to overlap between adjacent chunks.
        metadata: Optional metadata attached to every chunk.

    Returns:
        List of Chunk objects with sequential indices.

    Raises:
        ValueError: If chunk_overlap >= chunk_size.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
        )

    stripped = text.strip()
    if not stripped:
        return []

    base_metadata = metadata or {}
    chunks: list[Chunk] = []
    start = 0

    while start < len(stripped):
        end = min(start + chunk_size, len(stripped))
        segment = stripped[start:end]

        # If not the last chunk, try to split at a sentence boundary
        if end < len(stripped):
            # Search for the last sentence boundary within the segment
            last_boundary = _find_last_sentence_boundary(segment)
            if last_boundary is not None and last_boundary > chunk_overlap:
                segment = segment[:last_boundary]
                end = start + last_boundary

        chunks.append(
            Chunk(
                text=segment.strip(),
                index=len(chunks),
                metadata=dict(base_metadata),
            )
        )

        # If we reached the end of text, stop
        if start + len(segment) >= len(stripped):
            break

        # Advance by (segment length - overlap), but at least 1 char
        step = max(len(segment) - chunk_overlap, 1)
        start += step

    return chunks


def _find_last_sentence_boundary(text: str) -> int | None:
    """Find the position after the last sentence-ending punctuation in text."""
    last_pos = None
    for match in _SENTENCE_END.finditer(text):
        last_pos = match.start()
    return last_pos
