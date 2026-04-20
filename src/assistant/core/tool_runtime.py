from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode
import urllib.request

from pydantic import BaseModel

from .registry import ToolSpec
from .tool_policy import get_tool_policy
from .semantic_spec import BaseName, SemanticSpec
from .param_specs import (
    fetch_openapi,
    resolve_query_params,
    build_ollama_tool_schema,
    build_pydantic_args_model,
    ParamSpec,
)


@dataclass(frozen=True)
class ToolSurface:
    """
    Cached artifact for (tool_name, base).

    It separates:
    1) ArgsModel for runtime validation of executed API params
       - includes injected 'base' when required
       - keeps dimensions/select as CSV strings (API shape)
    2) planner_schema_partial for the LLM planner
       - excludes injected 'base'
       - uses arrays for dimensions/select
       - already includes low-card enums
       - high-card filters remain unconstrained for now
    """
    ArgsModel: type[BaseModel]
    planner_schema_partial: dict


class ToolRuntime:
    """
    Runtime layer:
    - Fetch OpenAPI once
    - Cache (ToolSpec, ParamSpec[]) per tool_name
    - Cache ToolSurface per (tool_name, base)
    - Execute HTTP GET calls
    """

    def __init__(self, api_base_url: str, tools: list[ToolSpec], timeout_sec: int = 30):
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_sec = timeout_sec

        # tool_name -> (ToolSpec, OpenAPI ParamSpecs)
        self._tools: dict[str, tuple[ToolSpec, list[ParamSpec]]] = {}

        # (tool_name, base) -> ToolSurface (base=None for tools without base)
        self._surface_cache: dict[tuple[str, Optional[str]], ToolSurface] = {}

        openapi = fetch_openapi(self.api_base_url, timeout_sec=timeout_sec)

        for tool in tools:
            params = resolve_query_params(openapi, tool)
            self._tools[tool.name] = (tool, params)

    def list_tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_tool(self, tool_name: str) -> tuple[ToolSpec, list[ParamSpec]]:
        item = self._tools.get(tool_name)
        if not item:
            raise KeyError(f"Tool not allowlisted: {tool_name}")
        return item

    def _allowed_filter_kind(self, tool_name: str) -> str:
        pol = get_tool_policy(tool_name)
        if pol.kind == "breakdown":
            return "breakdown"
        if pol.kind == "detail":
            return "detail"
        return "none"

    def _build_runtime_validation_params(
        self,
        tool_name: str,
        *,
        base: Optional[BaseName],
        semantic_spec: SemanticSpec,
        openapi_params: list[ParamSpec],
    ) -> list[ParamSpec]:
        """
        ParamSpec list for runtime validation of executed API params.

        This stays API-shaped:
        - includes injected 'base' when required
        - dimensions/select remain CSV strings
        """
        pol = get_tool_policy(tool_name)

        if pol.kind == "none":
            return openapi_params

        if base is None:
            raise ValueError(f"Tool '{tool_name}' requires base, but base=None was provided")

        allowed_filters = semantic_spec.allowed_filters(base, self._allowed_filter_kind(tool_name))
        allowed_keys = set(pol.core_params) | set(allowed_filters)

        return [p.model_copy(deep=True) for p in openapi_params if p.name in allowed_keys]

    def _build_planner_surface_params(
        self,
        tool_name: str,
        *,
        base: Optional[BaseName],
        semantic_spec: SemanticSpec,
        openapi_params: list[ParamSpec],
    ) -> list[ParamSpec]:
        """
        ParamSpec list for planner-facing partial LLM schema.

        Planner surface:
        - excludes injected 'base'
        - dimensions/select use arrays
        - low-card allowlists are attached as enums
        - high-card filters remain unconstrained for now
        """
        pol = get_tool_policy(tool_name)

        if pol.kind == "none":
            return [p.model_copy(deep=True) for p in openapi_params if p.name != "base"]

        if base is None:
            raise ValueError(f"Tool '{tool_name}' requires base, but base=None was provided")

        allowed_filters = semantic_spec.allowed_filters(base, self._allowed_filter_kind(tool_name))
        allowed_keys = (set(pol.core_params) | set(allowed_filters)) - {"base"}

        planner_params: list[ParamSpec] = []

        for p in openapi_params:
            if p.name not in allowed_keys:
                continue

            sp = p.model_copy(deep=True)

            if pol.kind == "breakdown":
                if sp.name == "metric":
                    sp.enum = sorted(list(semantic_spec.allowed_metrics(base)))
                elif sp.name == "dimensions":
                    sp.json_type = "array"
                    sp.items_json_type = "string"
                    sp.items_enum = sorted(list(semantic_spec.allowed_dimensions(base)))
                    sp.enum = None

            elif pol.kind == "detail":
                if sp.name == "select":
                    sp.json_type = "array"
                    sp.items_json_type = "string"
                    sp.items_enum = sorted(list(semantic_spec.allowed_columns(base)))
                    sp.enum = None

            planner_params.append(sp)

        return planner_params

    def get_surface(
        self,
        tool_name: str,
        *,
        base: Optional[BaseName],
        semantic_spec: SemanticSpec,
    ) -> ToolSurface:
        """
        Build once per (tool_name, base) and cache:
        - runtime ArgsModel
        - partial planner-facing LLM schema
        """
        key = (tool_name, base)
        cached = self._surface_cache.get(key)
        if cached:
            return cached

        spec, openapi_params = self.get_tool(tool_name)

        runtime_params = self._build_runtime_validation_params(
            tool_name,
            base=base,
            semantic_spec=semantic_spec,
            openapi_params=openapi_params,
        )
        planner_params = self._build_planner_surface_params(
            tool_name,
            base=base,
            semantic_spec=semantic_spec,
            openapi_params=openapi_params,
        )

        ArgsModel = build_pydantic_args_model(
            f"{tool_name}_{base or 'global'}",
            runtime_params,
        )
        planner_schema_partial = build_ollama_tool_schema(spec, planner_params)

        surface = ToolSurface(
            ArgsModel=ArgsModel,
            planner_schema_partial=planner_schema_partial,
        )
        self._surface_cache[key] = surface
        return surface

    def planner_schema_partial(
        self,
        tool_name: str,
        *,
        base: Optional[BaseName],
        semantic_spec: SemanticSpec,
    ) -> dict:
        """
        Return the partial planner-facing schema for (tool, base).
        High-card enums are intentionally not attached yet.
        """
        return self.get_surface(tool_name, base=base, semantic_spec=semantic_spec).planner_schema_partial

    def validate_types(
        self,
        tool_name: str,
        *,
        base: Optional[BaseName],
        semantic_spec: SemanticSpec,
        args: dict,
    ) -> dict:
        """
        Runtime validation only.

        This validates executed API params, so:
        - includes injected base when required
        - expects dimensions/select as CSV strings after adapter conversion
        """
        surface = self.get_surface(tool_name, base=base, semantic_spec=semantic_spec)
        validated = surface.ArgsModel.model_validate(args)
        return validated.model_dump(exclude_none=True)

    def validate_semantics(
        self,
        tool_name: str,
        *,
        base: Optional[BaseName],
        semantic_spec: SemanticSpec,
        args: dict,
    ) -> None:
        """
        Enforce semantic allowlists from /analytics/semantic_spec.
        Runtime-oriented: validates the final executed param values.
        """
        pol = get_tool_policy(tool_name)

        if pol.kind == "none":
            return

        if base is None:
            raise ValueError(f"Tool '{tool_name}' requires base, but base=None was provided")

        if pol.kind == "breakdown":
            metric = args.get("metric")
            if metric and metric not in semantic_spec.allowed_metrics(base):
                raise ValueError(f"Invalid metric '{metric}' for base '{base}'")

            dims_csv = args.get("dimensions") or ""
            dims = [d.strip() for d in dims_csv.split(",") if d.strip()]
            if not dims:
                raise ValueError("dimensions must be non-empty")
            if len(dims) > 2:
                raise ValueError("dimensions supports max 2 dimensions")

            allowed_dims = semantic_spec.allowed_dimensions(base)
            bad_dims = [d for d in dims if d not in allowed_dims]
            if bad_dims:
                raise ValueError(f"Invalid dimensions for base '{base}': {bad_dims}")

            allowed_filters = semantic_spec.allowed_filters(base, "breakdown")
            for k in args.keys():
                if k in {"base", "metric", "dimensions", "limit", "dry_run"}:
                    continue
                if k not in allowed_filters:
                    raise ValueError(f"Filter '{k}' not allowed for base '{base}' in breakdown")

        elif pol.kind == "detail":
            select_csv = args.get("select") or ""
            cols = [c.strip() for c in select_csv.split(",") if c.strip()]
            if not cols:
                raise ValueError("select must be non-empty")

            allowed_cols = semantic_spec.allowed_columns(base)
            bad_cols = [c for c in cols if c not in allowed_cols]
            if bad_cols:
                raise ValueError(f"Invalid select columns for base '{base}': {bad_cols}")

            allowed_filters = semantic_spec.allowed_filters(base, "detail")
            for k in args.keys():
                if k in {"base", "select", "limit", "dry_run", "seed"}:
                    continue
                if k not in allowed_filters:
                    raise ValueError(f"Filter '{k}' not allowed for base '{base}' in detail/sample")

    def call(self, tool_name: str, params: dict) -> dict:
        """
        Execute allowlisted tool via HTTP GET.
        """
        spec, _ = self.get_tool(tool_name)
        url = self.api_base_url + spec.endpoint
        if params:
            url += "?" + urlencode(params)

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            return json.load(resp)

    def call_for_llm(
        self,
        tool_name: str,
        params: dict,
        *,
        max_rows: int,
        max_chars: int,
    ) -> tuple[dict, dict]:
        """
        Call tool and produce an LLM-safe payload:
        - truncate rows
        - cap payload size
        Returns (full_result, llm_payload)
        """
        full = self.call(tool_name, params)

        payload = dict(full)
        rows = payload.get("rows")
        if isinstance(rows, list):
            payload["rows_total"] = len(rows)
            payload["rows_truncated"] = len(rows) > max_rows
            payload["rows"] = rows[:max_rows]

        text = json.dumps(payload, ensure_ascii=False)
        if len(text) > max_chars:
            payload.pop("rows", None)

        return full, payload
