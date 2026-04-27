from __future__ import annotations

import streamlit as st

from src.app.services.chat_service import ChatService
from src.app.ui.conversation_controller import get_active_run, submit_message
from src.app.ui.conversation_view import render_conversation_view
from src.app.ui.session_state import get_selected_thread_id, is_new_chat
from src.app.ui.sidebar import inject_sidebar_styles, render_thread_sidebar


st.set_page_config(page_title="Job Radar", layout="wide")


def _get_service() -> ChatService:
    if "chat_service" not in st.session_state:
        st.session_state.chat_service = ChatService.open_app()
    return st.session_state.chat_service


def _can_render_chat_input() -> bool:
    return get_selected_thread_id() is not None or is_new_chat()


def _chat_input_disabled() -> bool:
    thread_id = get_selected_thread_id()
    if not thread_id:
        return False

    active_run = get_active_run(thread_id)
    return bool(active_run is not None and active_run.status == "pending")


def _chat_input_placeholder() -> str:
    if _chat_input_disabled():
        return "This conversation is processing..."
    return "Ask about the job market"


def main() -> None:
    svc = _get_service()

    st.title("Job Radar")
    inject_sidebar_styles()
    render_thread_sidebar(svc)
    render_conversation_view(svc)

    if _can_render_chat_input():
        user_text = st.chat_input(
            _chat_input_placeholder(),
            disabled=_chat_input_disabled(),
        )
        if user_text:
            submit_message(svc, user_text=user_text)
            st.rerun()


if __name__ == "__main__":
    main()