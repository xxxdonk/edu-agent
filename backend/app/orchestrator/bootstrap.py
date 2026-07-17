from __future__ import annotations

import importlib
import importlib.util
from typing import TYPE_CHECKING

from .contracts import AgentRegistry

if TYPE_CHECKING:
    from app.llm import LLMClient


def load_optional_resource_agents(
    registry: AgentRegistry,
    llm_client: "LLMClient | None" = None,
    *,
    enable_llm: bool = False,
) -> None:
    """Agent 2 integration point: app.resources.registry.register_agents(registry)."""

    module_name = "app.resources.registry"
    if importlib.util.find_spec(module_name) is None:
        return
    module = importlib.import_module(module_name)
    register = getattr(module, "register_agents", None)
    if not callable(register):
        raise RuntimeError(f"{module_name} must expose register_agents(registry)")
    register(registry, llm_client, enable_llm=enable_llm)
