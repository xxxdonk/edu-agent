from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from app.schemas import SourceReference
from app.subjects import is_machine_learning_subject

from .loader import DocumentChunk, load_knowledge_base

logger = logging.getLogger(__name__)

_CJK_STOP_TERMS = {
    "一个",
    "一下",
    "什么",
    "内容",
    "可以",
    "完成",
    "希望",
    "怎么",
    "怎样",
    "目前",
    "相关",
    "知识",
    "课程",
}

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "machine_learning"


def knowledge_base_version(data_dir: Path | None = None) -> str:
    """Return a deterministic SHA-256 for every file consumed by the loader."""

    root = data_dir or DATA_DIR
    candidates = [
        path
        for path in root.iterdir()
        if path.is_file()
        and (
            path.name in {"syllabus.md", "sources.json"}
            or re.fullmatch(r"\d{2}-.+\.md", path.name)
        )
    ] if root.exists() else []
    digest = hashlib.sha256()
    for path in sorted(candidates, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class KnowledgeRetriever:
    def __init__(self, data_dir: Path | None = None) -> None:
        self._chunks: list[DocumentChunk] = []
        self._data_dir = data_dir or DATA_DIR
        self._loaded = False

    @property
    def knowledge_base_version(self) -> str:
        return knowledge_base_version(self._data_dir)

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
        subject_name: str | None = None,
        learning_goal: str | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        self._ensure_loaded()
        if not self._chunks:
            return []
        if subject_name and not is_machine_learning_subject(subject_name):
            return []

        query = " ".join(filter(None, [subject_name, topic, learning_goal]))
        query_terms = self._tokenize(query)
        scored: list[tuple[DocumentChunk, float]] = []
        for chunk in self._chunks:
            score = self._score(chunk, query_terms, query, difficulty)
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
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                tokens.append(token)
                for size in range(2, min(4, len(token)) + 1):
                    for start in range(len(token) - size + 1):
                        term = token[start : start + size]
                        if term not in _CJK_STOP_TERMS:
                            tokens.append(term)
            elif len(token) >= 2:
                tokens.append(token)
        return list(dict.fromkeys(tokens))

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

        normalized_topic = re.sub(r"\s+", "", topic.lower())
        normalized_chunk = re.sub(r"\s+", "", chunk_text)
        if normalized_topic and normalized_topic in normalized_chunk:
            score += 8.0

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
