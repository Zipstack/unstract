import { useCallback, useEffect, useState } from "react";

import { getCached, setCache } from "../helpers/metricsCache";
import { useSessionStore } from "../store/session-store";
import { useAxiosPrivate } from "./useAxiosPrivate";

/**
 * Hook for fetching metrics overview (quick stats for a date range).
 * Uses localStorage caching with TTL matching backend.
 *
 * @param {string} startDate - Start date (ISO 8601, optional - defaults to 7 days ago)
 * @param {string} endDate - End date (ISO 8601, optional - defaults to now)
 * @return {Object} { data, loading, error, refetch }
 */
function useMetricsOverview(startDate = null, endDate = null) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchOverview = useCallback(
    async (skipCache = false) => {
      // Guard: don't fetch if orgId is not available
      if (!orgId) {
        setLoading(false);
        return;
      }

      setError(null);
      const cacheParams = { org: orgId, startDate, endDate };

      // Check cache first (unless skip requested)
      if (!skipCache) {
        const cached = getCached("overview", cacheParams);
        if (cached) {
          setData(cached);
          setLoading(false);
          return;
        }
      }

      setLoading(true);

      try {
        const params = new URLSearchParams();
        if (startDate) {
          params.append("start_date", startDate);
        }
        if (endDate) {
          params.append("end_date", endDate);
        }

        const url = `/api/v1/unstract/${orgId}/metrics/overview/${
          params.toString() ? `?${params}` : ""
        }`;
        const response = await axiosPrivate.get(url);
        setData(response.data);
        // Cache the response
        setCache("overview", cacheParams, response.data);
      } catch (err) {
        setError(err.response?.data?.message || "Failed to fetch overview");
      } finally {
        setLoading(false);
      }
    },
    [axiosPrivate, orgId, startDate, endDate],
  );

  useEffect(() => {
    if (orgId) {
      fetchOverview();
    } else {
      setData(null);
      setLoading(false);
      setError(null);
    }
  }, [orgId, startDate, endDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // refetch bypasses cache
  const refetch = useCallback(() => fetchOverview(true), [fetchOverview]);

  return { data, loading, error, refetch };
}

/**
 * Hook for fetching recent processing activity.
 * Real-time data - no caching.
 *
 * @param {number} limit - Maximum records to return (default 10)
 * @return {Object} { data, loading, error, refetch }
 */
function useRecentActivity(limit = 10) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchActivity = useCallback(async () => {
    if (!orgId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const url = `/api/v1/unstract/${orgId}/metrics/recent-activity/?limit=${limit}`;
      const response = await axiosPrivate.get(url);
      setData(response.data);
    } catch (err) {
      setError(err.response?.data?.message || "Failed to fetch activity");
    } finally {
      setLoading(false);
    }
  }, [axiosPrivate, orgId, limit]);

  useEffect(() => {
    if (orgId) {
      fetchActivity();
    } else {
      setData(null);
      setLoading(false);
      setError(null);
    }
  }, [orgId, limit]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, error, refetch: fetchActivity };
}

/**
 * Hook for fetching LLM token usage grouped by deployment type.
 * Uses localStorage caching with 1-hour TTL per deployment type.
 * Supports manual refresh that bypasses both frontend and backend caches.
 *
 * @param {string} deploymentType - One of "API", "ETL", "TASK", "WF"
 * @param {string} startDate - Start date (ISO 8601)
 * @param {string} endDate - End date (ISO 8601)
 * @return {Object} { data, loading, error, refetch }
 */
function useDeploymentUsage(deploymentType, startDate, endDate) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchUsage = useCallback(
    async (skipCache = false) => {
      if (!orgId || !deploymentType || !startDate || !endDate) {
        setLoading(false);
        return;
      }

      setError(null);
      const cacheKey = `deployment_usage_${deploymentType}`;
      const cacheParams = { org: orgId, deploymentType, startDate, endDate };

      // Check cache first (unless skip requested)
      if (!skipCache) {
        const cached = getCached(cacheKey, cacheParams);
        if (cached) {
          setData(cached);
          setLoading(false);
          return;
        }
      }

      setLoading(true);

      try {
        const params = new URLSearchParams();
        params.append("start_date", startDate);
        params.append("end_date", endDate);
        params.append("deployment_type", deploymentType);
        if (skipCache) {
          params.append("refresh", "true");
        }
        const url = `/api/v1/unstract/${orgId}/metrics/workflow-token-usage/?${params}`;
        const response = await axiosPrivate.get(url);
        setData(response.data);
        setCache(cacheKey, cacheParams, response.data);
      } catch (err) {
        setError(
          err.response?.data?.message || "Failed to fetch deployment usage",
        );
      } finally {
        setLoading(false);
      }
    },
    [axiosPrivate, orgId, deploymentType, startDate, endDate],
  );

  useEffect(() => {
    if (orgId && deploymentType && startDate && endDate) {
      fetchUsage();
    } else {
      setData(null);
      setLoading(false);
      setError(null);
    }
  }, [orgId, deploymentType, startDate, endDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // refetch bypasses both frontend and backend caches
  const refetch = useCallback(() => fetchUsage(true), [fetchUsage]);

  return { data, loading, error, refetch };
}

/**
 * Hook for fetching subscription usage data (cloud-only).
 * Calls /subscription/usage/ and /subscription/usage/daily/ endpoints.
 * Returns null gracefully on OSS where these endpoints don't exist.
 *
 * @return {Object} { data, loading, error, refetch }
 */
function useSubscriptionUsage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchUsage = useCallback(async () => {
    if (!orgId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const baseUrl = `/api/v1/unstract/${orgId}`;
      const [totalRes, dailyRes] = await Promise.all([
        axiosPrivate.get(`${baseUrl}/subscription/usage/`),
        axiosPrivate.get(`${baseUrl}/subscription/usage/daily/`),
      ]);

      const totalPages = totalRes.data?.usage_data?.pages_processed || 0;
      const dailyUsage = (dailyRes.data?.usage_data?.usage || []).map(
        (item) => ({
          key: item.record_date,
          pagesExtracted: item.pages_processed,
          date: item.record_date,
        }),
      );

      setData({ totalPages, dailyUsage });
    } catch (err) {
      // 404 = endpoints don't exist (OSS) — not an error, just no data
      if (err.response?.status === 404) {
        setData(null);
      } else {
        setError(
          err.response?.data?.message || "Failed to fetch subscription usage",
        );
      }
    } finally {
      setLoading(false);
    }
  }, [axiosPrivate, orgId]);

  useEffect(() => {
    if (orgId) {
      fetchUsage();
    } else {
      setData(null);
      setLoading(false);
      setError(null);
    }
  }, [orgId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, error, refetch: fetchUsage };
}

export {
  useDeploymentUsage,
  useMetricsOverview,
  useRecentActivity,
  useSubscriptionUsage,
};
