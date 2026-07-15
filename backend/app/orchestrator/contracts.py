from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas import LearningPath, Resource, ResourceGenerationRequest, ResourceType, StudentProfile


@dataclass(frozen=True, slots=True)
class SharedAgentContext:
    task_id: str
    request: ResourceGenerationRequest
    profile: StudentProfile
    path: LearningPath


class ResourceAgent(Protocol):
    agent_name: str
    resource_type: ResourceType

    async def generate(self, context: SharedAgentContext) -> Resource:
        """Generate and validate one personalized, source-grounded resource."""


class ReviewerAgent(Protocol):
    agent_name: str

    async def review(
        self,
        resource: Resource,
        context: SharedAgentContext,
    ) -> Resource:
        """Return the reviewed resource with an updated review_status."""


class AgentRegistry:
    def __init__(self) -> None:
        self._resource_agents: dict[ResourceType, ResourceAgent] = {}
        self._reviewer: ReviewerAgent | None = None

    def register_resource(self, agent: ResourceAgent) -> None:
        if agent.resource_type in self._resource_agents:
            raise ValueError(f"duplicate resource agent: {agent.resource_type.value}")
        self._resource_agents[agent.resource_type] = agent

    def register_reviewer(self, agent: ReviewerAgent) -> None:
        if self._reviewer is not None:
            raise ValueError("reviewer agent already registered")
        self._reviewer = agent

    def resource_agent(self, resource_type: ResourceType) -> ResourceAgent | None:
        return self._resource_agents.get(resource_type)

    @property
    def reviewer(self) -> ReviewerAgent | None:
        return self._reviewer
