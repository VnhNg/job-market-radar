from __future__ import annotations

import streamlit as st

from src.app.services.chat_service import ChatService
from src.app.ui.conversation_controller import get_active_run, sync_active_runs
from src.app.ui.session_state import (
    get_selected_thread_id,
    has_turn_progress,
    is_new_chat,
    load_turn_progress,
    set_selected_thread_id,
)
from src.app.ui.source_view import render_sources_into

from src.eval.capture_service import EvalCaptureService


BOTTOM_SPACER_REM = 6.5


def _capture_turn_as_eval_case(svc: ChatService, *, turn_id: str):
    capture = EvalCaptureService.open_for_app_service(svc)
    try:
        return capture.capture_turn(turn_id=turn_id)
    finally:
        capture.close()


def _fragment(*, run_every: str | None = None):
    fragment = getattr(st, "fragment", None)
    if fragment is None:
        def decorator(fn):
            return fn
        return decorator
    return fragment(run_every=run_every)


def _render_progress_events(events: list[dict[str, object]]) -> None:
    if not events:
        st.caption("No progress yet.")
        return

    for event in events:
        output = event.get("output") if isinstance(event.get("output"), dict) else {}
        debug_reason = output.get("debug_reason")

        if isinstance(debug_reason, str) and debug_reason.strip():
            st.caption(debug_reason.strip())


def _processing_label(*, done: bool) -> str:
    return "Done!" if done else "Processing ⏳"


def _render_processing_into(
    placeholder,
    *,
    events: list[dict[str, object]],
    done: bool,
) -> None:
    with placeholder.container():
        with st.expander(_processing_label(done=done), expanded=False):
            _render_progress_events(events)


def _render_answer_into(placeholder, *, answer_text: str | None) -> None:
    with placeholder.container():
        if answer_text:
            st.write(answer_text)


def _render_completed_assistant_turn(
    svc: ChatService,
    *,
    turn_id: str,
    assistant_text: str,
) -> None:
    processing_placeholder = st.empty()
    answer_placeholder = st.empty()
    sources_placeholder = st.empty()

    if has_turn_progress(turn_id):
        _render_processing_into(
            processing_placeholder,
            events=load_turn_progress(turn_id),
            done=True,
        )

    _render_answer_into(answer_placeholder, answer_text=assistant_text)
    render_sources_into(sources_placeholder, svc, turn_id=turn_id)

    if st.button(
        "📝",
        key=f"capture_eval_case_{turn_id}",
        help="Add this turn to eval cases",
        type="tertiary",
    ):
        try:
            result = _capture_turn_as_eval_case(svc, turn_id=turn_id)
        except Exception as exc:
            st.toast(f"Could not capture eval case: {exc}", icon="⚠️")
        else:
            if result.created:
                st.toast(f"Captured eval case: `{result.case_id}`", icon="✅")
            else:
                st.toast(f"Already captured as eval case: `{result.case_id}`", icon="ℹ️")


def _render_active_run(*, run) -> None:
    with st.chat_message("user"):
        st.write(run.user_text)

    with st.chat_message("assistant"):
        processing_placeholder = st.empty()
        answer_placeholder = st.empty()

        _render_processing_into(
            processing_placeholder,
            events=run.progress_events,
            done=run.status != "pending",
        )

        if run.status == "failed":
            _render_answer_into(
                answer_placeholder,
                answer_text=run.error_message or "The turn failed.",
            )


def _render_thread_history(svc: ChatService, *, thread_id: str) -> None:
    for turn in svc.list_turns(thread_id=thread_id):
        with st.chat_message("user"):
            st.write(turn.user_text)

        with st.chat_message("assistant"):
            _render_completed_assistant_turn(
                svc,
                turn_id=turn.id,
                assistant_text=turn.assistant_text,
            )


def _render_bottom_spacer() -> None:
    st.markdown(
        f"<div style='height:{BOTTOM_SPACER_REM}rem;'></div>",
        unsafe_allow_html=True,
    )


def _render_existing_thread(svc: ChatService, *, thread_id: str) -> None:
    thread = svc.get_thread(thread_id)
    if thread is None:
        st.warning("Selected thread was not found.")
        set_selected_thread_id(None)
        return

    active_run = get_active_run(thread_id)

    st.subheader(thread.title)
    _render_thread_history(svc, thread_id=thread_id)

    if active_run is not None:
        _render_active_run(run=active_run)

    _render_bottom_spacer()


def _render_new_chat() -> None:
    st.subheader("New chat")
    _render_bottom_spacer()


def _render_empty_state() -> None:
    st.info("Create or select a thread to start chatting.")


def _render_body(svc: ChatService) -> None:
    sync_active_runs()

    selected_thread_id = get_selected_thread_id()
    if selected_thread_id:
        _render_existing_thread(svc, thread_id=selected_thread_id)
    elif is_new_chat():
        _render_new_chat()
    else:
        _render_empty_state()


@_fragment()
def _render_conversation_static(svc: ChatService) -> None:
    _render_body(svc)


@_fragment(run_every="400ms")
def _render_conversation_polling(svc: ChatService) -> None:
    _render_body(svc)


def render_conversation_view(svc: ChatService) -> None:
    selected_thread_id = get_selected_thread_id()
    active_run = get_active_run(selected_thread_id)

    if active_run is not None and active_run.status == "pending":
        _render_conversation_polling(svc)
    else:
        _render_conversation_static(svc)