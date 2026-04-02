# API Deployment Rate Limiting

## Overview

This document describes the rate limiting implementation for API deployments in Unstract. Rate limiting controls the number of concurrent API deployment requests to prevent resource exhaustion and ensure fair usage across organizations.

**Scope**: This rate limiting **ONLY applies to API deployments** (REST API endpoints). It does **NOT** affect:
- ETL pipeline executions
- Manual workflow runs from the UI
- Scheduled tasks
- Background jobs

## Architecture

### Dual-Layer Rate Limiting

The system implements two layers of rate limiting:

1. **Per-Organization Limit**: Each organization has a maximum number of concurrent API requests
2. **Global Limit**: System-wide limit across all organizations

Both limits are enforced, and requests are rejected if either limit is exceeded.

### Key Components

```
┌─────────────────────────────────────────────────────────────┐
│                API Request Flow (View Layer)                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │  1. Validate Request           │
            │     (Serializer, Files)        │
            └───────────────────────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │  2. Check Organization Limit   │
            │     (Per-Org Redis Lock)       │
            └───────────────────────────────┘
                            │
                    ┌───────┴───────┐
                    │               │
               ✓ Available      ✗ Exceeded
                    │               │
                    ▼               ▼
            ┌──────────────┐  ┌──────────────┐
            │ 3. Check     │  │ Raise 429    │
            │    Global    │  │ Rate Limit   │
            │    Limit     │  │ Exceeded     │
            └──────────────┘  └──────────────┘
                    │
            ┌───────┴───────┐
            │               │
       ✓ Available      ✗ Exceeded
            │               │
            ▼               ▼
    ┌──────────────┐  ┌──────────────┐
    │ 4. Acquire   │  │ Raise 429    │
    │    Slot      │  │ Rate Limit   │
    │  (ZSET Add)  │  │ Exceeded     │
    └──────────────┘  └──────────────┘
            │
            ▼
    ┌──────────────────────────────────┐
    │ 5. Execute Workflow (try-catch)  │
    │    - Setup (DB, files, queue)    │
    │    - Dispatch async job          │
    └──────────────────────────────────┘
            │
        ┌───┴───┐
        │       │
    Success   Exception
        │       │
        ▼       ▼
    ┌─────┐  ┌──────────────┐
    │ 6a. │  │ 6b. Release  │
    │Signal│  │     Slot     │
    │Will │  │  (Manual in  │
    │Auto │  │   Exception  │
    │Release│  │   Handler)   │
    └─────┘  └──────────────┘
               │
               ▼
         ┌──────────────┐
         │ Re-raise     │
         │ Exception    │
         └──────────────┘
```

**Key Design Points:**

- **View Layer Responsibility**: Rate limiting handled in `api_deployment_views.py`
- **Dual Release Paths**:
  - **View layer** releases on exceptions that propagate (early setup failures: DB, files)
  - **Helper layer** releases on caught exceptions (async dispatch failures, config errors)
  - **Signal** releases on successful async job completion
- **No Orphaned Slots**: Guaranteed cleanup on all error paths
- **No Double-Release**: Each failure path has exactly one release point

### Technical Implementation

#### 1. Redis Distributed Locks (Per-Organization)
- Each organization has a dedicated Redis lock
- Ensures atomic check-and-acquire operations
- Prevents race conditions within the same organization
- Lock timeout: 2 seconds (auto-release if holder crashes)
- Blocking timeout: 5 seconds (wait time to acquire lock)

#### 2. Redis Sorted Sets (ZSET)
- Tracks active executions with timestamps
- Automatic TTL-based cleanup (6 hours default)
- Separate ZSETs for:
  - Per-organization tracking: `api_deployment:rate_limit:org:{org_id}`
  - Global tracking: `api_deployment:rate_limit:global`

#### 3. Django Cache (Organization Limits)
- Caches organization rate limits from database
- **TTL**: 10 minutes
- **TTL Refresh**: Extended by 10 minutes on every read (LRU-like behavior)
- **Auto-invalidation**: Cache cleared on limit update/delete
- **Benefit**: ~95% reduction in database queries

