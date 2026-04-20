from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.semantic_spec import BaseName


# -------------------------
# Bounds
# -------------------------
MAX_TRACE_ENTRIES = 25


# -------------------------
# Persistent session memory
# -------------------------
class TraceEntry(BaseModel):
    """
    Long-lived reusable memory unit.
    """
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    base: Optional[BaseName] = None
    params: dict[str, Any] = Field(default_factory=dict)

    latency_ms: Optional[int] = None

    # bounded result payload suitable for later LLM reuse
    results: dict[str, Any] = Field(default_factory=dict)

    # compact semantic description of what this result is about
    meaning: str = ""


class SessionMemory(BaseModel):
    """
    Persistent across turns.
    """
    model_config = ConfigDict(extra="forbid")

    tool_trace: list[TraceEntry] = Field(default_factory=list)

    @field_validator("tool_trace")
    @classmethod
    def _bound_trace(cls, v: list[TraceEntry]) -> list[TraceEntry]:
        return v[-MAX_TRACE_ENTRIES:]


# -------------------------
# Turn-stable context
# -------------------------
class TurnContext(BaseModel):
    """
    Stable turn-level context shared across all steps in the current turn.

    This layer carries information remaining constant while the
    strategy executes, always available for downstream nodes.
    """
    model_config = ConfigDict(extra="forbid")

    question: str
    planning_text: Optional[str] = None

    base: Optional[BaseName] = None
    strategy_id: Optional[str] = None
    calls_in_step: Optional[int] = None


class TurnMemory(BaseModel):
    """
    Turn-scoped memory window.

    This is the subset of SessionMemory.tool_trace selected as relevant
    for the current turn. It will be extended when a step is executed
    successfully in the turn, but discarded when the turn ends.
    """
    model_config = ConfigDict(extra="forbid")

    tool_trace: list[TraceEntry] = Field(default_factory=list)

    @field_validator("tool_trace")
    @classmethod
    def _bound_trace(cls, v: list[TraceEntry]) -> list[TraceEntry]:
        return v[-MAX_TRACE_ENTRIES:]


# -------------------------
# Mutable execution state
# -------------------------
class FilterValuePool(BaseModel):
    """
    Call-local grounded candidate values for one filter field.
    """
    model_config = ConfigDict(extra="forbid")

    field_name: str
    values: list[Any] = Field(default_factory=list)
    description: str = ""


class CallState(BaseModel):
    """
    Mutable state for one tool call within the current step.
    """
    model_config = ConfigDict(extra="forbid")

    filter_value_pools: list[FilterValuePool] = Field(default_factory=list)
    planned_params: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)


class ExecutionState(BaseModel):
    """
    Mutable execution state for the current strategy step.

    Notes:
    - step_idx identifies where we are in the chain
    - everything derivable from (strategy_id, step_idx) must not be stored here
    """
    model_config = ConfigDict(extra="forbid")

    step_idx: int = 0
    calls: list[CallState] = Field(default_factory=list)


# -------------------------
# Turn container
# -------------------------
class Turn(BaseModel):
    """
    Current turn container.

    Combines:
    - stable turn context
    - turn-scoped memory window
    - mutable execution state
    """
    model_config = ConfigDict(extra="forbid")

    context: TurnContext
    memory: TurnMemory = Field(default_factory=TurnMemory)
    execution: ExecutionState = Field(default_factory=ExecutionState)


# -------------------------
# Top-level graph state
# -------------------------
class GraphState(BaseModel):
    """
    Top-level graph state.

    - session: persistent reusable memory across turns
    - turn: current turn only
    """
    model_config = ConfigDict(extra="forbid")

    session: SessionMemory = Field(default_factory=SessionMemory)
    turn: Optional[Turn] = None