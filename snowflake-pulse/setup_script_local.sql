-- =============================================================================
-- SNOWFLAKE PULSE — Local Setup Script
-- =============================================================================
-- Adapted for local deployment (no Native App framework).
-- Run this with SYSADMIN role against the SANDBOX database.
-- =============================================================================

USE ROLE SYSADMIN;
USE DATABASE SANDBOX;
USE WAREHOUSE COMPUTE_WH;

-- ─────────────────────────────────────────────
-- 1. SCHEMAS
-- ─────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS SANDBOX.core;
COMMENT ON SCHEMA SANDBOX.core IS 'Internal app tables for pipeline monitoring data';

CREATE SCHEMA IF NOT EXISTS SANDBOX.config;
COMMENT ON SCHEMA SANDBOX.config IS 'Configuration and reference management';

CREATE SCHEMA IF NOT EXISTS SANDBOX.shared;
COMMENT ON SCHEMA SANDBOX.shared IS 'Dashboard views consumed by Streamlit';


-- ─────────────────────────────────────────────
-- 2. GRANT ACCESS TO ACCOUNT_USAGE
-- ─────────────────────────────────────────────
-- The collector reads from SNOWFLAKE.ACCOUNT_USAGE views.
-- SYSADMIN needs IMPORTED PRIVILEGES on the SNOWFLAKE database.

USE ROLE ACCOUNTADMIN;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE SYSADMIN;
USE ROLE SYSADMIN;


-- ─────────────────────────────────────────────
-- 3. CORE TABLES
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SANDBOX.core.monitored_tasks (
    task_key               VARCHAR(500)   NOT NULL,
    database_name          VARCHAR(255),
    schema_name            VARCHAR(255),
    task_name              VARCHAR(255),
    warehouse_name         VARCHAR(255),
    schedule               VARCHAR(500),
    predecessor_task_key   VARCHAR(500),
    state                  VARCHAR(50),
    is_root_task           BOOLEAN DEFAULT FALSE,
    first_seen_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    last_seen_at           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (task_key)
);

CREATE TABLE IF NOT EXISTS SANDBOX.core.task_run_history (
    run_id                 VARCHAR(100)   NOT NULL,
    task_key               VARCHAR(500)   NOT NULL,
    query_id               VARCHAR(100),
    run_status             VARCHAR(50),
    error_code             VARCHAR(20),
    error_message          VARCHAR(10000),
    scheduled_time         TIMESTAMP_LTZ,
    query_start_time       TIMESTAMP_LTZ,
    completed_time         TIMESTAMP_LTZ,
    duration_seconds       NUMBER(12,2),
    warehouse_name         VARCHAR(255),
    estimated_credits      NUMBER(12,6)   DEFAULT 0,
    rows_inserted          NUMBER(18,0)   DEFAULT 0,
    rows_updated           NUMBER(18,0)   DEFAULT 0,
    rows_deleted           NUMBER(18,0)   DEFAULT 0,
    rows_produced          NUMBER(18,0)   DEFAULT 0,
    bytes_scanned          NUMBER(18,0)   DEFAULT 0,
    collected_at           TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (run_id, task_key)
);

CREATE TABLE IF NOT EXISTS SANDBOX.core.run_query_details (
    query_id               VARCHAR(100)   NOT NULL,
    run_id                 VARCHAR(100),
    task_key               VARCHAR(500),
    query_text             VARCHAR(100000),
    query_type             VARCHAR(100),
    execution_status       VARCHAR(50),
    error_message          VARCHAR(10000),
    start_time             TIMESTAMP_LTZ,
    end_time               TIMESTAMP_LTZ,
    total_elapsed_time_ms  NUMBER(18,0),
    rows_produced          NUMBER(18,0),
    rows_inserted          NUMBER(18,0),
    rows_updated           NUMBER(18,0),
    rows_deleted           NUMBER(18,0),
    bytes_scanned          NUMBER(18,0),
    credits_used           NUMBER(12,6),
    warehouse_name         VARCHAR(255),
    objects_read           VARIANT,
    objects_written        VARIANT,
    collected_at           TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (query_id)
);