#### 4. Atomic Check-and-Acquire
```python
# Pseudocode
with redis_lock(org_lock_key):
    cleanup_expired_entries()
    if org_count >= org_limit:
        return RATE_LIMIT_EXCEEDED
    if global_count >= global_limit:
        return RATE_LIMIT_EXCEEDED
    # Atomically add to both ZSETs
    zadd(org_key, execution_id, timestamp)
    zadd(global_key, execution_id, timestamp)
    return SUCCESS
```

#### 5. Automatic Release
- Slot automatically released when workflow execution completes
- Triggered by `WorkflowExecution.update_execution()` on completion/failure
- Fail-safe: Even if release fails, entries expire after TTL (6 hours)

### Fail-Open Strategy

If Redis is unavailable or operations fail, the system **allows requests** to proceed. This prevents rate limiting infrastructure issues from blocking legitimate traffic.

## Configuration

### Environment Variables

All configuration is done via environment variables in `.env` or system environment:

```bash
# Default concurrent request limit per organization (default: 20)
API_DEPLOYMENT_DEFAULT_RATE_LIMIT=20

# Global system-wide concurrent request limit (default: 100)
API_DEPLOYMENT_GLOBAL_RATE_LIMIT=100

# Time window (in hours) to keep requests as "active" (default: 6)
# Entries older than this are automatically cleaned up
API_DEPLOYMENT_RATE_LIMIT_TTL_HOURS=6

# Cache TTL for organization limits (in seconds, default: 600)
# TTL is refreshed on every read - frequently-used orgs stay cached
# Inactive orgs expire after this duration
API_DEPLOYMENT_RATE_LIMIT_CACHE_TTL=600

# Redis lock timeout (in seconds, default: 2)
# Lock auto-expires if holder crashes
API_DEPLOYMENT_RATE_LIMIT_LOCK_TIMEOUT=2

# Redis lock blocking timeout (in seconds, default: 5)
# How long to wait to acquire lock before giving up
API_DEPLOYMENT_RATE_LIMIT_LOCK_BLOCKING_TIMEOUT=5
```

### Django Settings

These environment variables are loaded in `backend/settings/base.py`:

```python
API_DEPLOYMENT_DEFAULT_RATE_LIMIT = int(os.environ.get("API_DEPLOYMENT_DEFAULT_RATE_LIMIT", 20))
API_DEPLOYMENT_GLOBAL_RATE_LIMIT = int(os.environ.get("API_DEPLOYMENT_GLOBAL_RATE_LIMIT", 100))
# ... etc
```

## Management Commands

Five management commands are provided for administrative operations:

### 1. Set Organization Rate Limit

Set or update a custom rate limit for a specific organization:

```bash
# Using organization ID
python manage.py set_org_rate_limit org_a1b2c3d4e5f6g7h8 50

# Using organization name
python manage.py set_org_rate_limit acme-corp 50
```

**Output**:
```
Created rate limit for organization "acme-corp" (org_a1b2c3d4e5f6g7h8): 50
Current usage: 5/50 concurrent requests
✓ Cache automatically cleared
```

**Features**:
- Accepts organization ID or name
- Auto-clears cache after update
- Shows current usage
- Warns if current usage exceeds new limit

### 2. Get Organization Rate Limit

View rate limit information and current usage for an organization:

```bash
# View rate limit info
python manage.py get_org_rate_limit org_a1b2c3d4e5f6g7h8

# Clear cache and force refresh from DB
python manage.py get_org_rate_limit org_a1b2c3d4e5f6g7h8 --clear-cache
```

**Output**:
```
Database Limit: 50
Last Modified: 2025-11-08 10:30:00
Cached Limit: 50 ✓

--- Current Usage ---
Organization: 5/50 concurrent requests
Global System: 45/100 concurrent requests
Organization at 10.0% capacity
```

### 3. List All Organization Rate Limits

