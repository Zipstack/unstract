import { useState, useEffect, useCallback } from "react";

import { getCached, setCache } from "../helpers/metricsCache";
import { useAxiosPrivate } from "./useAxiosPrivate";
import { useSessionStore } from "../store/session-store";

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
        if (startDate) params.append("start_date", startDate);
        if (endDate) params.append("end_date", endDate);

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
    [axiosPrivate, orgId, startDate, endDate]
  );

  useEffect(() => {
    if (orgId) {
      fetchOverview();
    } else {
      setData(null);
      setLoading(false);
      setError(null);
    }
  }, [orgId, startDate, endDate]); // eslint-disable-line

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
  }, [orgId, limit]); // eslint-disable-line

  return { data, loading, error, refetch: fetchActivity };
}

/**
 * Hook for fetching per-workflow LLM token usage.
 * Uses localStorage caching with 1-hour TTL. Supports manual refresh
 * that bypasses both frontend and backend caches.
 *
 * @param {string} startDate - Start date (ISO 8601)
 * @param {string} endDate - End date (ISO 8601)
 * @return {Object} { data, loading, error, refetch }
 */
function useWorkflowTokenUsage(startDate, endDate) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchUsage = useCallback(
    async (skipCache = false) => {
      if (!orgId || !startDate || !endDate) {
        setLoading(false);
        return;
      }

      setError(null);
      const cacheParams = { org: orgId, startDate, endDate };

      // Check cache first (unless skip requested)
      if (!skipCache) {
        const cached = getCached("workflow_token_usage", cacheParams);
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
        if (skipCache) params.append("refresh", "true");
        const url = `/api/v1/unstract/${orgId}/metrics/workflow-token-usage/?${params}`;
        const response = await axiosPrivate.get(url);
        setData(response.data);
        setCache("workflow_token_usage", cacheParams, response.data);
      } catch (err) {
        setError(
          err.response?.data?.message || "Failed to fetch workflow token usage"
        );
      } finally {
        setLoading(false);
      }
    },
    [axiosPrivate, orgId, startDate, endDate]
  );

  useEffect(() => {
    if (orgId && startDate && endDate) {
      fetchUsage();
    } else {
      setData(null);
      setLoading(false);
      setError(null);
    }
  }, [orgId, startDate, endDate]); // eslint-disable-line

  // refetch bypasses both frontend and backend caches
  const refetch = useCallback(() => fetchUsage(true), [fetchUsage]);

  return { data, loading, error, refetch };
}

export { useMetricsOverview, useRecentActivity, useWorkflowTokenUsage };
