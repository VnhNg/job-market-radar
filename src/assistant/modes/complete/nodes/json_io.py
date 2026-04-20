from __future__ import annotations

import json
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ValidationError


def extract_text(resp: dict) -> str:
    """
    Extract assistant text from an Ollama-like response dict.
    Keep permissive; supports common response shapes.
    """
    if not isinstance(resp, dict):
        return ""
    msg = resp.get("message")
    if isinstance(msg, dict):
        return msg.get("content") or ""
    return resp.get("response") or ""


def parse_json_object(text: str) -> dict:
    """
    Parse a JSON object from model output. Allows extra whitespace.
    Fail if no JSON object is found.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model output")

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    i = text.find("{")
    j = text.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("no JSON object found")

    obj = json.loads(text[i : j + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON was not an object")
    return obj


def call_llm_json(
    llm: Callable[..., dict],
    *,
    messages: list[dict],
    output_model: Type[BaseModel],
    default: BaseModel,
    options: dict[str, Any] | None = None,
    response_format: Any | None = "json",
) -> BaseModel:
    resp = llm(
        messages=messages,
        tools=None,
        options=options or {"temperature": 0},
        response_format=response_format,
    )
    raw = extract_text(resp)
    try:
        obj = parse_json_object(raw)
        return output_model.model_validate(obj)
    except (ValueError, ValidationError):
        return default