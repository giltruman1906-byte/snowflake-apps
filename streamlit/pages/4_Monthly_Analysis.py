# ─────────────────────────────────────────────
# Snowflake Pulse — Monthly Analysis
# ─────────────────────────────────────────────

import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Monthly Analysis | Pulse", page_icon="⚡", layout="wide")

session = get_active_session()

st.title("📅 Monthly Analysis")
st.caption("Month-over-month trends for cost, volume, and reliability — YTD")

# ── Fetch monthly trend data ──
monthly_df = session.sql("""
    SELECT * FROM shared.v_monthly_analysis ORDER BY month
""").to_pandas()

if monthly_df.empty:
    st.info("No data available yet for this year. The collector needs to run first.")
    st.stop()

# ── YTD Summary KPIs with MoM delta ──
ytd_credits = monthly_df["TOTAL_CREDITS"].sum()
ytd_runs = int(monthly_df["TOTAL_RUNS"].sum())
ytd_tasks = int(monthly_df["DISTINCT_TASKS"].max())
avg_failure = monthly_df["FAILURE_RATE_PCT"].mean()
avg_cpr = monthly_df["CREDITS_PER_RUN"].mean()

if len(monthly_df) >= 2:
    curr = monthly_df.iloc[-1]
    prev = monthly_df.iloc[-2]
    delta_credits = round(float(curr["TOTAL_CREDITS"] - prev["TOTAL_CREDITS"]), 4)
    delta_runs = int(curr["TOTAL_RUNS"] - prev["TOTAL_RUNS"])
    delta_tasks = int(curr["DISTINCT_TASKS"] - prev["DISTINCT_TASKS"])
    delta_failure = round(float(curr["FAILURE_RATE_PCT"] - prev["FAILURE_RATE_PCT"]), 2)
    delta_cpr = round(float(curr["CREDITS_PER_RUN"] - prev["CREDITS_PER_RUN"]), 6)
else:
    delta_credits = delta_runs = delta_tasks = delta_failure = delta_cpr = None

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "YTD Credits", f"{ytd_credits:.4f}",
    delta=f"{delta_credits:+.4f}" if delta_credits is not None else None,
    delta_color="inverse",
)
c2.metric(
    "YTD Runs", f"{ytd_runs:,}",
    delta=f"{delta_runs:+,}" if delta_runs is not None else None,
)
c3.metric(
    "Distinct Tasks", ytd_tasks,
    delta=f"{delta_tasks:+d}" if delta_tasks is not None else None,
)
c4.metric(
    "Avg Failure Rate", f"{avg_failure:.1f}%",
    delta=f"{delta_failure:+.1f}%" if delta_failure is not None else None,
    delta_color="inverse",
)
c5.metric(
    "Avg Cost/Run", f"{avg_cpr:.6f}",
    delta=f"{delta_cpr:+.6f}" if delta_cpr is not None else None,
    delta_color="inverse",
)

st.divider()

# ── Row 1: Total Credits + Distinct Tasks ──
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💰 Total Credits by Month")
    chart_credits = monthly_df[["MONTH", "TOTAL_CREDITS"]].copy()
    chart_credits["MONTH"] = chart_credits["MONTH"].astype(str)
    st.bar_chart(chart_credits.set_index("MONTH"))

with col_right:
    st.subheader("📊 Distinct Tasks by Month")
    chart_tasks = monthly_df[["MONTH", "DISTINCT_TASKS"]].copy()
    chart_tasks["MONTH"] = chart_tasks["MONTH"].astype(str)
    st.bar_chart(chart_tasks.set_index("MONTH"))

st.divider()

# ── Row 2: Cost per Task + Cost per Run ──
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💵 Cost per Task by Month")
    chart_cpt = monthly_df[["MONTH", "CREDITS_PER_TASK"]].copy()
    chart_cpt["MONTH"] = chart_cpt["MONTH"].astype(str)
    st.line_chart(chart_cpt.set_index("MONTH"))

with col_right:
    st.subheader("🔹 Cost per Run by Month")
    chart_cpr = monthly_df[["MONTH", "CREDITS_PER_RUN"]].copy()
    chart_cpr["MONTH"] = chart_cpr["MONTH"].astype(str)
    st.line_chart(chart_cpr.set_index("MONTH"))