List all organizations with custom rate limits:

```bash
# List without usage stats (fast)
python manage.py list_org_rate_limits

# List with current usage (slower, queries Redis)
python manage.py list_org_rate_limits --with-usage
```

**Output**:
```
Found 3 custom rate limits:

• acme-corp (org_a1b2c3d4e5f6g7h8)
  Limit: 50
  Usage: 5/50 (10.0%)

• widgets-inc (org_r1II1U07Th3RnSfv)
  Limit: 100
  Usage: 0/100 (0.0%)

• tech-startup (org_zj4xaTiCdTToPlaj)
  Limit: 25
  Usage: 18/25 (72.0%)
```

### 4. Delete Organization Rate Limit

Remove a custom rate limit (organization reverts to system default):

```bash
# With confirmation prompt
python manage.py delete_org_rate_limit org_a1b2c3d4e5f6g7h8

# Skip confirmation
python manage.py delete_org_rate_limit acme-corp --force
```

**Output**:
```
Organization: acme-corp (org_a1b2c3d4e5f6g7h8)
Current custom limit: 50

This will delete the custom rate limit and revert to the system default.
Continue? [y/N]: y

Deleted custom rate limit for organization "acme-corp" (org_a1b2c3d4e5f6g7h8)
Will now use system default: 20
Current usage: 5/20 concurrent requests
✓ Cache automatically cleared
```

### 5. Clear Organization Rate Limit Cache

Clear cached rate limits (useful after changing default limit via ENV):

```bash
# Clear specific organization cache
python manage.py clear_org_rate_limit_cache --org-id org_a1b2c3d4e5f6g7h8

# Clear cache for all orgs with custom limits (default)
python manage.py clear_org_rate_limit_cache

# Clear cache for ALL organizations (uses Redis pattern deletion)
python manage.py clear_org_rate_limit_cache --all
```

**Output** (for `--all`):
```
Clearing cache for ALL organizations (including those using defaults)...
Deleted 138 cache keys using pattern
✓ Cleared all organization rate limit caches using pattern deletion
Note: Cache will be repopulated on next API request for each org
```

**Performance**:
- With Redis cache backend: Uses `delete_pattern("rate_limit:cache:org_limit:*")` - very fast
- Other cache backends: Falls back to iterating through organizations

## Usage Scenarios

### Scenario 1: Set Custom Limit for High-Volume Customer

```bash
# Customer needs 200 concurrent requests
python manage.py set_org_rate_limit acme-corp 200

# Verify
python manage.py get_org_rate_limit acme-corp
```

### Scenario 2: Update System Default Limit

```bash
# Step 1: Update environment variable
export API_DEPLOYMENT_DEFAULT_RATE_LIMIT=30

# Step 2: Restart application to load new setting
# (or reload via your deployment process)

# Step 3: Clear all caches to pick up immediately
python manage.py clear_org_rate_limit_cache --all

# Now all orgs without custom limits will use 30
```

### Scenario 3: Monitor High-Usage Organizations

```bash
# List all orgs with usage stats
python manage.py list_org_rate_limits --with-usage | grep -E "([7-9][0-9]|100)\.0%"

# Check specific org
python manage.py get_org_rate_limit acme-corp
```

### Scenario 4: Temporarily Reduce Limit During Incident

```bash
# Reduce limit to prevent overload
python manage.py set_org_rate_limit acme-corp 10

# ... incident resolved ...

# Restore original limit
python manage.py set_org_rate_limit acme-corp 50
```

### Scenario 5: Remove All Custom Limits (Revert to Defaults)

```bash
# List all custom limits
python manage.py list_org_rate_limits

# Delete each custom limit
python manage.py delete_org_rate_limit acme-corp --force
python manage.py delete_org_rate_limit widgets-inc --force
python manage.py delete_org_rate_limit tech-startup --force

# All orgs now use system default (20)
```

## API Response Behavior

### Successful Request (200 OK)

