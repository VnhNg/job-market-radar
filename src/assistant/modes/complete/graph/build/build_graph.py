from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langchain_core.runnables import RunnableConfig

from ...nodes.start_turn import start_turn
from ...nodes.select_turn_memory import select_turn_memory
from ...nodes.route_base_strategy import route_base_strategy
from ...nodes.build_filter_value_pools import build_filter_value_pools
from ...nodes.plan_step_calls import plan_step_calls
from ...nodes.finalize_step_calls import finalize_step_calls
from ...nodes.execute_step_calls import execute_step_calls
from ...nodes.commit_step_results import commit_step_results
from ...nodes.finalize_answer import finalize_answer
from ...state import GraphState
from .strategy_state import prepare_next_step, should_finalize
from .surfaces import (
    build_call_surfaces,
    build_pool_builder_filter_field_specs,
    build_routing_base_docs,
    build_routing_tool_descriptions,
)
from .turn_state import init_execution_from_route, init_turn
from ..infra.tracing import trace_graph_node
from ..infra.runtime_context import (
    InvocationContext,
    trace_brief,
    call_pools_brief,
    planned_params_brief,
    results_brief,
)

def build_graph(
    *,
    llm,
    tool_runtime,
    semantic_spec,
    openapi: dict,
    tools,
    filter_values_fetcher,
    max_repairs,
    max_rows_to_llm,
    max_chars_to_llm,
    checkpointer=None,
):
    """
    LangGraph wiring only.

    Deterministic orchestration lives in graph.helpers.
    Business logic lives in nodes.
    """

    def _state_update(state: GraphState) -> dict[str, Any]:
        return {
            "session": state.session,
            "turn": state.turn,
        }

    def node_start_turn(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        current_user_question = runtime.context.current_user_question
        prior_user_questions = runtime.context.prior_user_questions

        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="start_turn",
            inputs={
                "current_user_question": current_user_question,
                "prior_user_questions_count": len(prior_user_questions),
            },
        ) as span:
            init_turn(state)
            out = start_turn(
                state,
                user_question=current_user_question,
                recent_user_questions=prior_user_questions,
                llm=llm,
            )
            span.end(outputs=out.model_dump())

        runtime.context.add_progress_event(
            "start_turn",
            contract_output=out,
            writes={
                "question": state.turn.context.question,
                "planning_text": state.turn.context.planning_text,
            },
        )
        return _state_update(state)

    def node_select_turn_memory(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="select_turn_memory",
            inputs={
                "question": state.turn.context.question,
                "session_trace_count": len(state.session.tool_trace),
            },
        ) as span:
            out = select_turn_memory(state, llm=llm)
            span.end(outputs=out.model_dump())

        runtime.context.add_progress_event(
            "select_turn_memory",
            contract_output=out,
            writes={
                "selected_trace_count": len(state.turn.memory.tool_trace),
                "selected_trace": trace_brief(state.turn.memory.tool_trace),
            },
        )
        return _state_update(state)

    def node_route_base_strategy(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="route_base_strategy",
            inputs={
                "question": state.turn.context.question,
                "planning_text": state.turn.context.planning_text,
                "selected_trace_count": len(state.turn.memory.tool_trace),
            },
        ) as span:
            out = route_base_strategy(
                state,
                tool_descriptions=build_routing_tool_descriptions(openapi=openapi, tools=tools),
                bases_docs=build_routing_base_docs(semantic_spec=semantic_spec),
                llm=llm,
            )
            span.end(outputs=out.model_dump())

        runtime.context.add_progress_event(
            "route_base_strategy",
            contract_output=out,
            writes={
                "base": state.turn.context.base,
                "strategy_id": state.turn.context.strategy_id,
                "calls_in_step": state.turn.context.calls_in_step,
            },
        )
        return _state_update(state)

    def node_init_execution(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="init_execution",
            inputs={
                "strategy_id": state.turn.context.strategy_id,
                "calls_in_step": state.turn.context.calls_in_step,
            },
        ) as span:
            init_execution_from_route(state)
            span.end(
                outputs={
                    "step_idx": state.turn.execution.step_idx,
                    "call_count": len(state.turn.execution.calls),
                }
            )

        runtime.context.add_progress_event(
            "init_execution",
            writes={
                "step_idx": state.turn.execution.step_idx,
                "call_count": len(state.turn.execution.calls),
            },
        )
        return _state_update(state)

    def node_build_filter_value_pools(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        filter_field_specs = build_pool_builder_filter_field_specs(
            state,
            tool_runtime=tool_runtime,
            semantic_spec=semantic_spec,
            filter_values_fetcher=filter_values_fetcher,
        )

        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="build_filter_value_pools",
            inputs={
                "question": state.turn.context.question,
                "base": state.turn.context.base,
                "strategy_id": state.turn.context.strategy_id,
                "filter_field_specs": filter_field_specs,
            },
        ) as span:
            out = build_filter_value_pools(
                state,
                filter_field_specs=filter_field_specs,
                llm=llm,
            )
            span.end(outputs=out.model_dump())

        runtime.context.add_progress_event(
            "build_filter_value_pools",
            contract_output=out,
            writes={
                "calls": call_pools_brief(state.turn.execution.calls),
            },
        )
        return _state_update(state)

    def node_plan_step_calls(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        call_surfaces = build_call_surfaces(
            state,
            tool_runtime=tool_runtime,
            semantic_spec=semantic_spec,
        )

        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="plan_step_calls",
            inputs={
                "question": state.turn.context.question,
                "base": state.turn.context.base,
                "strategy_id": state.turn.context.strategy_id,
                "call_surfaces": call_surfaces,
            },
        ) as span:
            out = plan_step_calls(
                state,
                call_surfaces=call_surfaces,
                llm=llm,
            )
            span.end(outputs=out.model_dump())

        runtime.context.add_progress_event(
            "plan_step_calls",
            contract_output=out,
            writes={
                "planned_params": planned_params_brief(state.turn.execution.calls),
            },
        )
        return _state_update(state)

    def node_finalize_step_calls(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        call_surfaces = build_call_surfaces(
            state,
            tool_runtime=tool_runtime,
            semantic_spec=semantic_spec,
        )

        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="finalize_step_calls",
            inputs={
                "base": state.turn.context.base,
                "strategy_id": state.turn.context.strategy_id,
                "planned_params": planned_params_brief(state.turn.execution.calls),
            },
        ) as span:
            summary = finalize_step_calls(
                state,
                call_surfaces=call_surfaces,
                tool_runtime=tool_runtime,
                semantic_spec=semantic_spec,
                llm=llm,
                max_repairs=max_repairs,
            )
            span.end(outputs=summary.model_dump())

        runtime.context.add_progress_event(
            "finalize_step_calls",
            writes=summary.model_dump(),
        )
        return _state_update(state)

    def node_execute_step_calls(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="execute_step_calls",
            inputs={
                "base": state.turn.context.base,
                "strategy_id": state.turn.context.strategy_id,
                "planned_params": planned_params_brief(state.turn.execution.calls),
            },
        ) as span:
            execute_step_calls(
                state,
                tool_runtime=tool_runtime,
                max_rows_to_llm=max_rows_to_llm,
                max_chars_to_llm=max_chars_to_llm,
            )
            span.end(
                outputs={
                    "results": results_brief(state.turn.execution.calls),
                }
            )

        runtime.context.add_progress_event(
            "execute_step_calls",
            writes={
                "results": results_brief(state.turn.execution.calls),
            },
        )
        return _state_update(state)

    def node_commit_step_results(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        session_before = len(state.session.tool_trace)
        turn_before = len(state.turn.memory.tool_trace)

        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="commit_step_results",
            inputs={
                "base": state.turn.context.base,
                "results": results_brief(state.turn.execution.calls),
            },
        ) as span:
            out = commit_step_results(state, llm=llm)
            span.end(outputs=out.model_dump())

        runtime.context.add_progress_event(
            "commit_step_results",
            contract_output=out,
            writes={
                "committed_count": len(out.meanings),
                "session_trace_before": session_before,
                "session_trace_after": len(state.session.tool_trace),
                "turn_trace_before": turn_before,
                "turn_trace_after": len(state.turn.memory.tool_trace),
                "committed_trace_tail": trace_brief(state.turn.memory.tool_trace),
            },
        )
        return _state_update(state)

    def node_prepare_next_step(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="prepare_next_step",
            inputs={
                "current_step_idx": state.turn.execution.step_idx,
                "current_call_count": len(state.turn.execution.calls),
            },
        ) as span:
            prepare_next_step(state)
            span.end(
                outputs={
                    "step_idx": state.turn.execution.step_idx,
                    "call_count": len(state.turn.execution.calls),
                }
            )

        runtime.context.add_progress_event(
            "prepare_next_step",
            writes={
                "step_idx": state.turn.execution.step_idx,
                "call_count": len(state.turn.execution.calls),
            },
        )
        return _state_update(state)

    def node_finalize_answer(state: GraphState, config: RunnableConfig, runtime: Runtime[InvocationContext]):
        with trace_graph_node(
            thread_id=config["configurable"]["thread_id"],
            node_name="finalize_answer",
            inputs={
                "question": state.turn.context.question,
                "turn_trace_count": len(state.turn.memory.tool_trace),
            },
        ) as span:
            answer = finalize_answer(state, llm=llm)
            runtime.context.final_answer = answer
            span.end(
                outputs={
                    "answer_preview": answer[:300],
                    "answer_length": len(answer),
                }
            )

        runtime.context.add_progress_event(
            "finalize_answer",
            writes={
                "answer_preview": answer[:300],
                "answer_length": len(answer),
                "turn_trace_count": len(state.turn.memory.tool_trace),
            },
        )
        return _state_update(state)

    def route_after_commit(state: GraphState) -> Literal["prepare_next_step", "finalize_answer"]:
        if should_finalize(state):
            return "finalize_answer"
        return "prepare_next_step"

    builder = StateGraph(GraphState, context_schema=InvocationContext)

    builder.add_node("start_turn", node_start_turn)
    builder.add_node("select_turn_memory", node_select_turn_memory)
    builder.add_node("route_base_strategy", node_route_base_strategy)
    builder.add_node("init_execution", node_init_execution)

    builder.add_node("build_filter_value_pools", node_build_filter_value_pools)
    builder.add_node("plan_step_calls", node_plan_step_calls)
    builder.add_node("finalize_step_calls", node_finalize_step_calls)
    builder.add_node("execute_step_calls", node_execute_step_calls)
    builder.add_node("commit_step_results", node_commit_step_results)

    builder.add_node("prepare_next_step", node_prepare_next_step)
    builder.add_node("finalize_answer", node_finalize_answer)

    builder.add_edge(START, "start_turn")
    builder.add_edge("start_turn", "select_turn_memory")
    builder.add_edge("select_turn_memory", "route_base_strategy")
    builder.add_edge("route_base_strategy", "init_execution")

    builder.add_edge("init_execution", "build_filter_value_pools")
    builder.add_edge("build_filter_value_pools", "plan_step_calls")
    builder.add_edge("plan_step_calls", "finalize_step_calls")
    builder.add_edge("finalize_step_calls", "execute_step_calls")
    builder.add_edge("execute_step_calls", "commit_step_results")

    builder.add_conditional_edges("commit_step_results", route_after_commit)

    builder.add_edge("prepare_next_step", "build_filter_value_pools")
    builder.add_edge("finalize_answer", END)

    return builder.compile(checkpointer=checkpointer)


