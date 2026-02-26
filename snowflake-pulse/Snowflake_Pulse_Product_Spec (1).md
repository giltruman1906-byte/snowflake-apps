# Snowflake Pulse -- Product Specification

## 1. Overview

**Snowflake Pulse** is a Snowflake Native App designed to monitor
Snowflake TASK-based data pipelines for seed-stage startups.

It provides lightweight pipeline health visibility, cost estimation,
execution tracking, and Slack/Webhook alerts --- all running entirely
inside the customer's Snowflake account.

------------------------------------------------------------------------

## 2. Problem Statement

Seed-stage startups using Snowflake often:

-   Do not monitor TASK failures effectively
-   Discover issues only after dashboards break
-   Lack Slack/webhook alerting for pipeline failures
-   Cannot easily see cost per task run
-   Have limited visibility into pipeline performance trends

Enterprise monitoring tools are too expensive and complex for small
teams.

Snowflake Pulse solves this with a simple, focused monitoring solution.

------------------------------------------------------------------------

## 3. MVP Scope

### A. Task Monitoring

-   Map all existing TASKS
-   Track execution status (Success / Fail / Skipped)
-   Track execution duration
-   Track cadence (runs per hour/day)
-   Display last run time

### B. Drill-Down Per Task Run

For each run: - Status and error message - Queries executed - Rows
inserted / updated / deleted - Duration - Estimated credits used -
Warehouse used

### C. Cost Estimation

Estimate credits per run using: - Warehouse metering history - Query
execution time windows - Prorated allocation methodology

### D. Alerts

Slack/Webhook notifications when: - Task fails - Duration exceeds
threshold - Task misses scheduled execution

### E. Dashboard (Streamlit in Snowflake)

Pages include:

1.  Overview
    -   Active tasks
    -   Failed runs (last 24h)
    -   Estimated credits usage
    -   Failure rate
2.  Task Detail
    -   Run trends
    -   Success vs failure breakdown
    -   Cost trends
    -   Rows processed trends
3.  Run Detail
    -   Error messages
    -   Query breakdown
    -   Objects read/written (foundation for lineage)

------------------------------------------------------------------------

## 4. Technical Architecture

### Step 1 -- Metadata Collection

Data sources: - TASK history views - QUERY history views - Warehouse
metering views - Object access history (for future lineage)

### Step 2 -- Internal App Tables

The app stores: - Task definitions - Task run history - Query details
per run - Estimated cost per run - Rows affected - Objects read/written

### Step 3 -- Collector Engine

A Snowflake TASK runs every few minutes to: 1. Pull new task runs 2.
Link runs to executed queries 3. Estimate cost 4. Capture row counts 5.
Store results in app tables

### Step 4 -- UI Layer

Streamlit reads internal tables and renders: - KPI cards - Trend
charts - Drill-down tables

------------------------------------------------------------------------

## 5. Value Proposition

Snowflake Pulse:

-   Reduces debugging time
-   Surfaces hidden cost inefficiencies
-   Improves pipeline reliability
-   Provides affordable monitoring for startups
-   Creates foundation for future lineage mapping

------------------------------------------------------------------------

## 6. Out of Scope (MVP)

Not included in v1: - Full enterprise lineage graphs - Column-level
lineage - Cross-tool ingestion (dbt, Airflow, etc.) - Governance
framework - Perfect cost accounting

------------------------------------------------------------------------

## 7. Future Expansion (v2+)

Because the system captures query-to-object relationships, future
enhancements may include:

-   Automated lineage graph
-   Upstream/downstream dependency visualization
-   Anomaly detection models
-   Efficiency scoring
-   dbt metadata integration

------------------------------------------------------------------------

## 8. Strategic Positioning

Snowflake Pulse is:

> The simplest way to monitor Snowflake pipelines.

Lightweight. Affordable. Built for seed-stage teams.
