from __future__ import annotations

import json
from typing import Optional, Any

import urllib.request
from pydantic import BaseModel, Field, create_model

from .registry import ToolSpec


SUPPORTED_JSON_TYPES = ("string", "integer", "number", "boolean")


class ParamSpec(BaseModel):
    name: str
    
    json_type: str  # "string" | "integer" | "number" | "boolean" | "array"
    enum: Optional[list[Any]] = None

    items_json_type: Optional[str] = None  # e.g. "string"
    items_enum: Optional[list[Any]] = None

    required: bool = False
    default: Optional[Any] = None
    description: str = ""
    llm_description: str = ""


def fetch_openapi(api_base_url: str, timeout_sec: int = 30) -> dict:
    url = api_base_url.rstrip("/") + "/openapi.json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.load(resp)


def _resolve_ref(openapi: dict, schema: dict) -> dict:
    ref = schema.get("$ref")
    if not ref:
        return schema
    # Only handle local refs like "#/components/schemas/XYZ"
    if not ref.startswith("#/"):
        return schema
    parts = ref.lstrip("#/").split("/")
    cur: Any = openapi
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return schema
    return cur if isinstance(cur, dict) else schema


def _json_type_from_openapi_schema(openapi: dict, schema: dict) -> str:
    schema = _resolve_ref(openapi, schema)

    t = schema.get("type")
    if t in SUPPORTED_JSON_TYPES:
        return t

    # Handle Optional / unions: anyOf / oneOf (pick first non-null scalar type)
    for key in ("anyOf", "oneOf"):
        variants = schema.get(key)
        if isinstance(variants, list):
            for v in variants:
                v = _resolve_ref(openapi, v if isinstance(v, dict) else {})
                vt = v.get("type")
                if vt in SUPPORTED_JSON_TYPES:
                    return vt

    # fallback (safe default)
    return "string"



def _python_type(json_type: str):
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }.get(json_type, str)


def resolve_query_params(openapi: dict, tool: ToolSpec) -> list[ParamSpec]:
    """
    Extract query parameters for a (method, endpoint) from OpenAPI spec.
    Only query params are supported for now.
    """
    path_item = openapi.get("paths", {}).get(tool.endpoint)
    if not path_item:
        raise KeyError(f"Endpoint not found in OpenAPI: {tool.endpoint}")

    op = path_item.get(tool.method.lower())
    if not op:
        raise KeyError(f"Method not found in OpenAPI for {tool.endpoint}: {tool.method}")

    params = []
    for p in op.get("parameters", []) or []:
        if p.get("in") != "query":
            continue
        schema = p.get("schema", {}) or {}
        json_type = _json_type_from_openapi_schema(openapi, schema)
        params.append(
            ParamSpec(
                name=p["name"].strip(),
                json_type=json_type,
                required=bool(p.get("required", False)),
                default=schema.get("default", None),
                description=p.get("description", "") or "",
                llm_description=p.get("schema", {}).get("x-llm-description", "") or "",
            )
        )
    return params


def build_ollama_tool_schema(tool: ToolSpec, params: list[ParamSpec]) -> dict:
    properties: dict = {}
    required: list[str] = []

    for p in params:
        prop: dict = {"description": (p.llm_description or p.description)}

        if p.json_type == "array":
            # Array type with item constraints
            item_type = p.items_json_type or "string"
            prop["type"] = "array"
            prop["items"] = {"type": item_type}
            if p.items_enum:
                prop["items"]["enum"] = p.items_enum
        else:
            prop["type"] = p.json_type
            if p.enum:
                prop["enum"] = p.enum

        if p.default is not None:
            prop["default"] = p.default

        properties[p.name] = prop

        if p.required:
            required.append(p.name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.title,
            "parameters": schema,
        },
    }


def build_pydantic_args_model(tool_name: str, params: list[ParamSpec]):
    """
    Build a Pydantic model class dynamically for tool call args validation.
    """
    fields = {}
    for p in params:
        py_t = _python_type(p.json_type)
        if p.required:
            fields[p.name] = (py_t, Field(..., description=p.description))
        else:
            default = p.default if p.default is not None else None
            fields[p.name] = (Optional[py_t], Field(default, description=p.description))

    return create_model(f"{tool_name}_Args", **fields)


def get_operation_doc(openapi: dict, endpoint: str, method: str = "get") -> dict:
    """
    Return {summary, description} for an OpenAPI operation.
    `endpoint` must match the path key, e.g. "/analytics/breakdown".
    """
    op = openapi["paths"][endpoint][method.lower()]
    out = {
        "summary": (op.get("summary") or ""),
        "description": (op.get("description") or ""),
    }
    for k, v in op.items():
        if isinstance(k, str) and k.startswith("x-"):
            out[k] = v

    return out