CREATE TABLE IF NOT EXISTS SANDBOX.core.cost_estimates (
    task_key               VARCHAR(500)   NOT NULL,
    run_date               DATE           NOT NULL,
    total_runs             NUMBER(10,0),
    total_duration_seconds NUMBER(12,2),
    estimated_credits      NUMBER(12,6),
    avg_credits_per_run    NUMBER(12,6),
    PRIMARY KEY (task_key, run_date)
);

CREATE TABLE IF NOT EXISTS SANDBOX.core.alert_config (
    alert_id               NUMBER AUTOINCREMENT,
    alert_type             VARCHAR(50)    NOT NULL,
    task_key               VARCHAR(500),
    threshold_seconds      NUMBER(12,0),
    slack_webhook_url      VARCHAR(2000),
    generic_webhook_url    VARCHAR(2000),
    is_enabled             BOOLEAN        DEFAULT TRUE,
    created_at             TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    updated_at             TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (alert_id)
);

CREATE TABLE IF NOT EXISTS SANDBOX.core.alert_log (
    log_id                 NUMBER AUTOINCREMENT,
    alert_id               NUMBER,
    task_key               VARCHAR(500),
    run_id                 VARCHAR(100),
    alert_type             VARCHAR(50),
    message                VARCHAR(5000),
    channel                VARCHAR(20),
    http_status_code       NUMBER(5,0),
    sent_at                TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (log_id)
);

CREATE TABLE IF NOT EXISTS SANDBOX.core.collector_state (
    state_key              VARCHAR(100)   NOT NULL DEFAULT 'LAST_RUN',
    last_collected_at      TIMESTAMP_LTZ,
    updated_at             TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (state_key)
);

INSERT INTO SANDBOX.core.collector_state (state_key, last_collected_at)
    SELECT 'LAST_RUN', DATEADD('day', -7, CURRENT_TIMESTAMP())
    WHERE NOT EXISTS (SELECT 1 FROM SANDBOX.core.collector_state WHERE state_key = 'LAST_RUN');


-- ─────────────────────────────────────────────
-- 4. COLLECTOR PROCEDURE
-- ─────────────────────────────────────────────
-- Uses direct SNOWFLAKE.ACCOUNT_USAGE references instead of REFERENCE().

CREATE OR REPLACE PROCEDURE SANDBOX.core.collect_task_runs()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    v_watermark TIMESTAMP_LTZ;
    v_rows_collected NUMBER DEFAULT 0;
