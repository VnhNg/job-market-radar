import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
import urllib.request

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "configs" / "tools.yaml"


def load_registry(registry_path: Path = DEFAULT_REGISTRY_PATH) -> list[dict]:
    """
    Load configs/tools.yaml and return tools list.
    """
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    tools = data.get("tools", []) if isinstance(data, dict) else []
    return tools


def call_tool(api_base_url: str, tool: dict, params: Optional[dict] = None) -> dict:
    """
    Execute a tool by calling its HTTP endpoint.
    """
    endpoint = tool["endpoint"]
    url = api_base_url.rstrip("/") + endpoint
    if params:
        url += "?" + urlencode(params)

    with urllib.request.urlopen(url) as resp:
        return json.load(resp)


def _json_schema_type(t: str) -> str:
    if t == "int":
        return "integer"
    if t == "float":
        return "number"
    return "string"


def tools_for_ollama(tools: list[dict]) -> list[dict]:
    """
    Convert YAML tools into Ollama tool definitions for /api/chat tool calling.
    """
    out: list[dict] = []
    for tool in tools:
        params = tool.get("params", []) or []

        properties: dict = {}
        required: list[str] = []

        for p in params:
            name = p["name"]
            ptype = _json_schema_type(p.get("type", "str"))

            properties[name] = {
                "type": ptype,
                "description": p.get("help", ""),
            }

            if "default" in p and p["default"] != "":
                properties[name]["default"] = p["default"]

            if p.get("required", False):
                required.append(name)

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required

        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["id"],
                    "description": tool.get("title", tool["id"]),
                    "parameters": schema,
                },
            }
        )
    return out
