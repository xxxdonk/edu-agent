from __future__ import annotations

import logging
import re
from pathlib import Path

from app.schemas import SourceReference

from .loader import DocumentChunk, load_knowledge_base

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "machine_learning"


class KnowledgeRetriever:
    def __init__(self, data_dir: Path | None = None) -> None:
        self._chunks: list[DocumentChunk] = []
        self._data_dir = data_dir or DATA_DIR
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._chunks = load_knowledge_base(self._data_dir)
        self._loaded = True
        if not self._chunks:
            logger.warning("no chunks loaded from %s", self._data_dir)

    def retrieve(
        self,
        topic: str,
        max_chunks: int = 5,
        difficulty: str | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        self._ensure_loaded()
        if not self._chunks:
            return []

        query_terms = self._tokenize(topic)
        scored: list[tuple[DocumentChunk, float]] = []
        for chunk in self._chunks:
            score = self._score(chunk, query_terms, topic, difficulty)
            if score > 0:
                scored.append((chunk, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:max_chunks]

    def to_source_references(
        self,
        chunks: list[tuple[DocumentChunk, float]],
    ) -> list[SourceReference]:
        return [
            SourceReference(
                source_id=chunk.source_id,
                title=chunk.title,
                locator=chunk.locator,
                chunk_id=chunk.chunk_id,
            )
            for chunk, _score in chunks
        ]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        text_lower = text.lower()
        for match in re.finditer(r"[\u4e00-\u9fff]+|[a-z0-9_-]+", text_lower):
            token = match.group()
            if len(token) >= 2:
                tokens.append(token)
        return tokens

    @staticmethod
    def _score(
        chunk: DocumentChunk,
        query_terms: list[str],
        topic: str,
        difficulty: str | None,
    ) -> float:
        score = 0.0

        topic_tokens = KnowledgeRetriever._tokenize(topic)
        chunk_text = chunk.content.lower()

        for term in topic_tokens:
            if term in chunk_text:
                score += 2.0

        for tag in chunk.topic_tags:
            tag_tokens = KnowledgeRetriever._tokenize(tag)
            for tt in tag_tokens:
                if any(tt in qt or qt in tt for qt in topic_tokens):
                    score += 3.0

        for term in query_terms:
            if term in chunk_text:
                score += 1.0

        heading_match = re.search(r"^#{1,3}\s+(.+)$", chunk.content, flags=re.MULTILINE)
        if heading_match:
            heading_text = heading_match.group(1).lower()
            for term in topic_tokens:
                if term in heading_text:
                    score += 2.5

        if difficulty and difficulty.lower() in chunk_text:
            score += 0.5

        length_factor = min(1.0, len(chunk.content) / 500)
        return score * length_factor
