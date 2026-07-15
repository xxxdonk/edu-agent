from __future__ import annotations

import importlib
import importlib.util

from .contracts import AgentRegistry


def load_optional_resource_agents(registry: AgentRegistry) -> None:
    """Agent 2 integration point: app.resources.registry.register_agents(registry)."""

    module_name = "app.resources.registry"
    if importlib.util.find_spec(module_name) is None:
        return
    module = importlib.import_module(module_name)
    register = getattr(module, "register_agents", None)
    if not callable(register):
        raise RuntimeError(f"{module_name} must expose register_agents(registry)")
    register(registry)
