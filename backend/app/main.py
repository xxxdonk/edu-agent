from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import install_error_handlers, router
from app.config import Settings
from app.database import Repository, SQLiteDatabase
from app.llm import LLMConfigurationError, build_llm_client
from app.llm.errors import safe_error_summary
from app.orchestrator import (
    AgentRegistry,
    Orchestrator,
    ResourceCache,
    load_optional_resource_agents,
)
from app.planner import PlannerAgent
from app.profile import ProfileAgent
from app.rag.retriever import knowledge_base_version

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    logger.warning(
        "ENABLE_LLM=%s provider=%s model=%s api_key_present=%s",
        runtime_settings.llm.enabled,
        runtime_settings.llm.provider,
        runtime_settings.llm.model,
        bool(runtime_settings.llm.api_key.strip()),
    )
    database = SQLiteDatabase(runtime_settings.database_path)
    repository = Repository(database)
    registry = AgentRegistry()
    kb_version = knowledge_base_version()
    resource_cache = ResourceCache(
        enabled=runtime_settings.resource_cache_enabled,
        ttl_seconds=runtime_settings.resource_cache_ttl_seconds,
        max_entries=runtime_settings.resource_cache_max_entries,
    )
    model_identity = (
        f"{runtime_settings.llm.provider}:"
        f"{runtime_settings.llm.model or '<unconfigured>'}"
    )
    logger.debug(
        "resource_cache enabled=%s ttl_seconds=%s max_entries=%s "
        "knowledge_base_version=%s",
        resource_cache.enabled,
        resource_cache.ttl_seconds,
        resource_cache.max_entries,
        kb_version[:12],
    )
    llm_client = None
    if runtime_settings.llm.enabled:
        try:
            llm_client = build_llm_client(runtime_settings.llm)
        except LLMConfigurationError as error:
            logger.warning("llm_disabled error=%s", safe_error_summary(error))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        load_optional_resource_agents(
            registry,
            llm_client,
            enable_llm=runtime_settings.llm.enabled,
        )
        yield

    app = FastAPI(
        title="EduAgent API",
        version="0.1.0",
        description="动态学习画像驱动的多智能体个性化学习资源生成系统",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.database = database
    app.state.repository = repository
    app.state.resource_cache = resource_cache
    app.state.llm_client = llm_client
    app.state.profile_agent = ProfileAgent(
        llm_client,
        enable_llm=runtime_settings.llm.enabled,
    )
    app.state.planner_agent = PlannerAgent(
        llm_client,
        enable_llm=runtime_settings.llm.enabled,
    )
    app.state.agent_registry = registry
    app.state.orchestrator = Orchestrator(
        repository,
        registry,
        resource_cache=resource_cache,
        model_identity=model_identity,
        knowledge_base_version=kb_version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