BEGIN
    -- Get watermark
    SELECT last_collected_at INTO v_watermark
    FROM SANDBOX.core.collector_state
    WHERE state_key = 'LAST_RUN';

    -- Step 1: Upsert monitored tasks
    -- Note: TASK_HISTORY only has run data, not task metadata like
    -- warehouse/schedule/predecessors. We get those from QUERY_HISTORY later.
    MERGE INTO SANDBOX.core.monitored_tasks tgt
    USING (
        SELECT
            database_name || '.' || schema_name || '.' || name AS task_key,
            database_name,
            schema_name,
            name AS task_name
        FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
        WHERE scheduled_time > :v_watermark
          AND database_name IS NOT NULL
          AND schema_name   IS NOT NULL
          AND name          IS NOT NULL
        GROUP BY database_name, schema_name, name
    ) src
    ON tgt.task_key = src.task_key
    WHEN MATCHED THEN UPDATE SET
        tgt.state        = 'active',
        tgt.last_seen_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (
        task_key, database_name, schema_name, task_name, state
    ) VALUES (
        src.task_key, src.database_name, src.schema_name, src.task_name, 'active'
    );

    -- Step 2: Insert new task runs
    -- warehouse_name is backfilled in Step 4 from QUERY_HISTORY data.
    -- Uses LEFT JOIN anti-pattern instead of NOT EXISTS (unsupported on ACCOUNT_USAGE).
    INSERT INTO SANDBOX.core.task_run_history (
        run_id, task_key, query_id, run_status,
        error_code, error_message,
        scheduled_time, query_start_time, completed_time, duration_seconds
    )
    SELECT
        COALESCE(th.graph_run_group_id::VARCHAR, th.run_id::VARCHAR)  AS run_id,
        th.database_name || '.' || th.schema_name || '.' || th.name AS task_key,
        th.query_id,
        th.state                                           AS run_status,
        th.error_code,
        th.error_message,
        th.scheduled_time,
        th.query_start_time,
        th.completed_time,
        DATEDIFF('second', th.query_start_time, th.completed_time) AS duration_seconds
    FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY th
    LEFT JOIN SANDBOX.core.task_run_history r
        ON r.run_id  = COALESCE(th.graph_run_group_id::VARCHAR, th.run_id::VARCHAR)
       AND r.task_key = th.database_name || '.' || th.schema_name || '.' || th.name
    WHERE th.scheduled_time > :v_watermark
      AND th.state IN ('SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')
      AND th.database_name IS NOT NULL
      AND th.schema_name   IS NOT NULL
      AND th.name          IS NOT NULL
      AND r.run_id IS NULL;

    v_rows_collected := SQLROWCOUNT;

    -- Step 3: Enrich with query details
    INSERT INTO SANDBOX.core.run_query_details (
        query_id, run_id, task_key, query_text, query_type,
        execution_status, error_message,
        start_time, end_time, total_elapsed_time_ms,
        rows_produced, rows_inserted, rows_updated, rows_deleted,
        bytes_scanned, credits_used, warehouse_name
    )
    SELECT
        qh.query_id,
        rh.run_id,
        rh.task_key,
        qh.query_text,
        qh.query_type,
        qh.execution_status,
        qh.error_message,
        qh.start_time,
        qh.end_time,
        qh.total_elapsed_time,
        qh.rows_produced,
        qh.rows_inserted,
        qh.rows_updated,
        qh.rows_deleted,
        qh.bytes_scanned,
        qh.credits_used_cloud_services,
        qh.warehouse_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh
    INNER JOIN SANDBOX.core.task_run_history rh
        ON qh.query_id = rh.query_id
    WHERE rh.collected_at > DATEADD('minute', -10, CURRENT_TIMESTAMP())
      AND NOT EXISTS (
          SELECT 1 FROM SANDBOX.core.run_query_details d WHERE d.query_id = qh.query_id
      );

    -- Step 4: Estimate cost per run + backfill warehouse_name from query details
    UPDATE SANDBOX.core.task_run_history rh
    SET estimated_credits = sub.est_credits,
        rows_inserted     = sub.total_inserted,
        rows_updated      = sub.total_updated,
        rows_deleted      = sub.total_deleted,
        rows_produced     = sub.total_produced,
        bytes_scanned     = sub.total_bytes,
        warehouse_name    = sub.wh_name
    FROM (
        SELECT
            run_id,
            task_key,
            SUM(credits_used)    AS est_credits,
            SUM(rows_inserted)   AS total_inserted,
            SUM(rows_updated)    AS total_updated,
            SUM(rows_deleted)    AS total_deleted,
            SUM(rows_produced)   AS total_produced,
            SUM(bytes_scanned)   AS total_bytes,
            MAX(warehouse_name)  AS wh_name
        FROM SANDBOX.core.run_query_details
        WHERE collected_at > DATEADD('minute', -10, CURRENT_TIMESTAMP())
        GROUP BY run_id, task_key
    ) sub
    WHERE rh.run_id = sub.run_id
      AND rh.task_key = sub.task_key;

    -- Step 4b: Backfill warehouse_name on monitored_tasks from run data
    UPDATE SANDBOX.core.monitored_tasks mt
    SET warehouse_name = sub.wh_name
    FROM (
        SELECT task_key, MAX(warehouse_name) AS wh_name
        FROM SANDBOX.core.task_run_history
        WHERE warehouse_name IS NOT NULL
        GROUP BY task_key
    ) sub
    WHERE mt.task_key = sub.task_key
      AND mt.warehouse_name IS NULL;

    -- Step 5: Aggregate daily cost estimates
    MERGE INTO SANDBOX.core.cost_estimates tgt
    USING (
        SELECT
            task_key,
            scheduled_time::DATE AS run_date,
            COUNT(*)             AS total_runs,
            SUM(duration_seconds)  AS total_duration_seconds,
            SUM(estimated_credits) AS estimated_credits,
            AVG(estimated_credits) AS avg_credits_per_run
        FROM SANDBOX.core.task_run_history
        WHERE scheduled_time::DATE >= DATEADD('day', -1, CURRENT_DATE())
        GROUP BY task_key, scheduled_time::DATE
    ) src
    ON tgt.task_key = src.task_key AND tgt.run_date = src.run_date
    WHEN MATCHED THEN UPDATE SET
        tgt.total_runs             = src.total_runs,
        tgt.total_duration_seconds = src.total_duration_seconds,
        tgt.estimated_credits      = src.estimated_credits,
        tgt.avg_credits_per_run    = src.avg_credits_per_run
    WHEN NOT MATCHED THEN INSERT VALUES (
        src.task_key, src.run_date, src.total_runs,
        src.total_duration_seconds, src.estimated_credits, src.avg_credits_per_run
    );

    -- Step 6: Update watermark
    UPDATE SANDBOX.core.collector_state
    SET last_collected_at = CURRENT_TIMESTAMP(),
        updated_at        = CURRENT_TIMESTAMP()
    WHERE state_key = 'LAST_RUN';

    RETURN 'Collected ' || v_rows_collected || ' new task runs';
