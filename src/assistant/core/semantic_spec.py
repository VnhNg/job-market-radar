from __future__ import annotations

import json
from typing import Literal
import urllib.request

from pydantic import BaseModel, Field


BaseName = Literal["jobs", "replication"]
ToolKind = Literal["breakdown", "detail"]  


class BaseDoc(BaseModel):
    grain: str = ""
    good_for: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class BreakdownBaseSpec(BaseModel):
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, str] = Field(default_factory=dict)  


class DetailBaseSpec(BaseModel):
    columns: list[str] = Field(default_factory=list)
    filters: dict[str, str] = Field(default_factory=dict)  


class SemanticSpec(BaseModel):
    bases: dict[BaseName, BaseDoc] = Field(default_factory=dict)
    breakdown: dict[BaseName, BreakdownBaseSpec]
    detail: dict[BaseName, DetailBaseSpec]

    def base_doc(self, base: BaseName) -> BaseDoc:
        return self.bases.get(base, BaseDoc())
    
    def allowed_metrics(self, base: BaseName) -> set[str]:
        return set(self.breakdown[base].metrics)

    def allowed_dimensions(self, base: BaseName) -> set[str]:
        return set(self.breakdown[base].dimensions)

    def allowed_columns(self, base: BaseName) -> set[str]:
        return set(self.detail[base].columns)

    def allowed_filters(self, base: BaseName, kind: ToolKind) -> set[str]:
        if kind == "breakdown":
            return set(self.breakdown[base].filters.keys())
        return set(self.detail[base].filters.keys())


def fetch_semantic_spec(api_base_url: str, timeout_sec: int = 30) -> SemanticSpec:
    """
    Fetch governed allowlists from the API.
    Source of truth for which metrics/dimensions/columns are valid per base.
    """
    url = api_base_url.rstrip("/") + "/analytics/semantic_spec"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        data = json.load(resp)
    return SemanticSpec.model_validate(data)
