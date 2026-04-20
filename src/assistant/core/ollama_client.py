from __future__ import annotations

import json
from typing import Any, Optional
import urllib.request


def ollama_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    stream: bool = False,
    options: Optional[dict[str, Any]] = None,
    response_format: Optional[Any] = None,  # NEW: "json" or JSON schema dict
    timeout_sec: int = 30,
) -> dict:
    url = str(base_url).rstrip("/") + "/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
    if options:
        payload["options"] = options
    if response_format is not None:
        payload["format"] = response_format

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.load(resp)
