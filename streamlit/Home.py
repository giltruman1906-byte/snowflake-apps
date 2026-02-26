# ─────────────────────────────────────────────
# Snowflake Pulse — Home / Overview Dashboard
# ─────────────────────────────────────────────

import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Snowflake Pulse", page_icon="⚡", layout="wide")

session = get_active_session()

# ── Header ──
st.title("⚡ Snowflake Pulse")
st.caption("Pipeline health at a glance")

# ── KPI Cards ──
overview = session.sql("SELECT * FROM shared.v_overview").collect()

if overview:
    row = overview[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Tasks",      row["ACTIVE_TASKS"])
    c2.metric("Failed Runs (24h)", row["FAILED_RUNS_24H"],  delta_color="inverse")
    c3.metric("Credits (24h)",     f'{row["CREDITS_24H"]:.4f}')
    c4.metric("Failure Rate (24h)", f'{row["FAILURE_RATE_24H"]:.1f}%' if row["FAILURE_RATE_24H"] else "0%",
              delta_color="inverse")
else:
    st.info("No data yet. Make sure the collector task is running.")

st.divider()

# ── Task Summary Table ──
st.subheader("📋 Task Summary")

tasks_df = session.sql("""
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
""").to_pandas()

if not tasks_df.empty:
    tasks_display = tasks_df.rename(columns={
        "TASK_KEY": "Task",
        "STATE": "Status",
        "TOTAL_RUNS": "Runs",
        "SUCCEEDED": "Succeeded",
        "FAILED": "Failed",
        "AVG_DURATION_SEC": "Avg Duration (s)",
        "TOTAL_CREDITS": "Credits",
        "LAST_RUN_TIME": "Last Run",
    })
    st.dataframe(tasks_display, use_container_width=True)
else:
    st.info("No monitored tasks found yet.")

st.divider()

# ── Recent Failures ──
st.subheader("🔴 Recent Failures")

failures_df = session.sql("""
    SELECT task_key, run_id, error_message, scheduled_time, duration_seconds
    FROM shared.v_run_timeline
    WHERE run_status = 'FAILED'
    ORDER BY scheduled_time DESC
    LIMIT 25
""").to_pandas()

if not failures_df.empty:
    failures_display = failures_df.rename(columns={
        "TASK_KEY": "Task",
        "RUN_ID": "Run ID",
        "ERROR_MESSAGE": "Error",
        "SCHEDULED_TIME": "Scheduled",
        "DURATION_SECONDS": "Duration (s)",
    })
    st.dataframe(failures_display, use_container_width=True)
else:
    st.success("No failures in the monitored window. 🎉")

# ── Credits Trend ──
st.divider()
st.subheader("💰 Daily Credit Usage")

cost_df = session.sql("""
    SELECT run_date, SUM(estimated_credits) AS daily_credits, SUM(total_runs) AS daily_runs
    FROM shared.v_daily_costs
    GROUP BY run_date
    ORDER BY run_date
""").to_pandas()

if not cost_df.empty:
    st.line_chart(cost_df.set_index("RUN_DATE")[["DAILY_CREDITS"]])
else:
    st.info("Cost data will appear after the collector runs for at least one day.")