END;
$$;


-- ─────────────────────────────────────────────
-- 5. ALERT PROCEDURE
-- ─────────────────────────────────────────────
-- Slack alerts require an external access integration.
-- If you don't have one set up yet, skip this section and
-- add alerts later.

-- Uncomment and configure if you have an external access integration:
-- CREATE OR REPLACE NETWORK RULE pulse_slack_rule
--     MODE = EGRESS
--     TYPE = HOST_PORT
--     VALUE_LIST = ('hooks.slack.com:443');
--
-- CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pulse_slack_access
--     ALLOWED_NETWORK_RULES = (pulse_slack_rule)
--     ENABLED = TRUE;

CREATE OR REPLACE PROCEDURE SANDBOX.core.check_and_send_alerts()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
-- If you set up the external access integration above, uncomment:
-- EXTERNAL_ACCESS_INTEGRATIONS = (pulse_slack_access)
AS
$$
import json
import requests
from snowflake.snowpark import Session

def run(session: Session) -> str:
    alerts_sent = 0

    alerts_df = session.sql("""
        SELECT alert_id, alert_type, task_key, threshold_seconds,
               slack_webhook_url, generic_webhook_url
        FROM SANDBOX.core.alert_config
        WHERE is_enabled = TRUE
    """).collect()

    for alert in alerts_df:
        alert_id    = alert['ALERT_ID']
        alert_type  = alert['ALERT_TYPE']
        task_filter = alert['TASK_KEY']
        threshold   = alert['THRESHOLD_SECONDS']
        slack_url   = alert['SLACK_WEBHOOK_URL']
        webhook_url = alert['GENERIC_WEBHOOK_URL']

        triggered_runs = []

        if alert_type == 'TASK_FAILURE':
            query = """
                SELECT run_id, task_key, error_message, completed_time
                FROM SANDBOX.core.task_run_history
                WHERE run_status = 'FAILED'
                  AND completed_time > DATEADD('minute', -6, CURRENT_TIMESTAMP())
            """
            if task_filter:
                query += f" AND task_key = '{task_filter}'"
            triggered_runs = session.sql(query).collect()

        elif alert_type == 'DURATION_EXCEEDED' and threshold:
            query = f"""
                SELECT run_id, task_key, duration_seconds, completed_time
                FROM SANDBOX.core.task_run_history
                WHERE duration_seconds > {threshold}
                  AND completed_time > DATEADD('minute', -6, CURRENT_TIMESTAMP())
                  AND run_status = 'SUCCEEDED'
            """
            if task_filter:
                query += f" AND task_key = '{task_filter}'"
            triggered_runs = session.sql(query).collect()

        elif alert_type == 'MISSED_SCHEDULE':
            query = """
                SELECT DISTINCT task_key
                FROM SANDBOX.core.monitored_tasks
                WHERE state = 'started'
                  AND task_key NOT IN (
                      SELECT DISTINCT task_key
                      FROM SANDBOX.core.task_run_history
                      WHERE scheduled_time > DATEADD('hour', -2, CURRENT_TIMESTAMP())
                  )
            """
            if task_filter:
                query += f" AND task_key = '{task_filter}'"
            triggered_runs = session.sql(query).collect()

        for run in triggered_runs:
            task_key = run['TASK_KEY']
            run_id = run.get('RUN_ID', 'N/A')

            dup_check = session.sql(f"""
                SELECT 1 FROM SANDBOX.core.alert_log
                WHERE alert_id = {alert_id}
                  AND run_id = '{run_id}'
                  AND task_key = '{task_key}'
            """).collect()
            if dup_check:
                continue

            message = _build_message(alert_type, run)
            status_code = 0

            if slack_url:
                status_code = _send_slack(slack_url, message)
                _log_alert(session, alert_id, task_key, run_id, alert_type, message, 'SLACK', status_code)
                alerts_sent += 1

            if webhook_url:
                status_code = _send_webhook(webhook_url, alert_type, run)
                _log_alert(session, alert_id, task_key, run_id, alert_type, message, 'WEBHOOK', status_code)
                alerts_sent += 1

    return f"Alerts sent: {alerts_sent}"


