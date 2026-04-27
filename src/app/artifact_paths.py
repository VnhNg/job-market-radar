from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class ArtifactPaths:
    profile: str
    db_path: Path
    checkpoint_path: Path
    langsmith_project: str | None


APP_ARTIFACT_PATHS = ArtifactPaths(
    profile="app",
    db_path=Path(".local/app/app.sqlite"),
    checkpoint_path=Path(".local/app/langgraph/complete/checkpoints.sqlite"),
    langsmith_project=os.getenv("LANGSMITH_PROJECT"),
)


EVAL_ARTIFACT_PATHS = ArtifactPaths(
    profile="eval",
    db_path=Path(".local/eval/eval.sqlite"),
    checkpoint_path=Path(".local/eval/langgraph/complete/checkpoints.sqlite"),
    langsmith_project=os.getenv("LANGSMITH_EVAL_PROJECT"),
)