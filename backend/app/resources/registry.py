from __future__ import annotations

import logging

from app.llm import LLMClient
from app.orchestrator import AgentRegistry
from app.rag import KnowledgeRetriever

from .coding_agent import CodingAgent
from .explanation_agent import ExplanationAgent
from .mindmap_agent import MindMapAgent
from .quiz_agent import QuizAgent
from .reading_agent import ReadingAgent
from .reviewer import ReviewerAgent

logger = logging.getLogger(__name__)

_RESOURCE_AGENTS = (
    ExplanationAgent,
    MindMapAgent,
    QuizAgent,
    ReadingAgent,
    CodingAgent,
)


def register_agents(
    registry: AgentRegistry,
    llm_client: LLMClient | None = None,
    *,
    enable_llm: bool = False,
) -> None:
    retriever = KnowledgeRetriever()

    for agent_cls in _RESOURCE_AGENTS:
        try:
            registry.register_resource(
                agent_cls(llm_client, retriever, enable_llm=enable_llm)
            )
        except ValueError as exc:
            logger.debug("resource_agent_skip reason=%s", exc)

    try:
        registry.register_reviewer(ReviewerAgent())
    except ValueError as exc:
        logger.debug("reviewer_skip reason=%s", exc)
