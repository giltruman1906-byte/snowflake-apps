# Snowflake Pulse — Native App

> ⚡ The simplest way to monitor Snowflake pipelines.

Lightweight task monitoring, cost estimation, and Slack alerts — running entirely inside your Snowflake account.

## Project Structure

```
snowflake-pulse/
├── manifest.yml                 # Native App manifest
├── setup_script.sql             # Runs on app install — creates everything
├── streamlit/
│   ├── Home.py                  # Overview dashboard (KPIs, task table, failures)
│   └── pages/
│       ├── 1_Task_Detail.py     # Per-task drill-down with trend charts
│       ├── 2_Run_Detail.py      # Per-run query breakdown
│       └── 3_Settings.py        # Alert config + webhook setup
└── README.md
```

## Quick Start

### 1. Create the Application Package

```sql
USE ROLE ACCOUNTADMIN;

CREATE APPLICATION PACKAGE IF NOT EXISTS snowflake_pulse_pkg;
USE APPLICATION PACKAGE snowflake_pulse_pkg;
CREATE SCHEMA IF NOT EXISTS stage_content;
CREATE OR REPLACE STAGE stage_content.pulse_stage
  FILE_FORMAT = (TYPE = 'CSV' FIELD_OPTIONALLY_ENCLOSED_BY = '"');
```

### 2. Upload all files

```bash
# From the project root directory
snowsql -q "
PUT file://manifest.yml         @snowflake_pulse_pkg.stage_content.pulse_stage/ OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
PUT file://setup_script.sql     @snowflake_pulse_pkg.stage_content.pulse_stage/ OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
PUT file://streamlit/Home.py    @snowflake_pulse_pkg.stage_content.pulse_stage/streamlit/ OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
PUT file://streamlit/pages/*.py @snowflake_pulse_pkg.stage_content.pulse_stage/streamlit/pages/ OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
"
```

### 3. Create a version and install

```sql
ALTER APPLICATION PACKAGE snowflake_pulse_pkg
  ADD VERSION v1 USING '@snowflake_pulse_pkg.stage_content.pulse_stage';

-- Install the app
CREATE APPLICATION snowflake_pulse
  FROM APPLICATION PACKAGE snowflake_pulse_pkg
  USING VERSION v1;
```

### 4. Grant references the app needs

```sql
-- Grant access to account usage views
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION snowflake_pulse;
```

### 5. Resume the collector tasks

```sql
-- Child first, then root
ALTER TASK snowflake_pulse.core.pulse_alert_task RESUME;
ALTER TASK snowflake_pulse.core.pulse_collector_task RESUME;
```

### 6. Set up Slack alerts (optional)

Create an external access integration for Slack:

```sql
CREATE OR REPLACE NETWORK RULE pulse_slack_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('hooks.slack.com');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pulse_slack_integration
  ALLOWED_NETWORK_RULES = (pulse_slack_rule)
  ENABLED = TRUE;

-- Register it with the app
CALL snowflake_pulse.config.register_reference(
  'slack_external_access', 'ADD', 'pulse_slack_integration'
);
```

Then add your webhook URL on the **Settings** page in the Streamlit UI.

---

## What It Monitors

| Feature | Description |
|---------|-------------|
| **Task Mapping** | Auto-discovers all TASKs across your account |
| **Run Tracking** | Success / Fail / Skipped with duration and timestamps |
| **Cost Estimation** | Credits per run via warehouse metering proration |
| **Query Details** | Full query breakdown per task run |
| **Row Counts** | Rows inserted / updated / deleted per run |
| **Slack Alerts** | Failures, slow runs, missed schedules |
| **Webhook Alerts** | Generic HTTP POST for any integration |

## Architecture

```
ACCOUNT_USAGE views ──▶ Collector Task (5 min) ──▶ Core Tables ──▶ Streamlit UI
                                                        │
                                                        ▼
                                                   Alert Engine ──▶ Slack / Webhook
```

## Out of Scope (v1)

- Full lineage graphs (foundation is captured — `objects_read`/`objects_written`)
- dbt / Airflow metadata integration
- Column-level lineage
- Anomaly detection

## Roadmap (v2+)

- Automated lineage graph visualization
- Upstream/downstream dependency mapping
- Anomaly detection on duration and row counts
- dbt metadata integration
- Efficiency scoring per task