def _build_message(alert_type, run):
    task_key = run['TASK_KEY']
    if alert_type == 'TASK_FAILURE':
        error = run.get('ERROR_MESSAGE', 'Unknown error')
        return f"Task Failed: {task_key}\nError: {error[:500]}"
    elif alert_type == 'DURATION_EXCEEDED':
        dur = run.get('DURATION_SECONDS', 0)
        return f"Slow Task: {task_key}\nDuration: {dur}s"
    elif alert_type == 'MISSED_SCHEDULE':
        return f"Missed Schedule: {task_key} has not run in the last 2 hours"
    return f"Alert for {task_key}"


def _send_slack(webhook_url, message):
    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=10)
        return resp.status_code
    except Exception:
        return 0


def _send_webhook(webhook_url, alert_type, run):
    try:
        payload = {"alert_type": alert_type, "task_key": run['TASK_KEY']}
        payload.update({k.lower(): str(v) for k, v in run.asDict().items()})
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code
    except Exception:
        return 0


def _log_alert(session, alert_id, task_key, run_id, alert_type, message, channel, status_code):
    safe_msg = message.replace("'", "''")[:2000]
    session.sql(f"""
        INSERT INTO SANDBOX.core.alert_log (alert_id, task_key, run_id, alert_type, message, channel, http_status_code)
        VALUES ({alert_id}, '{task_key}', '{run_id}', '{alert_type}', '{safe_msg}', '{channel}', {status_code})
    """).collect()
$$;


-- ─────────────────────────────────────────────
-- 6. COLLECTOR TASK (runs every 5 minutes)
-- ─────────────────────────────────────────────
-- Uses COMPUTE_WH instead of serverless managed warehouse.

CREATE OR REPLACE TASK SANDBOX.core.pulse_collector_task
    WAREHOUSE = COMPUTE_WH
    SCHEDULE  = '5 MINUTE'
    ALLOW_OVERLAPPING_EXECUTION = FALSE
AS
    CALL SANDBOX.core.collect_task_runs();


CREATE OR REPLACE TASK SANDBOX.core.pulse_alert_task
    WAREHOUSE = COMPUTE_WH
    AFTER SANDBOX.core.pulse_collector_task
AS
    CALL SANDBOX.core.check_and_send_alerts();


-- ─────────────────────────────────────────────
-- 7. DASHBOARD VIEWS (for Streamlit)
-- ─────────────────────────────────────────────

CREATE OR REPLACE VIEW SANDBOX.shared.v_overview AS
SELECT
    (SELECT COUNT(DISTINCT task_key) FROM SANDBOX.core.monitored_tasks WHERE state = 'started')    AS active_tasks,
    (SELECT COUNT(*) FROM SANDBOX.core.task_run_history
     WHERE run_status = 'FAILED' AND scheduled_time > DATEADD('hour', -24, CURRENT_TIMESTAMP())) AS failed_runs_24h,
    (SELECT COALESCE(SUM(estimated_credits), 0) FROM SANDBOX.core.task_run_history
     WHERE scheduled_time > DATEADD('hour', -24, CURRENT_TIMESTAMP()))                     AS credits_24h,
    (SELECT ROUND(
        COUNT_IF(run_status = 'FAILED') * 100.0 / NULLIF(COUNT(*), 0), 2
     ) FROM SANDBOX.core.task_run_history
     WHERE scheduled_time > DATEADD('hour', -24, CURRENT_TIMESTAMP()))                     AS failure_rate_24h;


