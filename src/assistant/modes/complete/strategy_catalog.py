from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field


class StepKind(str, Enum):
    B = "B"  # breakdown
    D = "D"  # detail
    S = "S"  # sample


class StrategyMode(str, Enum):
    SINGLE_STEP = "single_step"
    MULTI_STEP = "multi_step"


STEP_TO_TOOL: Dict[StepKind, str] = {
    StepKind.B: "analytics_breakdown",
    StepKind.D: "analytics_detail",
    StepKind.S: "analytics_sample",
}


class StepSpec(BaseModel):
    """
    One step in a strategy chain.
    Description is step-local and should only explain the role of this step.
    """
    model_config = ConfigDict(extra="forbid")

    kind: StepKind
    description: str = ""


class StrategySpec(BaseModel):
    """
    Strategy = allowed dependency chain of tool calls.

    Rules:
    - single_step: exactly 1 step, may emit up to max_calls_in_step calls
    - multi_step: 2-3 steps, exactly 1 call per step
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: StrategyMode
    steps: List[StepSpec] = Field(min_length=1, max_length=3)
    max_calls_in_step: int = Field(ge=1)

    def model_post_init(self, __context) -> None:
        if self.mode == StrategyMode.SINGLE_STEP:
            if len(self.steps) != 1:
                raise ValueError("single_step strategies must have exactly 1 step")
        elif self.mode == StrategyMode.MULTI_STEP:
            if len(self.steps) < 2 or len(self.steps) > 3:
                raise ValueError("multi_step strategies must have 2-3 steps")
            if self.max_calls_in_step != 1:
                raise ValueError("multi_step strategies must have max_calls_in_step=1")
        else:
            raise ValueError(f"Unknown strategy mode: {self.mode}")


def _step(kind: StepKind, description: str) -> StepSpec:
    return StepSpec(kind=kind, description=description)


def _strategy(
    strategy_id: str,
    mode: StrategyMode,
    steps: List[StepSpec],
    max_calls_in_step: int,
) -> StrategySpec:
    return StrategySpec(
        id=strategy_id,
        mode=mode,
        steps=steps,
        max_calls_in_step=max_calls_in_step,
    )


CATALOG: Dict[str, StrategySpec] = {
    # ---------- single-step ----------
    "SINGLE_BREAKDOWN": _strategy(
        "SINGLE_BREAKDOWN",
        StrategyMode.SINGLE_STEP,
        [
            _step(
                StepKind.B,
                "Produce one or more aggregate breakdown calls for the current ask. "
                "Use this when the question can be answered directly from grouped or ranked aggregate outputs. "
                "If multiple known slices should be analyzed separately, distribute them across calls instead of collapsing them into one call.",
            )
        ],
        max_calls_in_step=3,
    ),

    "SINGLE_DETAIL": _strategy(
        "SINGLE_DETAIL",
        StrategyMode.SINGLE_STEP,
        [
            _step(
                StepKind.D,
                "Produce one or more detail calls when the needed entity or slice is already known "
                "from the question or available memory. "
                "If multiple target entities or slices are already known and each call can describe only one of them, "
                "use separate calls rather than combining multiple values into one call. "
                "Preserve meaningful ordering from memory when the candidates are ranked.",
            )
        ],
        max_calls_in_step=3,
    ),

    "SINGLE_SAMPLE": _strategy(
        "SINGLE_SAMPLE",
        StrategyMode.SINGLE_STEP,
        [
            _step(
                StepKind.S,
                "Produce one or more sample calls when examples are sufficient and the target "
                "entity or slice is already known from the question or available memory. "
                "If separate examples are needed for multiple known entities or slices and each call can cover only one of them, "
                "distribute them across calls instead of combining them into one call. "
                "Preserve meaningful ordering from memory when the candidates are ranked.",
            )
        ],
        max_calls_in_step=3,
    ),

    # ---------- two-step ----------
    "B_B": _strategy(
        "B_B",
        StrategyMode.MULTI_STEP,
        [
            _step(
                StepKind.B,
                "First produce an upstream breakdown that creates the aggregate context or candidates needed downstream.",
            ),
            _step(
                StepKind.B,
                "Then run a second breakdown using grounded information from prior entries or the upstream step.",
            ),
        ],
        max_calls_in_step=1,
    ),
    "B_D": _strategy(
        "B_D",
        StrategyMode.MULTI_STEP,
        [
            _step(
                StepKind.B,
                "First produce a breakdown that creates grounded candidates for downstream drill-through.",
            ),
            _step(
                StepKind.D,
                "Then fetch detail rows for a grounded candidate coming from memory or the upstream breakdown.",
            ),
        ],
        max_calls_in_step=1,
    ),
    "S_B": _strategy(
        "S_B",
        StrategyMode.MULTI_STEP,
        [
            _step(
                StepKind.S,
                "First produce example rows to inspect or identify grounded candidates.",
            ),
            _step(
                StepKind.B,
                "Then run a breakdown using grounded information from memory or the upstream sample.",
            ),
        ],
        max_calls_in_step=1,
    ),
    "S_D": _strategy(
        "S_D",
        StrategyMode.MULTI_STEP,
        [
            _step(
                StepKind.S,
                "First produce example rows needed to identify or confirm grounded candidates.",
            ),
            _step(
                StepKind.D,
                "Then fetch detail rows using grounded information from memory or the upstream sample.",
            ),
        ],
        max_calls_in_step=1,
    ),
    "D_D": _strategy(
        "D_D",
        StrategyMode.MULTI_STEP,
        [
            _step(
                StepKind.D,
                "First fetch detail rows to expose grounded identifiers or entities needed downstream.",
            ),
            _step(
                StepKind.D,
                "Then fetch a second detail slice using grounded information from memory or the upstream detail.",
            ),
        ],
        max_calls_in_step=1,
    ),

    # ---------- three-step ----------
    "B_B_B": _strategy(
        "B_B_B",
        StrategyMode.MULTI_STEP,
        [
            _step(StepKind.B, "First produce an aggregate view that creates upstream context."),
            _step(StepKind.B, "Then refine the aggregate analysis using grounded upstream information."),
            _step(StepKind.B, "Finally produce the last aggregate view needed to answer the question."),
        ],
        max_calls_in_step=1,
    ),
    "B_B_D": _strategy(
        "B_B_D",
        StrategyMode.MULTI_STEP,
        [
            _step(StepKind.B, "First produce an aggregate view that creates upstream context."),
            _step(StepKind.B, "Then refine the aggregate analysis using grounded upstream information."),
            _step(StepKind.D, "Finally fetch detail rows using grounded candidates from prior entries."),
        ],
        max_calls_in_step=1,
    ),
    "S_B_D": _strategy(
        "S_B_D",
        StrategyMode.MULTI_STEP,
        [
            _step(StepKind.S, "First produce example rows to expose grounded candidates."),
            _step(StepKind.B, "Then run a breakdown using grounded information from prior entries."),
            _step(StepKind.D, "Finally fetch detail rows for a grounded candidate."),
        ],
        max_calls_in_step=1,
    ),
    "S_B_B": _strategy(
        "S_B_B",
        StrategyMode.MULTI_STEP,
        [
            _step(StepKind.S, "First produce example rows to expose grounded candidates."),
            _step(StepKind.B, "Then run a breakdown using grounded information from prior entries."),
            _step(StepKind.B, "Finally run a second aggregate refinement using grounded upstream information."),
        ],
        max_calls_in_step=1,
    ),
    "D_B_B": _strategy(
        "D_B_B",
        StrategyMode.MULTI_STEP,
        [
            _step(StepKind.D, "First fetch detail rows to expose grounded identifiers or entities."),
            _step(StepKind.B, "Then run a breakdown using grounded information from prior entries."),
            _step(StepKind.B, "Finally run a second aggregate refinement using grounded upstream information."),
        ],
        max_calls_in_step=1,
    ),
    "D_B_D": _strategy(
        "D_B_D",
        StrategyMode.MULTI_STEP,
        [
            _step(StepKind.D, "First fetch detail rows to expose grounded identifiers or entities."),
            _step(StepKind.B, "Then run a breakdown using grounded information from prior entries."),
            _step(StepKind.D, "Finally fetch detail rows using grounded candidates from memory or upstream output."),
        ],
        max_calls_in_step=1,
    ),
}


def get_strategy(strategy_id: str) -> StrategySpec:
    spec = CATALOG.get(strategy_id)
    if not spec:
        raise KeyError(f"Strategy not allowlisted: {strategy_id}")
    return spec


def tool_for_step(step_kind: StepKind) -> str:
    return STEP_TO_TOOL[step_kind]