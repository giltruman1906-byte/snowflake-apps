import streamlit as st

from local_streamlit.session import get_session


st.set_page_config(page_title="Settings | Pulse (Local)", page_icon="⚡", layout="wide")

session = get_session()

st.title("⚙️ Settings")

# ── Collector Status ──
st.subheader("🔄 Collector Status")

collector_state = session.sql(
    """
    SELECT last_collected_at, updated_at
    FROM core.collector_state
    WHERE state_key = 'LAST_RUN'
"""
).to_pandas()

if not collector_state.empty:
    r = collector_state.iloc[0]
    c1, c2 = st.columns(2)
    c1.metric("Last Collection", str(r["LAST_COLLECTED_AT"]))
    c2.metric("Updated At", str(r["UPDATED_AT"]))
else:
    st.warning("Collector has never run.")

st.caption(
    """
**To activate the collector in your Snowflake account**, run these SQL commands with an admin role:
```sql
ALTER TASK core.pulse_alert_task RESUME;    -- resume child first
ALTER TASK core.pulse_collector_task RESUME; -- then resume root
```
"""
)

st.divider()

# ── Alert Configuration ──
st.subheader("🔔 Alert Rules")

alerts_df = session.sql(
    """
    SELECT alert_id, alert_type, task_key, threshold_seconds,
           slack_webhook_url, generic_webhook_url, is_enabled
    FROM core.alert_config
    ORDER BY alert_id
"""
).to_pandas()

if not alerts_df.empty:
    st.dataframe(alerts_df, hide_index=True, use_container_width=True)
else:
    st.info("No alert rules configured yet. Add one below.")

st.divider()

# ── Add Alert Rule ──
st.subheader("➕ Add Alert Rule")

with st.form("add_alert"):
    col1, col2 = st.columns(2)

    with col1:
        alert_type = st.selectbox(
            "Alert Type",
            ["TASK_FAILURE", "DURATION_EXCEEDED", "MISSED_SCHEDULE"],
        )

        task_key = st.text_input(
            "Task Key (leave empty for all tasks)",
            placeholder="DB.SCHEMA.TASK_NAME",
        )

        threshold = st.number_input(
            "Duration Threshold (seconds)",
            min_value=0,
            value=300,
            help="Only used for DURATION_EXCEEDED alerts",
        )

    with col2:
        slack_url = st.text_input(
            "Slack Webhook URL",
            placeholder="https://hooks.slack.com/services/...",
        )

        webhook_url = st.text_input(
            "Generic Webhook URL (optional)",
            placeholder="https://your-endpoint.com/webhook",
        )

        is_enabled = st.checkbox("Enabled", value=True)

    submitted = st.form_submit_button("Add Alert Rule", type="primary")

    if submitted:
        task_key_val = f"'{task_key}'" if task_key else "NULL"
        slack_val = f"'{slack_url}'" if slack_url else "NULL"
        webhook_val = f"'{webhook_url}'" if webhook_url else "NULL"
        threshold_val = threshold if alert_type == "DURATION_EXCEEDED" else "NULL"

        session.sql(
            f"""
            INSERT INTO core.alert_config
                (alert_type, task_key, threshold_seconds, slack_webhook_url, generic_webhook_url, is_enabled)
            VALUES
                ('{alert_type}', {task_key_val}, {threshold_val}, {slack_val}, {webhook_val}, {is_enabled})
        """
        ).collect()

        st.success(f"Alert rule added: {alert_type}")
        st.rerun()

st.divider()

# ── Alert History ──
st.subheader("📜 Alert History")

alert_log_df = session.sql(
    """
    SELECT alert_type, task_key, run_id, channel,
           http_status_code, message, sent_at
    FROM core.alert_log
    ORDER BY sent_at DESC
    LIMIT 50
"""
).to_pandas()

if not alert_log_df.empty:
    st.dataframe(alert_log_df, hide_index=True, use_container_width=True)
else:
    st.info("No alerts have been sent yet.")