When rate limit is not exceeded, requests proceed normally:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "execution_id": "abc123...",
  "status": "queued",
  ...
}
```

### Rate Limit Exceeded (429 Too Many Requests)

When rate limit is exceeded, API returns 429 with a standardized error response:

#### Organization Limit Exceeded
```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "type": "client_error",
  "errors": [
    {
      "code": "error",
      "detail": "Organization has reached the maximum concurrent API requests limit (20/20). Please try again later.",
      "attr": null
    }
  ]
}
```

#### Global Limit Exceeded (System Overload)
```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "type": "client_error",
  "errors": [
    {
      "code": "error",
      "detail": "Our system is currently experiencing high load. Please try again in a few moments.",
      "attr": null
    }
  ]
}
```

**Response Format**:
The error response follows the `drf-standardized-errors` format used throughout the application:
- `type`: Error type (always `"client_error"` for 429)
- `errors`: Array of error objects
  - `code`: Error code (always `"error"`)
  - `detail`: Human-readable error message
  - `attr`: Field name (null for non-field errors)

**Note**: Clients should implement their own retry logic with exponential backoff. The rate limit will be released once active requests complete.

## Best Practices

### 1. Set Custom Limits for Known High-Volume Customers

```bash
# Identify high-volume customers
python manage.py list_org_rate_limits --with-usage

# Set custom limits proactively
python manage.py set_org_rate_limit high-volume-customer 100
```

### 2. Monitor Global Limit Usage

If global limit is frequently hit, consider increasing it:

```bash
# Check current global usage
python manage.py get_org_rate_limit any-org-id  # Shows global usage

# If consistently high, increase global limit
export API_DEPLOYMENT_GLOBAL_RATE_LIMIT=200
# Restart application
```

### 3. Use TTL Refresh for Efficiency

The cache TTL refresh (10 minutes, extended on read) provides optimal performance:
- Active orgs stay cached indefinitely (no DB queries)
- Inactive orgs expire after 10 minutes
- No manual cache management needed

### 4. Clear Cache After ENV Changes

After changing `API_DEPLOYMENT_DEFAULT_RATE_LIMIT`:

```bash
# Clear all caches to pick up new default immediately
python manage.py clear_org_rate_limit_cache --all
```

### 5. Set Appropriate Global Limit

The global limit should be:
- **Higher than sum of expected concurrent per-org usage**
- **Lower than system capacity** (to prevent resource exhaustion)

Example calculation:
- 10 organizations
- Average 20 concurrent requests per org
- Expected total: 200 concurrent requests
- Recommended global limit: 250-300 (buffer for spikes)

## Troubleshooting

### Issue: Rate limit hit but usage seems low

**Check**:
1. Redis cleanup might not have run yet (6-hour TTL)
2. Check actual Redis data:
   ```bash
   redis-cli
   > ZCARD api_deployment:rate_limit:org:org_a1b2c3d4e5f6g7h8
   > ZRANGE api_deployment:rate_limit:org:org_a1b2c3d4e5f6g7h8 0 -1 WITHSCORES
   ```
3. Look for stuck executions (never completed/failed)

**Solution**:
```bash
# Manually cleanup (run ZREMRANGEBYSCORE with old timestamp)
# Or wait for automatic cleanup (next request)
```

### Issue: Custom limit not taking effect

**Check**:
1. Verify limit in database:
   ```bash
   python manage.py get_org_rate_limit acme-corp
   ```
2. Check if cache was cleared:
   ```bash
   python manage.py get_org_rate_limit acme-corp --clear-cache
   ```

**Solution**:
```bash
# Clear cache and verify
python manage.py clear_org_rate_limit_cache --org-id acme-corp
python manage.py get_org_rate_limit acme-corp
```

### Issue: Default limit change not picked up

**Cause**: Cache still holds old default for orgs without custom limits

**Solution**:
```bash
# Clear ALL organization caches
python manage.py clear_org_rate_limit_cache --all
```

### Issue: Redis connection errors

**Behavior**: System fails open - requests are allowed

**Check**:
1. Redis connectivity: `redis-cli ping`
2. Application logs for connection errors

**Solution**:
1. Fix Redis connection
2. No action needed for rate limiting - it's working as designed (fail-open)

### Issue: Lock acquisition failures

**Symptoms**: Logs show "Failed to acquire rate limit lock"

**Cause**: High contention (many concurrent requests from same org)

**Solution**:
1. Increase `API_DEPLOYMENT_RATE_LIMIT_LOCK_BLOCKING_TIMEOUT` (default: 5s)
2. Or increase org limit if legitimate traffic

### Issue: Performance concerns with cache

**Expected behavior**:
- Cache hit: <1ms (no DB query)
- Cache miss: 10-20ms (DB query + cache set)
- ~95% cache hit rate for active organizations

**Monitor**:
```bash
# Check cache behavior
python manage.py get_org_rate_limit acme-corp  # Should show "Cached Limit: X ✓"
```

## Database Schema

### OrganizationRateLimit Model

```python
class OrganizationRateLimit(BaseModel):
    id = UUIDField(primary_key=True)
    organization = ForeignKey(Organization)
    concurrent_request_limit = IntegerField(default=5)
    created_at = DateTimeField(auto_now_add=True)
    modified_at = DateTimeField(auto_now=True)
