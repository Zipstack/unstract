# Celery Chord Infinite Retry Issue - Complete Analysis

## Summary
The production system experienced 20+ days of continuous retries causing worker saturation due to a combination of Celery design flaws and application-level bugs.

## Root Cause Chain

### 1. Initial Trigger: Malformed Task Results
- **File processing batch tasks** completed but returned `None` instead of expected result dictionaries
- **Expected format**: `{"successful_files": X, "failed_files": Y}`
- **Actual format**: `None` values
- **Evidence**: chord_unlock task args show `'result': [[['788dee64-1fba-4018-9403-0f7c40b6b424', None], None], ...]`

### 2. Callback Task Crash  
- **Location**: `backend/workflow_manager/workflow_v2/file_execution_tasks.py:334`
- **Code**: `sum(result["successful_files"] for result in results)`
- **Error**: `TypeError: 'NoneType' object is not subscriptable`
- **Affected Executions**:
  - `7c6fe329-a39b-43f7-8589-2153ac51f6fd` (Workflow 2, 100 files) - started May 2025
  - `51d7f771-7f57-4660-bd5f-501d06968baa` (gokul's test, 45 files) - started May 2025
- **Impact**: Callback crashes before acknowledging completion

### 3. Celery Chord Design Flaw
- **chord_unlock task** monitors chord completion in Celery's built-in implementation
- **Configuration**: `max_retries=None` (unlimited retries)
- **Retry interval**: 3 seconds (`CELERY_RESULT_CHORD_RETRY_INTERVAL=3`)
- **When callback fails**: chord_unlock retries indefinitely
- **Source**: `celery/app/builtins.py` - `@app.task(name='celery.chord_unlock', max_retries=None, ...)`

### 4. Message Redelivery Loop
- **`task_acks_late = True`**: Tasks only acknowledge after successful completion (line 33 in `backend/backend/celery_config.py`)
- **Unhandled exception**: Prevents acknowledgment of failed callback tasks
- **Result**: Failed callback messages remain in queue and get redelivered

### 5. Configuration Change Amplification
- **June 3, 2025**: Critical configuration change deployed via [PR #1335](https://github.com/Zipstack/unstract/pull/1335) (commit `a59d8a8a`)
- **PR Purpose**: "Celery split for callbacks" - separate workers for file processing vs callbacks
- **Change**: `worker_pool_restarts = True` added to prevent chord loss during scaling
- **Unintended consequence**: Multiple workers began processing same chord_unlock tasks
- **Multiplication effect**: Each worker scaling event created additional chord_unlock instances

### 6. Worker Saturation and Exponential Amplification  
- **Load balancing**: Each retry lands on different worker
- **Multiple simultaneous executions**: Same chord_unlock task running on multiple workers
- **Stuck task IDs observed**:
  - `57e32ca2-c0a9-43ef-a8ca-bd3d5f70d2aa` (execution: `7c6fe329-a39b-43f7-8589-2153ac51f6fd`)
  - `daee3d80-6d44-419e-9029-c3a3b2ecacb0` (execution: `51d7f771-7f57-4660-bd5f-501d06968baa`)
  - `0eaa011d-654d-43f8-beb6-a2e3557eae0c` (chord ID for coordinating tasks)
- **Resource exhaustion**: Workers consumed by exponentially multiplying retries
- **Infrastructure scaling**: Cloud repo commit `68f12f02` added memory/scale upgrades, triggering more multiplication

## Observable Symptoms
- **Fluctuating chord_unlock count**: 7→5→1→1→1→2→2→3 (indicating continuous creation/destruction)
- **Multiple workers executing identical tasks**: Same task ID on different worker nodes
- **Log spam**: `"INFO : Task celery.chord_unlock[57e32ca2-c0a9-43ef-a8ca-bd3d5f70d2aa] retry: Retry in 3s"` every 3 seconds
- **WorkflowExecution stuck**: Records remain in "EXECUTING" status indefinitely
- **Worker saturation**: High CPU/memory usage with no productive work
- **⚠️ CRITICAL TIMELINE: Executions stuck for 2.5+ months**:
  - `51d7f771-7f57-4660-bd5f-501d06968baa`: 77 days (2 months, 9 days, 16 hours)
  - `7c6fe329-a39b-43f7-8589-2153ac51f6fd`: 84 days (2 months, 16 days, 8 hours)
- **Log forensics impossible**: Original execution logs missing due to retention, only chord_unlock retry logs available

## Why Standard Retry Mechanisms Failed

### Application Level
- **max_retries=0**: Only applies to individual tasks, not chord coordination
- **Exception handling**: Missing around critical aggregation logic in callback
- **Input validation**: No validation of batch task results before aggregation

### Celery Level
- **Chord design**: Assumes callbacks will eventually succeed or fail cleanly
- **No circuit breaker**: chord_unlock has no maximum retry limit by design
- **Configuration interaction**: `task_acks_late` + unlimited retries = infinite loops

## Affected Components
- **Stuck executions**: 2 WorkflowExecutions permanently in EXECUTING state
  - Pipeline IDs: `b05a40f8-0284-401b-8dd8-eae13db25432`, `03122cfb-bf31-4c00-9b3a-cd807f6d9e6d`
- **Resource cleanup**: Never triggered (file cleanup, logging, status updates)
- **Worker capacity**: Saturated across multiple worker pools
- **System performance**: Degraded due to resource contention
- **⚠️ CATASTROPHIC SCALE - REVISED**: 
  - **2.5+ months of continuous retries** (since May 2025)
  - **228 MILLION log entries from just 2 executions** (114M per execution via log analytics)
  - **Retry amplification**: ~17 retries per second per execution (not every 3 seconds as expected)
  - **Multiple simultaneous chord_unlock tasks** per execution causing exponential retry explosion
  - **Silent degradation escalation**: 1.5 months undetected, then 10x log spike in July 2025
- **Forensic analysis blocked**: Original failure logs lost to retention, only retry logs remain

## Technical Details

### Code Location
```python
# File: backend/workflow_manager/workflow_v2/file_execution_tasks.py
# Lines: 334-335
total_successful = sum(result["successful_files"] for result in results)
total_failed = sum(result["failed_files"] for result in results)
```

### Configuration Contributing to Issue
```python
# backend/backend/celery_config.py:33
task_acks_late = True

# backend/backend/settings/base.py:169-170
CELERY_RESULT_CHORD_RETRY_INTERVAL = int(
    os.environ.get("CELERY_RESULT_CHORD_RETRY_INTERVAL", "3")
)

# backend/workflow_manager/workflow_v2/file_execution_tasks.py:292
max_retries=0  # Only applies to callback task, not chord_unlock
```

### Celery Chord Implementation
```python
# From celery/app/builtins.py
@app.task(name='celery.chord_unlock', max_retries=None, shared=False,
          default_retry_delay=app.conf.result_chord_retry_interval, ...)
```

## Resolution Strategy

### Immediate Actions
1. **Revoke stuck chord_unlock tasks**:
   ```bash
   celery -A backend control revoke 57e32ca2-c0a9-43ef-a8ca-bd3d5f70d2aa --terminate
   celery -A backend control revoke daee3d80-6d44-419e-9029-c3a3b2ecacb0 --terminate
   ```

### Short-term Fixes
1. **Add exception handling in callback aggregation**:
   ```python
   # Around line 334 in file_execution_tasks.py
   try:
       total_successful = sum(
           result.get("successful_files", 0) if result else 0 
           for result in results
       )
       total_failed = sum(
           result.get("failed_files", 0) if result else 0 
           for result in results
       )
   except (TypeError, AttributeError) as e:
       logger.error(f"Invalid batch results format: {results}, error: {e}")
       # Set safe defaults or raise proper exception
   ```

2. **Input validation for batch results**:
   ```python
   # Validate results before aggregation
   if not results or not all(isinstance(r, dict) for r in results if r):
       logger.error(f"Invalid batch results: {results}")
       # Handle gracefully
   ```

### Long-term Solutions
1. **Implement chord retry limits** via custom chord implementation
2. **Replace chord with alternative coordination** (e.g., database-based workflow state)
3. **Add circuit breakers** for workflow coordination
4. **Improve observability** for chord health monitoring

## Lessons Learned
- **Celery chords require careful exception handling** in callback tasks
- **`task_acks_late` can amplify failure scenarios** when combined with poor error handling
- **Unlimited retries are dangerous** without proper circuit breakers
- **Input validation is critical** for task coordination points
- **Celery chord design has known limitations** at scale
- **⚠️ MONITORING BLIND SPOT**: System degraded silently for 1.5 months before becoming visible through log volume spike
- **⚠️ LOG RETENTION vs FORENSICS**: Critical debugging information lost when logs rotate faster than issue detection
- **⚠️ ESCALATION PATTERN**: Issues can compound over time, becoming more severe and resource-intensive

## Prevention Measures
1. **Mandatory exception handling** in all chord callbacks
2. **Input validation** for all inter-task data
3. **⚠️ CRITICAL: Chord retry monitoring** with alerts for tasks running >24 hours
4. **⚠️ CRITICAL: Worker health dashboards** showing task retry rates and patterns
5. **Extended log retention** for coordination task failures
6. **Dead letter queues** for permanently failed chord callbacks
7. **Consider alternatives to chords** for complex workflows

## Scale Discovery via Log Analytics
**Critical finding through targeted log analytics query:**
```sql
SELECT COUNT(*) AS log_count FROM `unstract-production.global._Default._Default`
WHERE text_payload LIKE '%Task celery.chord_unlock[57e32ca2-c0a9-43ef-a8ca-bd3d5f70d2aa] retry: Retry in 3s%'
   OR text_payload LIKE '%Task celery.chord_unlock[0eaa011d-654d-43f8-beb6-a2e3557eae0c] retry: Retry in 3s%';
```
- **228,368,034 total log entries** from just 2 stuck executions
- **114M logs per execution**: Far exceeding expected retry frequency
- **Retry amplification**: Multiple simultaneous chord_unlock instances per execution
- **Resource multiplication**: Each execution spawning dozens of concurrent retry attempts

## Forensic Challenges
**Root cause analysis was severely hampered by:**
- **Log retention policies**: 12-week retention window insufficient for long-running issues
- **Different log streams**: Execution logs vs chord_unlock retry logs have different retention
- **Silent degradation**: No alerting on abnormal retry patterns
- **Missing observability**: No dashboards showing chord health over time
- **⚠️ SCALE BLINDNESS**: Manual inspection only revealed 2 stuck executions; log analytics revealed systemic failure

**Recommendation**: Implement dedicated monitoring for Celery coordination primitives separate from application logs.

---

**Date**: August 2025 - Analysis completed on production issue lasting 2.5+ months (since May 2025)  
**Impact**: 228 MILLION log entries from just 2 stuck executions, exponential retry amplification  
**Scale**: 114M logs per execution (~17 retries/second), multiple concurrent chord_unlock tasks per execution  
**Resolution**: Emergency chord task termination + retry amplification fix + worker scaling review