st.divider()

# ── Row 3: Failure Rate + Avg Duration + Rows Affected ──
col_left, col_mid, col_right = st.columns(3)

with col_left:
    st.subheader("🔴 Failure Rate (%)")
    chart_fail = monthly_df[["MONTH", "FAILURE_RATE_PCT"]].copy()
    chart_fail["MONTH"] = chart_fail["MONTH"].astype(str)
    st.area_chart(chart_fail.set_index("MONTH"))

with col_mid:
    st.subheader("⏱️ Avg Duration (s)")
    chart_dur = monthly_df[["MONTH", "AVG_DURATION_SECONDS"]].copy()
    chart_dur["MONTH"] = chart_dur["MONTH"].astype(str)
    st.line_chart(chart_dur.set_index("MONTH"))

with col_right:
    st.subheader("📦 Rows Affected")
    chart_rows = monthly_df[["MONTH", "TOTAL_ROWS_AFFECTED"]].copy()
    chart_rows["MONTH"] = chart_rows["MONTH"].astype(str)
    st.bar_chart(chart_rows.set_index("MONTH"))

st.divider()

# ── Monthly Trend Table ──
st.subheader("📋 Monthly Trend Table")

trend_display = monthly_df.copy()
trend_display["MONTH"] = trend_display["MONTH"].astype(str)
trend_display = trend_display.rename(columns={
    "MONTH": "Month",
    "DISTINCT_TASKS": "Tasks",
    "TOTAL_RUNS": "Runs",
    "SUCCEEDED_RUNS": "Succeeded",
    "FAILED_RUNS": "Failed",
    "TOTAL_CREDITS": "Credits",
    "CREDITS_PER_TASK": "Credits/Task",
    "CREDITS_PER_RUN": "Credits/Run",
    "TOTAL_DURATION_SECONDS": "Total Duration (s)",
    "AVG_DURATION_SECONDS": "Avg Duration (s)",
    "FAILURE_RATE_PCT": "Failure Rate (%)",
    "TOTAL_ROWS_AFFECTED": "Rows Affected",
})
display_cols = [
    "Month", "Tasks", "Runs", "Succeeded", "Failed", "Failure Rate (%)",
    "Credits", "Credits/Task", "Credits/Run", "Avg Duration (s)", "Rows Affected",
]
st.dataframe(trend_display[display_cols], use_container_width=True)

st.divider()

# ── Per-Task Breakdown for Selected Month ──
st.subheader("🔍 Per-Task Breakdown")

month_options = monthly_df["MONTH"].astype(str).tolist()
selected_month = st.selectbox("Select a month", month_options, index=len(month_options) - 1)

task_breakdown_df = session.sql(f"""
    SELECT
        task_key,
        COUNT(*)                                             AS total_runs,
        COUNT_IF(run_status = 'SUCCEEDED')                   AS succeeded,
        COUNT_IF(run_status = 'FAILED')                      AS failed,
        ROUND(SUM(estimated_credits), 4)                     AS total_credits,
        ROUND(AVG(estimated_credits), 6)                     AS avg_credits_per_run,
        ROUND(SUM(duration_seconds), 2)                      AS total_duration_sec,
        ROUND(AVG(duration_seconds), 2)                      AS avg_duration_sec,
        SUM(rows_inserted + rows_updated + rows_deleted)     AS rows_affected
    FROM core.task_run_history
    WHERE DATE_TRUNC('MONTH', scheduled_time)::DATE = '{selected_month}'
    GROUP BY task_key
    ORDER BY total_credits DESC
""").to_pandas()

if not task_breakdown_df.empty:
    breakdown_display = task_breakdown_df.rename(columns={
        "TASK_KEY": "Task",
        "TOTAL_RUNS": "Runs",
        "SUCCEEDED": "Succeeded",
        "FAILED": "Failed",
        "TOTAL_CREDITS": "Credits",
        "AVG_CREDITS_PER_RUN": "Avg Credits/Run",
        "TOTAL_DURATION_SEC": "Total Duration (s)",
        "AVG_DURATION_SEC": "Avg Duration (s)",
        "ROWS_AFFECTED": "Rows Affected",
    })
    st.dataframe(breakdown_display, use_container_width=True)
else:
    st.info("No task runs found for this month.")
