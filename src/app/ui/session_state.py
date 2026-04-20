from __future__ import annotations

import streamlit as st


def get_selected_thread_id() -> str | None:
    return st.session_state.get("selected_thread_id")


def set_selected_thread_id(thread_id: str | None) -> None:
    if thread_id is None:
        st.session_state.pop("selected_thread_id", None)
    else:
        st.session_state.selected_thread_id = thread_id


def is_new_chat() -> bool:
    return bool(st.session_state.get("is_new_chat", False))


def start_new_chat() -> None:
    set_selected_thread_id(None)
    st.session_state.is_new_chat = True


def leave_new_chat_mode() -> None:
    st.session_state.is_new_chat = False


def toggle_settings_panel() -> None:
    st.session_state.show_settings_panel = not bool(
        st.session_state.get("show_settings_panel", False)
    )


def show_settings_panel() -> bool:
    return bool(st.session_state.get("show_settings_panel", False))


def get_max_prior_user_questions() -> int:
    if "max_prior_user_questions" not in st.session_state:
        st.session_state.max_prior_user_questions = 5
    return int(st.session_state.max_prior_user_questions)


def progress_state_key(turn_id: str) -> str:
    return f"turn:{turn_id}:progress_events"


def sources_open_key(turn_id: str) -> str:
    return f"turn:{turn_id}:sources_open"


def source_open_key(turn_id: str, source_index: int) -> str:
    return f"turn:{turn_id}:source:{source_index}:open"


def full_rows_key(turn_id: str, source_index: int) -> str:
    return f"turn:{turn_id}:source:{source_index}:full_rows"


def store_turn_progress(turn_id: str, events: list[dict[str, object]]) -> None:
    st.session_state[progress_state_key(turn_id)] = list(events)


def load_turn_progress(turn_id: str) -> list[dict[str, object]]:
    value = st.session_state.get(progress_state_key(turn_id), [])
    return value if isinstance(value, list) else []


def has_turn_progress(turn_id: str) -> bool:
    return len(load_turn_progress(turn_id)) > 0


def clear_turn_ui_state(turn_id: str) -> None:
    keys_to_delete = [
        progress_state_key(turn_id),
        sources_open_key(turn_id),
    ]

    source_prefix = f"turn:{turn_id}:source:"
    for key in list(st.session_state.keys()):
        if key.startswith(source_prefix):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        st.session_state.pop(key, None)