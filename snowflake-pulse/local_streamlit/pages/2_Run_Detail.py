import streamlit as st

from local_streamlit.session import get_session


st.set_page_config(page_title="Run Detail | Pulse (Local)", page_icon="⚡", layout="wide")

session = get_session()

st.title("🔍 Run Detail")

# ── Filters ──
col1, col2 = st.columns(2)

with col1:
    tasks = session.sql(
        "SELECT DISTINCT task_key FROM shared.v_run_timeline ORDER BY task_key"
    ).to_pandas()
    if tasks.empty:
        st.info("No data yet.")
        st.stop()
    selected_task = st.selectbox("Task", tasks["TASK_KEY"].tolist())

with col2:
    runs = session.sql(
        f"""
        SELECT run_id, run_status, scheduled_time
        FROM shared.v_run_timeline
        WHERE task_key = '{selected_task}'
        ORDER BY scheduled_time DESC
        LIMIT 50
    """
    ).to_pandas()

    if runs.empty:
        st.info("No runs found for this task.")
        st.stop()

    run_options = runs.apply(
        lambda r: f"{r['RUN_ID']} — {r['RUN_STATUS']} @ {r['SCHEDULED_TIME']}", axis=1
    ).tolist()
    selected_run_label = st.selectbox("Run", run_options)
    selected_run_id = selected_run_label.split(" — ")[0]

st.divider()

# ── Run Summary ──
run_info = session.sql(
    f"""
    SELECT run_status, scheduled_time, duration_seconds,
           estimated_credits, rows_affected, error_message
    FROM shared.v_run_timeline
    WHERE task_key = '{selected_task}' AND run_id = '{selected_run_id}'
"""
).to_pandas()

if not run_info.empty:
    r = run_info.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    status_emoji = (
        "✅"
        if r["RUN_STATUS"] == "SUCCEEDED"
        else "❌"
        if r["RUN_STATUS"] == "FAILED"
        else "⏭️"
    )
    c1.metric("Status", f'{status_emoji} {r["RUN_STATUS"]}')
    c2.metric(
        "Duration (s)", f'{r["DURATION_SECONDS"]:.1f}' if r["DURATION_SECONDS"] else "N/A"
    )
    c3.metric(
        "Credits",
        f'{r["ESTIMATED_CREDITS"]:.4f}' if r["ESTIMATED_CREDITS"] else "0",
    )
    c4.metric("Rows Affected", r["ROWS_AFFECTED"] or 0)

    if r["RUN_STATUS"] == "FAILED" and r["ERROR_MESSAGE"]:
        st.error(f"**Error:** {r['ERROR_MESSAGE']}")

st.divider()

# ── Query Breakdown ──
st.subheader("🔎 Query Breakdown")

queries_df = session.sql(
    f"""
    SELECT
        query_id,
        query_type,
        execution_status,
        total_elapsed_time_ms,
        rows_produced,
        rows_inserted,
        rows_updated,
        rows_deleted,
        bytes_scanned,
        credits_used,
        query_text,
        error_message
    FROM core.run_query_details
    WHERE run_id = '{selected_run_id}' AND task_key = '{selected_task}'
    ORDER BY start_time
"""
).to_pandas()

if not queries_df.empty:
    st.dataframe(
        queries_df,
        column_config={
            "QUERY_ID": st.column_config.TextColumn("Query ID"),
            "QUERY_TYPE": st.column_config.TextColumn("Type"),
            "EXECUTION_STATUS": st.column_config.TextColumn("Status"),
            "TOTAL_ELAPSED_TIME_MS": st.column_config.NumberColumn("Time (ms)"),
            "ROWS_PRODUCED": st.column_config.NumberColumn("Produced"),
            "ROWS_INSERTED": st.column_config.NumberColumn("Inserted"),
            "ROWS_UPDATED": st.column_config.NumberColumn("Updated"),
            "ROWS_DELETED": st.column_config.NumberColumn("Deleted"),
            "BYTES_SCANNED": st.column_config.NumberColumn("Bytes Scanned"),
            "CREDITS_USED": st.column_config.NumberColumn(
                "Credits", format="%.6f"
            ),
            "QUERY_TEXT": st.column_config.TextColumn("SQL", width="large"),
            "ERROR_MESSAGE": st.column_config.TextColumn("Error", width="large"),
        },
        hide_index=True,
        use_container_width=True,
    )

    # ── Objects Read/Written (future lineage foundation) ──
    objects = session.sql(
        f"""
        SELECT query_id, objects_read, objects_written
        FROM core.run_query_details
        WHERE run_id = '{selected_run_id}' AND task_key = '{selected_task}'
          AND (objects_read IS NOT NULL OR objects_written IS NOT NULL)
    """
    ).to_pandas()

    if not objects.empty:
        st.divider()
        st.subheader("🗂️ Objects Read / Written")
        st.caption("Foundation for lineage mapping (v2)")
        st.dataframe(objects, hide_index=True, use_container_width=True)
else:
    st.info("No query details found for this run. Data may still be syncing.")