```

**Migration**: `backend/api_v2/migrations/0003_add_organization_rate_limit.py`

## Performance Characteristics

### Latency Impact

Per API request:
- **Cache hit** (most common): +1-2ms
- **Cache miss**: +10-20ms (includes DB query)
- **Lock acquisition**: +5-10ms (Redis roundtrip)
- **Total overhead**: ~15-30ms per request

### Scalability

- **Per-org locks**: No contention between organizations
- **Global limit check**: No lock (eventual consistency acceptable)
- **Redis ZSET operations**: O(log N) where N = active executions
- **Cache**: Reduces DB load by ~95%

### Resource Usage

- **Redis memory per execution**: ~100 bytes (ZSET entry + cache entry)
- **Redis memory for 1000 concurrent executions**: ~100 KB
- **Database**: 1 row per organization with custom limit (typically < 100 rows)

## Security Considerations

### Denial of Service (DoS) Prevention

The rate limiting system itself is designed to prevent DoS:
- Fail-open strategy prevents rate limiting infrastructure from becoming attack vector
- Per-org isolation prevents one org from affecting others
- Global limit prevents system-wide resource exhaustion

### Bypass Attempts

Rate limiting cannot be bypassed because:
- Enforced at application layer (before authentication/authorization)
- Uses Redis distributed locks (atomic operations)
- Cache invalidation is automatic (can't bypass by manipulating cache)

### Monitoring and Alerting

Recommended monitoring:
1. **Global limit usage**: Alert if >80% for extended periods
2. **Per-org limit usage**: Alert if >90% for important customers
3. **429 error rate**: Alert if spike occurs
4. **Redis connectivity**: Alert on connection failures

## References

### Code Locations

- **Rate limiter**: `backend/api_v2/rate_limiter.py`
- **Constants**: `backend/api_v2/rate_limit_constants.py`
- **Model**: `backend/api_v2/models.py` (`OrganizationRateLimit`)
- **View layer (entry point)**: `backend/api_v2/api_deployment_views.py` (`DeploymentExecution.post`)
- **Helper layer**: `backend/api_v2/deployment_helper.py` (`execute_workflow`)
- **Auto-release**: `backend/workflow_manager/workflow_v2/models/execution.py`
- **Management commands**: `backend/api_v2/management/commands/`

### Configuration Files

- **Environment variables**: `backend/sample.env`
- **Django settings**: `backend/backend/settings/base.py`
- **Migration**: `backend/api_v2/migrations/0003_add_organization_rate_limit.py`

### Related Documentation

- Redis ZSET documentation: https://redis.io/docs/data-types/sorted-sets/
- Django cache framework: https://docs.djangoproject.com/en/stable/topics/cache/
- HTTP 429 status code: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
