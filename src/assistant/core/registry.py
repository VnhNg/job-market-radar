from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl


PROJECT_ROOT = Path(__file__).resolve().parents[3]


# --------- tools registry ---------
class ToolSpec(BaseModel):
    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    method: Literal["GET"] = "GET"
    endpoint: str = Field(min_length=1)


class ToolsRegistry(BaseModel):
    tools: list[ToolSpec]


def load_tools_registry(path: Path | None = None) -> ToolsRegistry:
    path = path or (PROJECT_ROOT / "configs" / "tools.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ToolsRegistry.model_validate(data)


# --------- assistant config ---------
class OllamaConfig(BaseModel):
    base_url: HttpUrl = "http://127.0.0.1:11434"
    model: str = Field(min_length=1)


class ApiConfig(BaseModel):
    base_url: HttpUrl = "http://127.0.0.1:8000"


class AgentConfig(BaseModel):
    max_tool_calls: int = Field(default=3, ge=1, le=10)
    request_timeout_sec: int = Field(default=30, ge=5, le=120)
    max_rows_to_llm: int = Field(default=50, ge=1, le=500)
    max_chars_to_llm: int = Field(default=12000, ge=1000, le=100000)


class AssistantConfig(BaseModel):
    ollama: OllamaConfig
    api: ApiConfig
    agent: AgentConfig


def load_assistant_config(path: Path | None = None) -> AssistantConfig:
    path = path or (PROJECT_ROOT / "configs" / "assistant.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AssistantConfig.model_validate(data)
