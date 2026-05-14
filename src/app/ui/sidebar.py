from __future__ import annotations

import streamlit as st

from src.app.services.chat_service import ChatService
from src.app.ui.conversation_controller import get_active_run
from src.app.ui.session_state import (
    clear_turn_ui_state,
    get_selected_thread_id,
    leave_new_chat_mode,
    set_selected_thread_id,
    start_new_chat,
)


TOP_TOGGLE_CLEARANCE_REM = 2.6
TOP_PANEL_CONTENT_REM = 4.9
BOTTOM_PANEL_TOTAL_REM = 4.2


def inject_sidebar_styles() -> None:
    list_height_css = (
        f"calc(100vh - {TOP_TOGGLE_CLEARANCE_REM + TOP_PANEL_CONTENT_REM + BOTTOM_PANEL_TOTAL_REM + 0.5}rem)"
    )

    st.markdown(
        f"""
        <style>
        [data-testid="stSidebarContent"] {{
            overflow: hidden !important;
            height: 100vh !important;
            background: var(--secondary-background-color) !important;
        }}

        /* Top shell area */
        [data-testid="stSidebarContent"] .st-key-sidebar_top_panel {{
            margin-top: {TOP_TOGGLE_CLEARANCE_REM}rem !important;
            min-height: {TOP_PANEL_CONTENT_REM}rem !important;
            box-sizing: border-box !important;
            padding: 0.5rem 0.75rem 0.35rem 0.75rem !important;
            background: var(--secondary-background-color) !important;
            border-bottom: 1px solid rgba(128, 128, 128, 0.14) !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_top_panel > div {{
            row-gap: 0.45rem !important;
        }}

        .sidebar-recent-conversations-title {{
            margin: 0 !important;
            padding: 0 0.15rem !important;
            font-size: 1.25rem !important;
            line-height: 1.2 !important;
            font-weight: 600 !important;
            color: var(--text-color) !important;
        }}

        /* Middle scroll container */
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel {{
            height: {list_height_css} !important;
            background: var(--secondary-background-color) !important;
            padding: 0.15rem 0 0.35rem 0 !important;
            overflow-x: hidden !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel > div {{
            padding-left: 0 !important;
            padding-right: 0 !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stVerticalBlock"] {{
            overflow-x: hidden !important;
        }}

        /* Bottom shell area */
        [data-testid="stSidebarContent"] .st-key-sidebar_bottom_panel {{
            min-height: {BOTTOM_PANEL_TOTAL_REM}rem !important;
            box-sizing: border-box !important;
            padding: 0.5rem 0.75rem 0.75rem 0.75rem !important;
            background: var(--secondary-background-color) !important;
            border-top: 1px solid rgba(128, 128, 128, 0.14) !important;
        }}

        /* New Chat button */
        [data-testid="stSidebarContent"] .st-key-sidebar_top_panel button[kind="primary"] {{
            border: 1px solid rgba(128, 128, 128, 0.45) !important;
            background: rgba(255, 255, 255, 0.02) !important;
            box-shadow: none !important;
            height: 2.75rem !important;
            min-height: 2.75rem !important;
            max-height: 2.75rem !important;
            padding: 0.25rem 0.75rem !important;
            justify-content: center !important;
            align-items: center !important;
            transition: transform 0.14s ease, background 0.14s ease, border-color 0.14s ease !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_top_panel button[kind="primary"] p {{
            margin: 0 !important;
            font-size: 1.04rem !important;
            font-weight: 600 !important;
            color: var(--text-color) !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_top_panel button[kind="primary"]:hover {{
            border-color: rgba(128, 128, 128, 0.8) !important;
            background: rgba(255, 255, 255, 0.06) !important;
            transform: translateY(-1px) !important;
        }}

        /* Popover trigger button */
        [data-testid="stSidebarContent"] .st-key-sidebar_bottom_panel button[kind="secondary"] {{
            border: 1px solid rgba(128, 128, 128, 0.35) !important;
            background: transparent !important;
            box-shadow: none !important;
            height: 2.75rem !important;
            min-height: 2.75rem !important;
            max-height: 2.75rem !important;
            padding: 0 !important;
            justify-content: center !important;
            align-items: center !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_bottom_panel button[kind="secondary"] p {{
            margin: 0 !important;
            font-weight: 600 !important;
            text-align: center !important;
        }}

        /* Conversation row layout: full width, no horizontal scrollbar */
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] {{
            width: 100% !important;
            gap: 0.15rem !important;
            overflow: hidden !important;
            padding: 0 0.25rem !important;
            box-sizing: border-box !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div {{
            min-width: 0 !important;
        }}

        /* Conversation buttons */
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button {{
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            width: 100% !important;
            height: 2.6rem !important;
            min-height: 2.6rem !important;
            max-height: 2.6rem !important;
            padding: 0.25rem 0.5rem !important;
            justify-content: flex-start !important;
            align-items: center !important;
            color: var(--text-color) !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button p {{
            width: 100% !important;
            margin: 0 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            display: block !important;
            line-height: 1.2 !important;
            color: var(--text-color) !important;
            transform: scale(1) !important;
            transform-origin: left center !important;
            transition: transform 0.14s ease, font-weight 0.14s ease, color 0.14s ease !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button[kind="tertiary"] p {{
            font-weight: 500 !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button[kind="secondary"] p {{
            font-weight: 650 !important;
            text-decoration: underline !important;
            text-underline-offset: 0.18rem !important;
            text-decoration-thickness: 1.5px !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button[kind="tertiary"]:hover,
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button[kind="secondary"]:hover {{
            color: var(--text-color) !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button[kind="tertiary"]:hover p,
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(1) button[kind="secondary"]:hover p {{
            color: var(--text-color) !important;
            transform: scale(1.08) !important;
        }}

        /* Delete x button */
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(2) button[kind="tertiary"] {{
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            width: 100% !important;
            height: 2.6rem !important;
            min-height: 2.6rem !important;
            max-height: 2.6rem !important;
            padding: 0 !important;
            justify-content: center !important;
            align-items: center !important;
            opacity: 0 !important;
            pointer-events: none !important;
            transition: opacity 0.14s ease !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"] > div:nth-child(2) button[kind="tertiary"] p {{
            width: 100% !important;
            margin: 0 !important;
            text-align: center !important;
            font-weight: 600 !important;
            color: var(--text-color) !important;
            transition: color 0.14s ease !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"]:hover > div:nth-child(2) button[kind="tertiary"] {{
            opacity: 1 !important;
            pointer-events: auto !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"]:has(> div:nth-child(2) button[kind="tertiary"]:hover) > div:nth-child(2) button[kind="tertiary"] p,
        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"]:has(> div:nth-child(2) button[kind="tertiary"]:hover) > div:nth-child(1) button p {{
            color: #d11a2a !important;
        }}

        [data-testid="stSidebarContent"] .st-key-sidebar_list_panel [data-testid="stHorizontalBlock"]:has(> div:nth-child(2) button[kind="tertiary"]:hover) > div:nth-child(1) button p {{
            transform: scale(1.08) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_settings_popover() -> None:
    if "max_prior_user_questions" not in st.session_state:
        st.session_state.max_prior_user_questions = 5

    with st.popover("⚙ Setting", width="content"):
        st.caption("Settings")
        st.number_input(
            "Previous questions to reuse",
            min_value=0,
            max_value=20,
            step=1,
            key="max_prior_user_questions",
        )


def render_thread_row(
    svc: ChatService,
    *,
    thread,
    selected_thread_id: str | None,
) -> None:
    active_run = get_active_run(thread.id)
    is_selected = selected_thread_id == thread.id
    is_processing = bool(active_run is not None and active_run.status == "pending")

    label = thread.title
    if is_selected:
        label = f"▸ {label}"
    if is_processing:
        label = f"{label} ⏳"

    title_button_type = "secondary" if is_selected else "tertiary"

    thread_col, delete_col = st.columns([0.94, 0.06], gap="small")

    with thread_col:
        if st.button(
            label,
            key=f"thread:{thread.id}",
            width="stretch",
            type=title_button_type,
        ):
            set_selected_thread_id(thread.id)
            leave_new_chat_mode()
            st.rerun()

    with delete_col:
        if st.button(
            "x",
            key=f"thread:{thread.id}:delete",
            width="stretch",
            type="tertiary",
            disabled=is_processing,
        ):
            turn_ids = [turn.id for turn in svc.list_turns(thread_id=thread.id)]

            try:
                svc.delete_thread(thread.id)
            except Exception as exc:
                st.error(str(exc))
            else:
                for turn_id in turn_ids:
                    clear_turn_ui_state(turn_id)

                if get_selected_thread_id() == thread.id:
                    set_selected_thread_id(None)
                    leave_new_chat_mode()

                st.rerun()


def render_thread_sidebar(svc: ChatService) -> None:
    with st.sidebar:
        with st.container(key="sidebar_top_panel"):
            if st.button("New Chat", width="stretch", type="primary"):
                start_new_chat()
                st.rerun()

            st.markdown(
                '<div class="sidebar-recent-conversations-title">Recent Conversations</div>',
                unsafe_allow_html=True,
            )

        with st.container(key="sidebar_list_panel", height=420, border=False):
            selected_thread_id = get_selected_thread_id()
            for thread in svc.list_threads():
                render_thread_row(
                    svc,
                    thread=thread,
                    selected_thread_id=selected_thread_id,
                )

        with st.container(key="sidebar_bottom_panel"):
            render_settings_popover()