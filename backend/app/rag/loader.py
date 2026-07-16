from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: str
    source_id: str
    title: str
    locator: str
    content: str
    topic_tags: list[str] = field(default_factory=list)


def load_knowledge_base(data_dir: Path) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []

    syllabus_path = data_dir / "syllabus.md"
    if syllabus_path.exists() and syllabus_path.stat().st_size > 0:
        text = syllabus_path.read_text(encoding="utf-8")
        chunks.extend(_chunk_syllabus(text, syllabus_path))

    sources_path = data_dir / "sources.json"
    if sources_path.exists() and sources_path.stat().st_size > 0:
        chunks.extend(_load_sources(sources_path))

    return chunks


def _extract_topics(text: str) -> list[str]:
    topics: list[str] = []
    for heading in re.findall(r"^#{1,4}\s+(.+)$", text, flags=re.MULTILINE):
        cleaned = re.sub(r"[\*\#\_`]", "", heading).strip()
        if cleaned and len(cleaned) >= 2:
            topics.append(cleaned)
    return topics


def _chunk_syllabus(text: str, path: Path) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    source_id = "ml-syllabus"
    title = "机器学习基础课程大纲"

    sections = re.split(r"\n(?=#{1,4}\s)", text)
    for idx, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", section.split("\n")[0])
        section_title = heading_match.group(2).strip() if heading_match else f"章节{idx + 1}"
        chunk_id = f"chunk-{idx + 1:03d}"
        locator = f"data/machine_learning/syllabus.md#{section_title}"

        all_topics = _extract_topics(section)
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                source_id=source_id,
                title=title,
                locator=locator,
                content=section,
                topic_tags=all_topics,
            )
        )

    return chunks


def _load_sources(sources_path: Path) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("sources", [])
    for idx, entry in enumerate(entries):
        chunk_id = entry.get("chunk_id", f"src-chunk-{idx:03d}")
        content = entry.get("content", "")
        if not content:
            continue
        all_topics = entry.get("topics", []) + _extract_topics(content)
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                source_id=entry.get("source_id", f"source-{idx:03d}"),
                title=entry.get("title", "未知来源"),
                locator=entry.get("locator", str(sources_path)),
                content=content,
                topic_tags=list(dict.fromkeys(all_topics)),
            )
        )
    return chunks
