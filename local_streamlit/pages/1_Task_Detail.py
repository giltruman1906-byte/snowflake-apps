import streamlit as st

from local_streamlit.session import get_session


st.set_page_config(page_title="Task Detail | Pulse (Local)", page_icon="⚡", layout="wide")

session = get_session()

st.title("📊 Task Detail")

# ── Task Selector ──
tasks = session.sql(
    "SELECT task_key FROM shared.v_task_summary ORDER BY task_key"
).to_pandas()

if tasks.empty:
    st.info("No tasks found. Run the collector first.")
    st.stop()

selected_task = st.selectbox("Select a task", tasks["TASK_KEY"].tolist())

st.divider()

# ── Task Metadata ──
meta = session.sql(
    f"""
    SELECT * FROM shared.v_task_summary
    WHERE task_key = '{selected_task}'
"""
).to_pandas()

if not meta.empty:
    row = meta.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Runs", row["TOTAL_RUNS"])
    c2.metric("Succeeded", row["SUCCEEDED"])
    c3.metric("Failed", row["FAILED"])
    c4.metric("Avg Duration (s)", f'{row["AVG_DURATION_SEC"]:.1f}')
    c5.metric("Total Credits", f'{row["TOTAL_CREDITS"]:.4f}')

st.divider()

# ── Run History ──
st.subheader("🕐 Run History")

runs_df = session.sql(
    f"""
    SELECT run_id, run_status, scheduled_time, duration_seconds,
           estimated_credits, rows_affected, error_message
    FROM shared.v_run_timeline
    WHERE task_key = '{selected_task}'
    ORDER BY scheduled_time DESC
    LIMIT 100
"""
).to_pandas()

if not runs_df.empty:
    st.dataframe(
        runs_df,
        column_config={
            "run_id": st.column_config.TextColumn("Run ID"),
            "run_status": st.column_config.TextColumn("Status"),
            "scheduled_time": st.column_config.DatetimeColumn(
                "Scheduled", format="YYYY-MM-DD HH:mm"
            ),
            "duration_seconds": st.column_config.NumberColumn("Duration (s)"),
            "estimated_credits": st.column_config.NumberColumn(
                "Credits", format="%.4f"
            ),
            "rows_affected": st.column_config.NumberColumn("Rows Affected"),
            "error_message": st.column_config.TextColumn("Error", width="large"),
        },
        hide_index=True,
        use_container_width=True,
    )

    # ── Trend Charts ──
    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("⏱️ Duration Trend")
        duration_chart = runs_df[["SCHEDULED_TIME", "DURATION_SECONDS"]].dropna()
        if not duration_chart.empty:
            duration_chart = duration_chart.sort_values("SCHEDULED_TIME")
            st.line_chart(duration_chart.set_index("SCHEDULED_TIME"))

    with col_right:
        st.subheader("💰 Cost Trend")
        cost_chart = runs_df[["SCHEDULED_TIME", "ESTIMATED_CREDITS"]].dropna()
        if not cost_chart.empty:
            cost_chart = cost_chart.sort_values("SCHEDULED_TIME")
            st.line_chart(cost_chart.set_index("SCHEDULED_TIME"))

    st.divider()
    st.subheader("✅ Success vs Failure")
    status_counts = runs_df["RUN_STATUS"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]
    st.bar_chart(status_counts.set_index("Status"))

    st.divider()
    st.subheader("📦 Rows Processed Trend")
    rows_chart = runs_df[["SCHEDULED_TIME", "ROWS_AFFECTED"]].dropna()
    if not rows_chart.empty:
        rows_chart = rows_chart.sort_values("SCHEDULED_TIME")
        st.area_chart(rows_chart.set_index("SCHEDULED_TIME"))
else:
    st.info("No runs found for this task.")

