/**
 * LocalStorage cache utility for dashboard metrics.
 * Provides TTL-based caching matching backend cache TTLs.
 */

const CACHE_PREFIX = "dashboard_metrics_";

// Cache TTLs matching backend settings (in milliseconds)
const CACHE_TTL = {
  overview: 5 * 60 * 1000, // 5 minutes (DASHBOARD_CACHE_TTL_OVERVIEW)
  summary: 15 * 60 * 1000, // 15 minutes (DASHBOARD_CACHE_TTL_SUMMARY)
  series: 30 * 60 * 1000, // 30 minutes (DASHBOARD_CACHE_TTL_SERIES)
  "live-summary": 15 * 60 * 1000, // Same as summary
  "live-series": 30 * 60 * 1000, // Same as series
  workflow_token_usage: 60 * 60 * 1000, // 1 hour (DASHBOARD_CACHE_TTL_WORKFLOW_USAGE)
};

/**
 * Build a unique cache key from endpoint and params.
 *
 * @param {string} endpoint - API endpoint name
 * @param {Object} params - Query parameters
 * @return {string} Unique cache key
 */
function buildCacheKey(endpoint, params) {
  const sortedKeys = Object.keys(params).sort();
  const paramStr = sortedKeys.map((k) => `${k}=${params[k]}`).join("&");
  // Use simple encoding to avoid btoa issues with unicode
  const hash = paramStr ? `_${encodeURIComponent(paramStr)}` : "";
  return `${CACHE_PREFIX}${endpoint}${hash}`;
}

/**
 * Get cached data if valid and not expired.
 *
 * @param {string} endpoint - API endpoint name
 * @param {Object} params - Query parameters used in the request
 * @return {Object|null} Cached data or null if not found/expired
 */
function getCached(endpoint, params = {}) {
  try {
    const key = buildCacheKey(endpoint, params);
    const cached = localStorage.getItem(key);
    if (!cached) return null;

    const { data, expiry } = JSON.parse(cached);
    if (Date.now() > expiry) {
      localStorage.removeItem(key);
      return null;
    }
    return data;
  } catch (error) {
    // Handle JSON parse errors or other issues
    console.warn("Cache read error:", error);
    return null;
  }
}

/**
 * Store data in cache with TTL.
 *
 * @param {string} endpoint - API endpoint name
 * @param {Object} params - Query parameters used in the request
 * @param {Object} data - Data to cache
 */
function setCache(endpoint, params = {}, data) {
  try {
    const key = buildCacheKey(endpoint, params);
    const ttl = CACHE_TTL[endpoint] || CACHE_TTL.summary;
    const entry = {
      data,
      expiry: Date.now() + ttl,
      timestamp: Date.now(),
    };
    localStorage.setItem(key, JSON.stringify(entry));
  } catch (error) {
    // Handle localStorage quota errors
    console.warn("Cache write error:", error);
    // Try to clear old cache entries if quota exceeded
    if (error.name === "QuotaExceededError") {
      clearMetricsCache();
    }
  }
}

/**
 * Clear all metrics cache entries.
 * Useful when user manually refreshes or on logout.
 */
function clearMetricsCache() {
  try {
    const keys = Object.keys(localStorage).filter((k) =>
      k.startsWith(CACHE_PREFIX)
    );
    keys.forEach((k) => localStorage.removeItem(k));
  } catch (error) {
    console.warn("Cache clear error:", error);
  }
}

/**
 * Get cache entry metadata (for debugging).
 *
 * @param {string} endpoint - API endpoint name
 * @param {Object} params - Query parameters
 * @return {Object|null} Cache metadata or null
 */
function getCacheInfo(endpoint, params = {}) {
  try {
    const key = buildCacheKey(endpoint, params);
    const cached = localStorage.getItem(key);
    if (!cached) return null;

    const { expiry, timestamp } = JSON.parse(cached);
    return {
      key,
      timestamp: new Date(timestamp).toISOString(),
      expiry: new Date(expiry).toISOString(),
      ttlRemaining: Math.max(0, expiry - Date.now()),
      isExpired: Date.now() > expiry,
    };
  } catch (error) {
    return null;
  }
}

export { getCached, setCache, clearMetricsCache, getCacheInfo, CACHE_TTL };
