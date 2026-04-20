from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ...core.semantic_spec import BaseName
from .state import FilterValuePool


class StartTurnOutput(BaseModel):
    """
    Output of start_turn.

    - selected_prior_indexes: indexes into the bounded recent prior user-question list
    - planning_text: optional compact text built from current question + selected prior questions
    - debug_reason: short explanation of the selection/rewrite behavior
    """
    model_config = ConfigDict(extra="forbid")

    selected_prior_indexes: list[int] = Field(default_factory=list)
    planning_text: Optional[str] = None

    debug_reason: str = ""


class SelectTurnMemoryOutput(BaseModel):
    """
    Output of select_turn_memory.

    - selected_trace_indexes: indexes into SessionMemory.tool_trace
    - debug_reason: short explanation of why those trace entries are relevant
    """
    model_config = ConfigDict(extra="forbid")

    selected_trace_indexes: list[int] = Field(default_factory=list)

    debug_reason: str = ""


class RouteBaseStrategyOutput(BaseModel):
    """
    Output of route_base_strategy.

    - base: routed base for the turn
    - strategy_id: routed strategy, must exist in the strategy catalog
    """
    model_config = ConfigDict(extra="forbid")

    base: BaseName
    strategy_id: str
    calls_in_step: int = Field(ge=1)

    debug_reason: str = ""


class BuildFilterValuePoolsOutput(BaseModel):
    """
    Output of build_filter_value_pools.

    Reuses the state-level CallState class instead of introducing a parallel contract class.
    At this stage, each call is expected to have only filter_value_pools filled.
    Other CallState fields should remain at their defaults.
    """
    model_config = ConfigDict(extra="forbid")

    calls: list[list[FilterValuePool]] = Field(default_factory=list)

    debug_reason: str = ""


class StepCallsOutput(BaseModel):
    """
    Shared output shape for:
    - plan_step_calls
    - finalize_step_calls

    The ordered calls list must align 1:1 with ExecutionState.calls.
    Each dict represents planned/stabilized params for one call in the current step.
    """
    model_config = ConfigDict(extra="forbid")

    calls: list[dict[str, Any]] = Field(default_factory=list)

    debug_reason: str = ""


class CommitStepResultsOutput(BaseModel):
    """
    Output of commit_step_results.

    Reuses the state-level TraceEntry class.
    Contains only successful entries to be appended into memory.
    """
    model_config = ConfigDict(extra="forbid")

    meanings: list[str] = Field(default_factory=list)

    debug_reason: str = ""


class FinalizeAnswerOutput(BaseModel):
    """
    Temporary output of finalize_answer.

    - answer: final grounded answer text
    - sources: short source summaries derived from committed trace entries
    """
    model_config = ConfigDict(extra="forbid")

    answer: str
    sources: list[str] = Field(default_factory=list)

    debug_reason: str = ""