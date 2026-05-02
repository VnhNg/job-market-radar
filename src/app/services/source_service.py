from __future__ import annotations

from dataclasses import dataclass

from src.app.repos.turn_repo import TurnRepo, TurnRow
from src.assistant.modes.complete.bootstrap import CompleteBootstrap
from src.assistant.modes.complete.graph.infra.checkpoints import checkpoint_config


@dataclass
class SourceCard:
    tool_name: str
    base: str
    meaning: str
    params: dict
    rows: list[dict[str, object]]
    rows_total: int | None

@dataclass
class SourceService:
    bootstrap: CompleteBootstrap
    turn_repo: TurnRepo

    def get_turn(self, turn_id: str) -> TurnRow | None:
        return self.turn_repo.get_turn(turn_id)

    def list_sources_for_turn(self, *, turn_id: str) -> list[SourceCard]:
        turn = self.turn_repo.get_turn(turn_id)
        if turn is None:
            raise RuntimeError(f"Turn not found: {turn_id}")

        snapshot = self.bootstrap.graph.get_state(
            checkpoint_config(turn.thread_id, turn.checkpoint_id)
        )
        values = getattr(snapshot, "values", None) or {}
        turn_state = values.get("turn")
        if turn_state is None:
            return []

        tool_trace = turn_state.memory.tool_trace
        return [
            SourceCard(
                tool_name=entry.tool_name,
                base=entry.base,
                meaning=entry.meaning,
                params=dict(entry.params),
                rows=[
                    dict(row)
                    for row in entry.results.get("rows", [])
                    if isinstance(row, dict)
                ],
                rows_total=entry.results.get("rows_total"),
            )
            for entry in tool_trace
        ]
    

    def load_full_source_rows(self, *, turn_id: str, source_index: int) -> list[dict[str, object]]:
        turn = self.turn_repo.get_turn(turn_id)
        if turn is None:
            raise RuntimeError(f"Turn not found: {turn_id}")

        snapshot = self.bootstrap.graph.get_state(
            checkpoint_config(turn.thread_id, turn.checkpoint_id)
        )
        values = getattr(snapshot, "values", None) or {}
        turn_state = values.get("turn")
        if turn_state is None:
            return []

        tool_trace = turn_state.memory.tool_trace
        if source_index < 0 or source_index >= len(tool_trace):
            raise IndexError(f"Source index out of range: {source_index}")

        entry = tool_trace[source_index]
        full_result = self.bootstrap.tool_runtime.call(entry.tool_name, dict(entry.params))

        rows = full_result.get("rows")
        if not isinstance(rows, list):
            return []

        return [
            dict(row)
            for row in rows
            if isinstance(row, dict)
        ]