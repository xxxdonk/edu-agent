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
    """Agent 2 integration point: app.resources.registry.register_agents(registry).

    Gracefully degrades when the app.resources package is unavailable, so
    that develop can start without Agent2 modules.
    """

    module_name = "app.resources.registry"
    try:
        if importlib.util.find_spec(module_name) is None:
            return
    except (ModuleNotFoundError, ImportError) as exc:
        logger = logging.getLogger(__name__)
        logger.info("resource_agents_skipped reason=%s", exc)
        return
    except Exception:
        logger = logging.getLogger(__name__)
        logger.warning("resource_agents_skip_unexpected", exc_info=True)
        return

    try:
        module = importlib.import_module(module_name)
    except (ModuleNotFoundError, ImportError) as exc:
        logger = logging.getLogger(__name__)
        logger.info("resource_agents_import_skipped reason=%s", exc)
        return

    register = getattr(module, "register_agents", None)
    if not callable(register):
        raise RuntimeError(f"{module_name} must expose register_agents(registry)")
    register(registry, llm_client, enable_llm=enable_llm)
