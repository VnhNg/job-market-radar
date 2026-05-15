from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from pathlib import Path

from src.api.analytics.filter_values import get_filter_values
from src.assistant.core.ollama_client import ollama_chat
from src.assistant.core.param_specs import fetch_openapi
from src.assistant.core.registry import load_assistant_config, load_tools_registry
from src.assistant.core.semantic_spec import fetch_semantic_spec
from src.assistant.core.tool_runtime import ToolRuntime
from src.assistant.modes.complete.graph.build.build_graph import build_graph
from src.assistant.modes.complete.graph.infra.checkpoints import CheckpointRuntime, make_checkpointer
from src.assistant.modes.complete.graph.infra.langsmith_runtime import LangSmithRuntime

def make_llm() -> Callable[..., dict]:
    cfg = load_assistant_config()
    model = cfg.ollama.model
    base_url = cfg.ollama.base_url
    timeout_sec = cfg.ollama.timeout_sec

    def llm(*, messages, tools=None, response_format=None, options=None, **kwargs):
        return ollama_chat(
            base_url=base_url,
            model=model,
            messages=messages,
            tools=tools,
            options=options,
            response_format=response_format,
            timeout_sec=timeout_sec,
        )

    return llm


@dataclass
class CompleteBootstrap:
    graph: object
    checkpoint_runtime: CheckpointRuntime
    langsmith_runtime: LangSmithRuntime
    tool_runtime: ToolRuntime


def build_complete_bootstrap(
    *,
    checkpoint_path: str | Path = ".local/app/langgraph/complete/checkpoints.sqlite",
    langsmith_project: str | None = None,
) -> CompleteBootstrap:
    cfg = load_assistant_config()
    base_url = str(cfg.api.base_url)
    registry = load_tools_registry()

    llm = make_llm()
    timeout = cfg.agent.request_timeout_sec
    semantic_spec = fetch_semantic_spec(base_url, timeout_sec=timeout)
    tool_runtime = ToolRuntime(base_url, registry.tools, timeout_sec=timeout)
    openapi = fetch_openapi(base_url, timeout_sec=timeout)

    checkpoint_runtime = make_checkpointer(kind="sqlite", path=checkpoint_path)
    langsmith_runtime = LangSmithRuntime.open(project_name=langsmith_project)

    graph = build_graph(
        llm=llm,
        tool_runtime=tool_runtime,
        semantic_spec=semantic_spec,
        openapi=openapi,
        tools=registry.tools,
        filter_values_fetcher=get_filter_values,
        max_repairs=cfg.agent.max_repairs,
        max_rows_to_llm=cfg.agent.max_rows_to_llm,
        max_chars_to_llm=cfg.agent.max_chars_to_llm,
        langsmith_runtime=langsmith_runtime,
        checkpointer=checkpoint_runtime.checkpointer,
    )

    return CompleteBootstrap(
        graph=graph,
        checkpoint_runtime=checkpoint_runtime,
        langsmith_runtime=langsmith_runtime,
        tool_runtime=tool_runtime,
    )