CREATE OR REPLACE VIEW SANDBOX.shared.v_task_summary AS
SELECT
    mt.task_key,
    mt.database_name,
    mt.schema_name,
    mt.task_name,
    mt.warehouse_name,
    mt.schedule,
    mt.state,
    mt.is_root_task,
    COUNT(rh.run_id)                                          AS total_runs,
    COUNT_IF(rh.run_status = 'SUCCEEDED')                     AS succeeded,
    COUNT_IF(rh.run_status = 'FAILED')                        AS failed,
    ROUND(AVG(rh.duration_seconds), 2)                        AS avg_duration_sec,
    ROUND(SUM(rh.estimated_credits), 4)                       AS total_credits,
    MAX(rh.scheduled_time)                                    AS last_run_time
FROM SANDBOX.core.monitored_tasks mt
LEFT JOIN SANDBOX.core.task_run_history rh ON mt.task_key = rh.task_key
GROUP BY mt.task_key, mt.database_name, mt.schema_name, mt.task_name,
         mt.warehouse_name, mt.schedule, mt.state, mt.is_root_task;


CREATE OR REPLACE VIEW SANDBOX.shared.v_run_timeline AS
SELECT
    task_key,
    run_id,
    run_status,
    scheduled_time,
    duration_seconds,
    estimated_credits,
    rows_inserted + rows_updated + rows_deleted AS rows_affected,
    error_message
FROM SANDBOX.core.task_run_history
ORDER BY scheduled_time DESC;


CREATE OR REPLACE VIEW SANDBOX.shared.v_daily_costs AS
SELECT
    task_key,
    run_date,
    total_runs,
    total_duration_seconds,
    estimated_credits,
    avg_credits_per_run
FROM SANDBOX.core.cost_estimates
ORDER BY run_date DESC;


CREATE OR REPLACE VIEW SANDBOX.shared.v_monthly_analysis AS
SELECT
    DATE_TRUNC('MONTH', scheduled_time)::DATE                                              AS month,
    COUNT(DISTINCT task_key)                                                                AS distinct_tasks,
    COUNT(*)                                                                                AS total_runs,
    COUNT_IF(run_status = 'SUCCEEDED')                                                      AS succeeded_runs,
    COUNT_IF(run_status = 'FAILED')                                                         AS failed_runs,
    ROUND(SUM(estimated_credits), 4)                                                        AS total_credits,
    ROUND(SUM(estimated_credits) / NULLIF(COUNT(DISTINCT task_key), 0), 4)                  AS credits_per_task,
    ROUND(SUM(estimated_credits) / NULLIF(COUNT(*), 0), 6)                                  AS credits_per_run,
    ROUND(SUM(duration_seconds), 2)                                                         AS total_duration_seconds,
    ROUND(AVG(duration_seconds), 2)                                                         AS avg_duration_seconds,
    ROUND(COUNT_IF(run_status = 'FAILED') * 100.0 / NULLIF(COUNT(*), 0), 2)                 AS failure_rate_pct,
    SUM(rows_inserted + rows_updated + rows_deleted)                                        AS total_rows_affected
FROM SANDBOX.core.task_run_history
WHERE scheduled_time >= DATE_TRUNC('YEAR', CURRENT_DATE())
GROUP BY DATE_TRUNC('MONTH', scheduled_time)::DATE
ORDER BY month;


-- ─────────────────────────────────────────────
-- 8. ACTIVATE TASKS
-- ─────────────────────────────────────────────
-- Resume child task first, then root task.

ALTER TASK SANDBOX.core.pulse_alert_task RESUME;
ALTER TASK SANDBOX.core.pulse_collector_task RESUME;
