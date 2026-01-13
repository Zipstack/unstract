# Dashboard Metrics Module

This module provides a metrics dashboard for monitoring document processing, API usage, and LLM costs. It aggregates data from various source tables into pre-computed hourly, daily, and monthly tables for fast querying.

---

## Quick Reference (TL;DR)

### What It Does
- Tracks **9 metrics**: documents processed, pages processed, LLM calls, challenges, summarization calls, API requests, ETL executions, LLM costs, and prompt executions
- Aggregates data from 4 source tables into 3 pre-computed tables (hourly/daily/monthly)
- Provides REST API endpoints with Redis caching for fast dashboard rendering

### Data Flow
```
Source Tables (usage_v2, page_usage, workflow_execution, workflow_file_execution)
       ↓ [Celery task every 15 min]
Aggregated Tables (EventMetricsHourly → Daily → Monthly)
       ↓
API Endpoints (/overview/, /summary/, /series/)
       ↓ [Redis cache]
Frontend Dashboard (MetricsSummary, MetricsChart, MetricsTable)
```

### Key Files
| File | Purpose |
|------|---------|
| `services.py` | Queries source tables (9 methods, one per metric) |
| `tasks.py` | Celery tasks for aggregation and cleanup |
| `views.py` | REST API endpoints |
| `cache.py` | Redis caching layer (bucket-based MGET) |
| `models.py` | Aggregated tables (Hourly/Daily/Monthly) |

### Quick Commands
```bash
# Backfill historical data (run first!)
python manage.py backfill_metrics --days=30

# Start metrics worker
celery -A backend worker -Q dashboard_metric_events -l info

# Start scheduler (for periodic aggregation)
celery -A backend beat -l info
```

### Celery Tasks & Schedule
| Task | Schedule | What It Does |
|------|----------|--------------|
| `aggregate_from_sources` | Every 15 min | Aggregates source → hourly/daily/monthly |
| `cleanup_hourly_data` | Daily 2 AM | Deletes hourly data > 30 days |
| `cleanup_daily_data` | Weekly Sun 3 AM | Deletes daily data > 365 days |

### API Endpoints
| Endpoint | Source | Use Case |
|----------|--------|----------|
| `/overview/` | Hourly table | Dashboard home (last 7 days) |
| `/summary/` | Auto-selected | Detailed stats with date range |
| `/series/` | Auto-selected | Time series charts |
| `/live-summary/` | Source tables | Real-time (no aggregation delay) |

