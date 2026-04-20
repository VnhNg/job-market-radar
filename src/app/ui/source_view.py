from __future__ import annotations

import streamlit as st

from src.app.services.chat_service import ChatService
from src.app.ui.session_state import full_rows_key, source_open_key, sources_open_key


def render_source_item(
    svc: ChatService,
    *,
    turn_id: str,
    source_index: int,
    source,
) -> None:
    title = source.meaning or f"Source {source_index + 1}"
    card_open_key = source_open_key(turn_id, source_index)
    rows_key = full_rows_key(turn_id, source_index)

    with st.popover(title, width="stretch"):
        st.session_state[card_open_key] = True

        st.caption(
            f"Tool: {source.tool_name} · Base: {source.base} · "
            f"Rows: {source.rows_total if source.rows_total is not None else 'unknown'}"
        )

        st.markdown("**Params**")
        st.json(source.params)

        full_rows = st.session_state.get(rows_key)
        if isinstance(full_rows, list):
            st.markdown("**Full table**")
            if full_rows:
                st.dataframe(full_rows, width="stretch")
            else:
                st.caption("No rows returned.")
            return

        st.markdown("**Table preview**")
        if source.rows:
            st.dataframe(source.rows, width="stretch")
        else:
            st.caption("No preview rows available.")

        if st.button("Load full table", key=f"{turn_id}:source:{source_index}:load_full"):
            st.session_state[rows_key] = svc.load_full_source_rows(
                turn_id=turn_id,
                source_index=source_index,
            )
            st.session_state[card_open_key] = True
            st.session_state[sources_open_key(turn_id)] = True
            st.rerun()


def render_sources_into(placeholder, svc: ChatService, *, turn_id: str) -> None:
    with placeholder.container():
        with st.expander(
            "Sources",
            expanded=st.session_state.get(sources_open_key(turn_id), False),
        ):
            sources = svc.list_sources_for_turn(turn_id=turn_id)
            if not sources:
                st.caption("No sources available.")
                return

            for source_index, source in enumerate(sources):
                render_source_item(
                    svc,
                    turn_id=turn_id,
                    source_index=source_index,
                    source=source,
                )