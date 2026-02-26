import streamlit as st

from local_streamlit.session import get_session


st.set_page_config(page_title="Snowflake Pulse (Local)", page_icon="⚡", layout="wide")

session = get_session()

# ── Header ──
st.title("⚡ Snowflake Pulse — Local")
st.caption("Pipeline health at a glance (connected via Snowpark from your machine)")

# ── KPI Cards ──
overview = session.sql("SELECT * FROM shared.v_overview").collect()

if overview:
    row = overview[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Tasks", row["ACTIVE_TASKS"])
    c2.metric("Failed Runs (24h)", row["FAILED_RUNS_24H"], delta_color="inverse")
    c3.metric("Credits (24h)", f'{row["CREDITS_24H"]:.4f}')
    c4.metric(
        "Failure Rate (24h)",
        f'{row["FAILURE_RATE_24H"]:.1f}%' if row["FAILURE_RATE_24H"] else "0%",
        delta_color="inverse",
    )
else:
    st.info("No data yet. Make sure the collector task is running.")

st.divider()

# ── Task Summary Table ──
st.subheader("📋 Task Summary")

tasks_df = session.sql(
    """
    SELECT
        task_key,
        state,
        total_runs,
        succeeded,
        failed,
        avg_duration_sec,
        total_credits,
        last_run_time
    FROM shared.v_task_summary
    ORDER BY failed DESC, last_run_time DESC
"""
).to_pandas()

if not tasks_df.empty:
    st.dataframe(
        tasks_df,
        column_config={
            "task_key": st.column_config.TextColumn("Task", width="large"),
            "state": st.column_config.TextColumn("Status"),
            "total_runs": st.column_config.NumberColumn("Runs"),
            "succeeded": st.column_config.NumberColumn("✅"),
            "failed": st.column_config.NumberColumn("❌"),
            "avg_duration_sec": st.column_config.NumberColumn(
                "Avg Duration (s)", format="%.1f"
            ),
            "total_credits": st.column_config.NumberColumn(
                "Credits", format="%.4f"
            ),
            "last_run_time": st.column_config.DatetimeColumn(
                "Last Run", format="YYYY-MM-DD HH:mm"
            ),
        },
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No monitored tasks found yet.")

st.divider()

# ── Recent Failures ──
st.subheader("🔴 Recent Failures")

failures_df = session.sql(
    """
    SELECT task_key, run_id, error_message, scheduled_time, duration_seconds
    FROM shared.v_run_timeline
    WHERE run_status = 'FAILED'
    ORDER BY scheduled_time DESC
    LIMIT 25
"""
).to_pandas()

if not failures_df.empty:
    st.dataframe(
        failures_df,
        column_config={
            "task_key": st.column_config.TextColumn("Task", width="large"),
            "run_id": st.column_config.TextColumn("Run ID"),
            "error_message": st.column_config.TextColumn("Error", width="large"),
            "scheduled_time": st.column_config.DatetimeColumn(
                "Scheduled", format="YYYY-MM-DD HH:mm"
            ),
            "duration_seconds": st.column_config.NumberColumn("Duration (s)"),
        },
        hide_index=True,
        use_container_width=True,
    )
else:
    st.success("No failures in the monitored window.")

st.divider()
st.subheader("💰 Daily Credit Usage")

cost_df = session.sql(
    """
    SELECT run_date, SUM(estimated_credits) AS daily_credits, SUM(total_runs) AS daily_runs
    FROM shared.v_daily_costs
    GROUP BY run_date
    ORDER BY run_date
"""
).to_pandas()

if not cost_df.empty:
    st.line_chart(cost_df.set_index("RUN_DATE")[["DAILY_CREDITS"]])
else:
    st.info(
        "Cost data will appear after the collector runs for at least one day."
    )