### Caching TTLs
- **Current hour**: 30 seconds (data still changing)
- **Historical**: 8 hours (stable data)
- **Overview API**: 5 minutes
- **Summary/Series API**: 15-30 minutes

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Metrics Definitions](#metrics-definitions)
- [Source Tables](#source-tables)
- [Aggregated Tables](#aggregated-tables)
- [Celery Tasks](#celery-tasks)
- [API Endpoints](#api-endpoints)
- [Caching Strategy](#caching-strategy)
- [Frontend Components](#frontend-components)
- [Setup & Configuration](#setup--configuration)
- [Management Commands](#management-commands)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SOURCE TABLES                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   usage_v2   │  │ page_usage   │  │  workflow_   │  │  workflow_   │    │
│  │              │  │              │  │  execution   │  │  file_exec   │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │     MetricsQueryService         │
                    │   (services.py)                 │
                    │                                 │
                    │  Queries source tables and      │
                    │  aggregates by time period      │
                    └────────────────┬────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ EventMetrics    │      │ EventMetrics    │      │ EventMetrics    │
│ Hourly          │      │ Daily           │      │ Monthly         │
│                 │      │                 │      │                 │
│ • 24h query     │      │ • 7 day query   │      │ • 2 month query │
│ • 30 day retain │      │ • 365 day retain│      │ • No cleanup    │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │      API Endpoints        │
                    │      (views.py)           │
                    │                           │
                    │  /overview/               │
                    │  /summary/                │
                    │  /series/                 │
                    │  /live-summary/           │
                    │  /live-series/            │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Redis Cache (Bucket)    │
                    │                           │
                    │  Per-hour bucket caching  │
                    │  MGET for batch retrieval │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │     Frontend Dashboard    │
                    │                           │
                    │  MetricsSummary           │
                    │  MetricsChart             │
                    │  MetricsBreakdown         │
                    │  MetricsTable             │
                    └───────────────────────────┘
```

---

## Metrics Definitions

### All 9 Metrics

| Metric Name | Type | Description | Unit |
|-------------|------|-------------|------|
| `documents_processed` | Counter | Number of documents successfully processed | count |
| `pages_processed` | Histogram | Total pages extracted from documents | count |
| `llm_calls` | Counter | Number of LLM API calls made | count |
| `challenges` | Counter | LLM calls for challenge/verification | count |
| `summarization_calls` | Counter | LLM calls for summarization | count |
| `deployed_api_requests` | Counter | Requests to deployed API endpoints | count |
| `etl_pipeline_executions` | Counter | ETL pipeline workflow executions | count |
| `llm_usage` | Histogram | LLM usage cost | USD ($) |
| `prompt_executions` | Counter | Total workflow/prompt executions | count |

### Metric Types: Counter vs Histogram

The `metric_type` field distinguishes how metrics are aggregated:

| Type | Aggregation | Use Case | Example |
|------|-------------|----------|---------|
| **Counter** | `COUNT(id)` | Counting discrete events | "How many LLM calls happened?" |
| **Histogram** | `SUM(value)` | Summing continuous values | "How many pages were processed?" |

**Counter Metrics** (7 metrics):
- `documents_processed`, `llm_calls`, `challenges`, `summarization_calls`
- `deployed_api_requests`, `etl_pipeline_executions`, `prompt_executions`

**Histogram Metrics** (2 metrics):
- `pages_processed` - Sums `pages_processed` field from PageUsage
- `llm_usage` - Sums `cost_in_dollars` field from Usage

The `metric_count` field tracks how many source records were aggregated, useful for calculating averages (`total_value / metric_count`).

### Cost Calculation (`llm_usage` metric)

The `cost_in_dollars` value in the Usage table is calculated by the **platform-service** when recording LLM usage:

```
cost = (input_cost_per_token × input_tokens) + (output_cost_per_token × output_tokens)
```

**Pricing Source**: LiteLLM's model pricing database
- URL: `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`
- Cached locally with configurable TTL (default: 7 days)
- Contains `input_cost_per_token` and `output_cost_per_token` per model/provider

**Calculation Flow** (in `platform-service/helper/cost_calculation.py`):
1. Lookup model by name + provider in pricing database
2. Get `input_cost_per_token` and `output_cost_per_token`
3. Calculate: `cost = (input_cost × prompt_tokens) + (output_cost × completion_tokens)`
4. Store in `usage_v2.cost_in_dollars` field

**Example**: GPT-4 with 1000 input tokens and 500 output tokens:
- Input: $0.00003/token × 1000 = $0.03
- Output: $0.00006/token × 500 = $0.03
- Total: $0.06

---

## Source Tables

### Metric to Source Table Mapping

| Metric | Source Table | Model | Filter Conditions | Aggregation |
|--------|-------------|-------|-------------------|-------------|
| `documents_processed` | `workflow_file_execution` | `WorkflowFileExecution` | `status="COMPLETED"` | `COUNT(id)` |
| `pages_processed` | `page_usage` | `PageUsage` | None | `SUM(pages_processed)` |
| `llm_calls` | `usage_v2` | `Usage` | `usage_type="llm"` | `COUNT(id)` |
| `challenges` | `usage_v2` | `Usage` | `usage_type="llm"`, `llm_usage_reason="challenge"` | `COUNT(id)` |
| `summarization_calls` | `usage_v2` | `Usage` | `usage_type="llm"`, `llm_usage_reason="summarize"` | `COUNT(id)` |
| `deployed_api_requests` | `workflow_execution` | `WorkflowExecution` | `pipeline_id IN APIDeployment.ids` | `COUNT(id)` |
| `etl_pipeline_executions` | `workflow_execution` | `WorkflowExecution` | `pipeline_id IN Pipeline(type=ETL).ids` | `COUNT(id)` |
| `llm_usage` | `usage_v2` | `Usage` | `usage_type="llm"` | `SUM(cost_in_dollars)` |
| `prompt_executions` | `workflow_execution` | `WorkflowExecution` | Via `workflow.organization_id` | `COUNT(id)` |

### Source Table Details

#### 1. `usage_v2` (Usage Model)
- **Location**: `usage_v2/models.py`
- **Key Fields**:
  - `organization_id`: UUID - Organization reference
  - `usage_type`: String - Type of usage ("llm", "embedding", etc.)
  - `llm_usage_reason`: String - Reason for LLM call ("extraction", "challenge", "summarize")
  - `cost_in_dollars`: Decimal - Cost of the LLM call
  - `created_at`: DateTime - Timestamp
- **Metrics Derived**: `llm_calls`, `challenges`, `summarization_calls`, `llm_usage`

#### 2. `page_usage` (PageUsage Model)
- **Location**: `account_usage/models.py`
- **Key Fields**:
  - `organization_id`: String - Organization ID (note: CharField, not FK)
  - `pages_processed`: Integer - Number of pages processed
  - `file_name`: String - Source file name
  - `created_at`: DateTime - Timestamp
- **Metrics Derived**: `pages_processed`

#### 3. `workflow_execution` (WorkflowExecution Model)
- **Location**: `workflow_manager/workflow_v2/models/execution.py`
- **Key Fields**:
  - `workflow_id`: FK - Reference to Workflow
  - `pipeline_id`: FK - Reference to Pipeline/APIDeployment
  - `status`: String - Execution status
  - `created_at`: DateTime - Timestamp
- **Metrics Derived**: `deployed_api_requests`, `etl_pipeline_executions`, `prompt_executions`

#### 4. `workflow_file_execution` (WorkflowFileExecution Model)
- **Location**: `workflow_manager/file_execution/models.py`
- **Key Fields**:
  - `workflow_execution_id`: FK - Reference to WorkflowExecution
  - `file_name`: String - Processed file name
  - `status`: String - "COMPLETED", "ERROR", etc.
  - `created_at`: DateTime - Timestamp
- **Metrics Derived**: `documents_processed`

---

## Aggregated Tables

### Three-Tier Aggregation

| Table | Model | Time Column | Granularity | Query Window | Retention |
|-------|-------|-------------|-------------|--------------|-----------|
| `event_metrics_hourly` | `EventMetricsHourly` | `timestamp` | Hour | Last 24 hours | 30 days |
| `event_metrics_daily` | `EventMetricsDaily` | `date` | Day | Last 7 days | 365 days |
| `event_metrics_monthly` | `EventMetricsMonthly` | `month` | Month | Last 2 months | Forever |

### Table Schema

All three tables share a similar schema:

```python
class EventMetricsHourly(Model):
    id = UUIDField(primary_key=True)
    organization = ForeignKey(Organization)
    timestamp = DateTimeField()           # Hour bucket (truncated)
    metric_name = CharField(max_length=64)  # e.g., "documents_processed"
    metric_type = CharField(choices=["counter", "histogram"])
    metric_value = FloatField()           # Aggregated value
    metric_count = IntegerField()         # Number of events aggregated
    labels = JSONField()                  # Additional dimensions
    project = CharField(default="default")
    tag = CharField(blank=True)
    created_at = DateTimeField(auto_now_add=True)
    modified_at = DateTimeField(auto_now=True)
```

### Unique Constraints

Each table has a unique constraint on:
```
(organization, timestamp/date/month, metric_name, project, tag)
```

This enables upsert operations during aggregation.

---

## Celery Tasks

### Task Configuration

Located in `tasks.py`:

| Task Name | Celery Name | Schedule | Queue | Purpose |
|-----------|-------------|----------|-------|---------|
| `aggregate_metrics_from_sources` | `dashboard_metrics.aggregate_from_sources` | Every 15 min | `dashboard_metric_events` | Aggregate from source tables |
| `cleanup_hourly_metrics` | `dashboard_metrics.cleanup_hourly_data` | Daily 2:00 AM UTC | `dashboard_metric_events` | Delete hourly data >30 days |
| `cleanup_daily_metrics` | `dashboard_metrics.cleanup_daily_data` | Weekly Sun 3:00 AM UTC | `dashboard_metric_events` | Delete daily data >365 days |
| `process_dashboard_metric_events` | `dashboard_metrics.process_events` | On-demand (batched) | `dashboard_metric_events` | Process real-time events |

### Queue Configuration

In `backend/celery_config.py`:

```python
task_queues = [
    Queue("dashboard_metric_events", routing_key="dashboard_metric_events"),
    # ... other queues
]

task_routes = {
    "dashboard_metrics.process_events": {"queue": "dashboard_metric_events"},
    "dashboard_metrics.aggregate_from_sources": {"queue": "dashboard_metric_events"},
    "dashboard_metrics.cleanup_hourly_data": {"queue": "dashboard_metric_events"},
    "dashboard_metrics.cleanup_daily_data": {"queue": "dashboard_metric_events"},
}
```

### Running the Worker

```bash
# Start the dashboard metrics worker
celery -A backend worker --loglevel=info -Q dashboard_metric_events

# Start Celery Beat for periodic tasks
celery -A backend beat --loglevel=info
```

### Aggregation Task Details

The `aggregate_metrics_from_sources` task:

1. **Iterates over all organizations**
2. **For each metric**:
   - Queries source table with `MetricsQueryService`
   - Groups by time period (hour/day/month)
3. **Upserts results** into aggregated tables using `update_or_create`
4. **Uses `_base_manager`** to bypass Django's organization filter in Celery context

```python
# Query windows
hourly_start = end_date - timedelta(hours=24)    # Last 24 hours
daily_start = end_date - timedelta(days=7)       # Last 7 days
monthly_start = first_of_previous_month          # Last 2 months
```

---

## API Endpoints

### Endpoint Overview

Base URL: `/api/v1/unstract/<org_id>/metrics/`

| Endpoint | Method | Description | Data Source |
|----------|--------|-------------|-------------|
| `/overview/` | GET | Last 7 days summary + daily trend | `EventMetricsHourly` |
| `/summary/` | GET | Summary stats for date range | Auto-selected table |
| `/series/` | GET | Time series for date range | Auto-selected table |
| `/live-summary/` | GET | Summary from source tables | Source tables directly |
| `/live-series/` | GET | Time series from source tables | Source tables directly |
| `/health/` | GET | Health check | DB + Cache |

### Auto Source Selection

The `/summary/` and `/series/` endpoints automatically select the data source:

| Date Range | Source Table |
|------------|--------------|
| ≤ 7 days | `event_metrics_hourly` |
| ≤ 90 days | `event_metrics_daily` |
| > 90 days | `event_metrics_monthly` |

Override with `?source=hourly|daily|monthly`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_date` | ISO 8601 | 30 days ago | Start of date range |
| `end_date` | ISO 8601 | Now | End of date range |
| `granularity` | String | `day` | Time grouping: `hour`, `day`, `week` |
| `metric_name` | String | None | Filter by specific metric |
| `project` | String | None | Filter by project |
| `source` | String | `auto` | Data source: `auto`, `hourly`, `daily`, `monthly` |

### Response Format

#### `/overview/` Response
```json
{
  "period": {
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-01-07T23:59:59Z",
    "days": 7
  },
  "totals": [
    {"metric_name": "documents_processed", "total_value": 1500, "total_count": 150},
    {"metric_name": "pages_processed", "total_value": 45000, "total_count": 150}
  ],
  "daily_trend": [
    {
      "date": "2024-01-01T00:00:00Z",
      "metrics": {
        "documents_processed": 200,
        "pages_processed": 6000
      }
    }
  ]
}
```

#### `/summary/` Response
```json
{
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-31T23:59:59Z",
  "source": "daily",
  "summary": [
    {
      "metric_name": "documents_processed",
      "metric_type": "counter",
      "total_value": 5000,
      "total_count": 500,
      "average_value": 10,
      "min_value": 1,
      "max_value": 50
    }
  ]
}
```

---

## Caching Strategy

### Two-Layer Caching

#### 1. Whole-Response Caching (Simple)
Used for `/overview/`, `/live-summary/`, `/live-series/`

```python
@cache_metrics_response(endpoint="overview")
def overview(self, request):
    ...
```

TTLs:
- Overview: 5 minutes
- Summary: 15 minutes
- Series: 30 minutes

#### 2. Bucket-Based Caching (Advanced)
Used for `/summary/` and `/series/` with hourly source

**How it works:**
1. Split time range into hourly buckets
2. Use Redis MGET to fetch all buckets in one round-trip
3. Query DB only for missing buckets
4. Save new buckets with appropriate TTL

**Cache Key Format:**
```
metrics:bucket:hourly:<org_id>:<timestamp>[:metric_name]
```

**TTL Strategy:**
- Current hour: 30 seconds (data still changing)
- Historical hours: 8 hours (data stable)

**Benefits:**
- Overlapping queries reuse cached buckets
- Query for Jan 1-7 caches 168 hourly buckets
- Query for Jan 5-10 reuses 72 cached buckets, only queries 72 new

### Cache Configuration

In `settings.py`:
```python
DASHBOARD_CACHE_TTL_CURRENT_HOUR = 30      # 30 seconds
DASHBOARD_CACHE_TTL_HISTORICAL = 28800     # 8 hours
DASHBOARD_CACHE_TTL_OVERVIEW = 300         # 5 minutes
DASHBOARD_CACHE_TTL_SUMMARY = 900          # 15 minutes
DASHBOARD_CACHE_TTL_SERIES = 1800          # 30 minutes
```

---

## Frontend Components

### Component Hierarchy

```
MetricsDashboardPage
└── MetricsDashboard
    ├── MetricsSummary     (Summary cards - uses totals)
    ├── MetricsChart       (Line chart - uses daily_trend)
    ├── MetricsBreakdown   (Distribution - uses totals)
    └── MetricsTable       (Detailed table - uses summary)
```

### Data Hooks

Located in `frontend/src/hooks/useMetricsData.js`:

| Hook | Endpoint | Purpose |
|------|----------|---------|
| `useMetricsOverview` | `/overview/` | Last 7 days quick stats |
| `useMetricsSummary` | `/summary/` | Summary with date range |
| `useMetricsSeries` | `/series/` | Time series with date range |

### Frontend Caching

Uses localStorage with TTL matching backend:
```javascript
// helpers/metricsCache.js
const CACHE_TTL = {
  overview: 5 * 60 * 1000,    // 5 minutes
  summary: 15 * 60 * 1000,    // 15 minutes
  series: 30 * 60 * 1000,     // 30 minutes
};
```

---

## Setup & Configuration

### 1. Install Dependencies

```bash
cd backend/
uv sync
```

Required packages in `pyproject.toml`:
- `celery-batches` - For batched event processing
- `django-celery-beat` - For periodic task scheduling
- `django-redis` - For MGET/pipeline operations

### 2. Run Migrations

```bash
python manage.py migrate dashboard_metrics
```

This creates:
- Three aggregated tables
- Periodic task schedules in `django_celery_beat`

### 3. Backfill Historical Data

```bash
# Backfill last 30 days for all organizations
python manage.py backfill_metrics --days=30

# Backfill for specific org
python manage.py backfill_metrics --days=90 --org-id=<uuid>

# Dry run to see what would be done
python manage.py backfill_metrics --days=7 --dry-run
```

### 4. Start Workers

```bash
# Terminal 1: Dashboard metrics worker
celery -A backend worker --loglevel=info -Q dashboard_metric_events

# Terminal 2: Celery Beat scheduler
celery -A backend beat --loglevel=info
```

### 5. Verify Setup

```bash
# Check periodic tasks are registered
python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
for t in PeriodicTask.objects.filter(name__startswith='dashboard'):
    print(f'{t.name}: enabled={t.enabled}')
"

# Check aggregated data exists
python manage.py shell -c "
from dashboard_metrics.models import EventMetricsHourly
print(f'Hourly records: {EventMetricsHourly._base_manager.count()}')
"
```

---

## Management Commands

### `backfill_metrics`

Populates aggregated tables from historical source data.

```bash
python manage.py backfill_metrics [options]

Options:
  --days=N          Number of days to backfill (default: 30)
  --org-id=UUID     Specific organization (default: all)
  --dry-run         Show what would be done
  --skip-hourly     Skip hourly aggregation
  --skip-daily      Skip daily aggregation
  --skip-monthly    Skip monthly aggregation
```

### `generate_metrics_test_data`

Creates test data in source tables for development.

```bash
python manage.py generate_metrics_test_data [options]

Options:
  --org-id=UUID         Organization ID
  --days=N              Days of data to generate (default: 7)
  --records-per-day=N   Records per day per table (default: 20)
  --clean               Remove existing test data first
```

---

## Troubleshooting

### Common Issues

#### 1. Chart shows only one metric
**Cause**: Only one metric has data in `EventMetricsHourly`
**Fix**: Run `python manage.py backfill_metrics --days=30`

#### 2. Empty dashboard
**Cause**: Aggregated tables are empty
**Fix**:
1. Check source tables have data
2. Run backfill command
3. Verify Celery worker is running

#### 3. Celery task not running
**Cause**: Task not routed to correct queue
**Fix**: Ensure `celery_config.py` has the task route:
```python
"dashboard_metrics.aggregate_from_sources": {"queue": "dashboard_metric_events"},
```

#### 4. Slow queries
**Cause**: Large date range hitting hourly table
**Fix**: Use `?source=daily` or `?source=monthly` for large ranges

### Debugging Commands

```bash
# Check what's in aggregated tables
python manage.py shell -c "
from dashboard_metrics.models import *
from django.db.models import Count

print('=== Hourly ===')
for m in EventMetricsHourly._base_manager.values('metric_name').annotate(c=Count('id')):
    print(f\"  {m['metric_name']}: {m['c']}\")

print('=== Daily ===')
for m in EventMetricsDaily._base_manager.values('metric_name').annotate(c=Count('id')):
    print(f\"  {m['metric_name']}: {m['c']}\")
"

# Manually trigger aggregation
python manage.py shell -c "
from dashboard_metrics.tasks import aggregate_metrics_from_sources
result = aggregate_metrics_from_sources()
print(result)
"

# Check cache stats
python manage.py shell -c "
from dashboard_metrics.cache import get_bucket_cache_stats
from django.utils import timezone
from datetime import timedelta

end = timezone.now()
start = end - timedelta(days=7)
stats = get_bucket_cache_stats('your-org-id', start, end, 'hourly')
print(stats)
"
```

---

## File Structure

```
backend/dashboard_metrics/
├── __init__.py
├── admin.py                    # Django admin registration
├── apps.py                     # App configuration
├── cache.py                    # Caching layer (bucket-based + decorators)
├── models.py                   # EventMetricsHourly/Daily/Monthly models
├── serializers.py              # DRF serializers
├── services.py                 # MetricsQueryService (source table queries)
├── tasks.py                    # Celery tasks (aggregation, cleanup)
├── urls.py                     # URL routing
├── views.py                    # API ViewSet
├── README.md                   # This file
├── management/
│   └── commands/
│       ├── backfill_metrics.py
│       └── generate_metrics_test_data.py
├── migrations/
│   ├── 0001_initial.py                    # Create tables
│   ├── 0002_setup_cleanup_tasks.py        # Cleanup periodic tasks
│   └── 0003_setup_aggregation_task.py     # Aggregation periodic task
└── tests/
    └── test_tasks.py
```

---

## Contributing

When adding new metrics:

1. **Add query method** in `services.py`:
   ```python
   @staticmethod
   def get_new_metric(org_id, start, end, granularity):
       ...
   ```

2. **Add to metric configs** in `tasks.py`:
   ```python
   metric_configs = [
       ...
       ("new_metric", MetricsQueryService.get_new_metric, False),
   ]
   ```

3. **Add to backfill command** in `management/commands/backfill_metrics.py`

4. **Update frontend** default selected metrics if needed

5. **Run backfill** to populate historical data
