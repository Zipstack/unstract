import { useState, useEffect, useCallback } from "react";

import {
  getCached,
  setCache,
  clearMetricsCache,
} from "../helpers/metricsCache";
import { useAxiosPrivate } from "./useAxiosPrivate";
import { useSessionStore } from "../store/session-store";

/**
 * Hook for fetching dashboard metrics data from the API.
 *
 * @param {Object} options - Query options
 * @param {string} options.startDate - Start date (ISO 8601)
 * @param {string} options.endDate - End date (ISO 8601)
 * @param {string} options.granularity - Time granularity (hour, day, week)
 * @param {string} options.metricName - Filter by specific metric
 * @return {Object} { data, loading, error, refetch }
 */
function useMetricsData(options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchMetrics = useCallback(
    async (endpoint = "overview") => {
      // Guard: don't fetch if orgId is not available
      if (!orgId) {
        setLoading(false);
        return null;
      }

      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams();
        if (options.startDate) params.append("start_date", options.startDate);
        if (options.endDate) params.append("end_date", options.endDate);
        if (options.granularity)
          params.append("granularity", options.granularity);
        if (options.metricName)
          params.append("metric_name", options.metricName);

        const url = `/api/v1/unstract/${orgId}/metrics/${endpoint}/${
          params.toString() ? `?${params}` : ""
        }`;

        const response = await axiosPrivate.get(url);
        setData(response.data);
        return response.data;
      } catch (err) {
        const errorMessage =
          err.response?.data?.message ||
          err.message ||
          "Failed to fetch metrics";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [axiosPrivate, options, orgId]
  );

  const refetch = useCallback(() => {
    return fetchMetrics("overview");
  }, [fetchMetrics]);

  return { data, loading, error, refetch, fetchMetrics };
}

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
    }
  }, [orgId, startDate, endDate]); // eslint-disable-line

  // refetch bypasses cache
  const refetch = useCallback(() => fetchOverview(true), [fetchOverview]);

  return { data, loading, error, refetch };
}

/**
 * Hook for fetching metrics summary with date range.
 * Uses localStorage caching with TTL matching backend.
 *
 * @param {string} startDate - Start date (ISO 8601)
 * @param {string} endDate - End date (ISO 8601)
 * @param {string} metricName - Filter by specific metric (optional)
 * @param {string} source - Data source: 'auto', 'hourly', 'daily', 'monthly' (default: 'auto')
 * @return {Object} { data, loading, error, refetch }
 */
function useMetricsSummary(
  startDate,
  endDate,
  metricName = null,
  source = "auto"
) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchSummary = useCallback(
    async (skipCache = false) => {
      // Guard: don't fetch if required params are missing
      if (!startDate || !endDate || !orgId) {
        setLoading(false);
        return;
      }

      setError(null);
      const endpoint = "summary";
      const cacheParams = {
        org: orgId,
        startDate,
        endDate,
        metricName,
        source,
      };

      // Check cache first (unless skip requested)
      if (!skipCache) {
        const cached = getCached(endpoint, cacheParams);
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
        if (metricName) params.append("metric_name", metricName);
        if (source) params.append("source", source);

        const url = `/api/v1/unstract/${orgId}/metrics/${endpoint}/?${params}`;
        const response = await axiosPrivate.get(url);
        setData(response.data);
        // Cache the response
        setCache(endpoint, cacheParams, response.data);
      } catch (err) {
        setError(err.response?.data?.message || "Failed to fetch summary");
      } finally {
        setLoading(false);
      }
    },
    [axiosPrivate, startDate, endDate, metricName, source, orgId]
  );

  useEffect(() => {
    if (startDate && endDate && orgId) {
      fetchSummary();
    }
  }, [orgId, startDate, endDate, metricName, source]); // eslint-disable-line

  // refetch bypasses cache
  const refetch = useCallback(() => fetchSummary(true), [fetchSummary]);

  return { data, loading, error, refetch };
}

/**
 * Hook for fetching metrics time series.
 * Uses localStorage caching with TTL matching backend.
 *
 * @param {string} startDate - Start date (ISO 8601)
 * @param {string} endDate - End date (ISO 8601)
 * @param {string} granularity - Time granularity (hour, day, week)
 * @param {string} source - Data source: 'auto', 'hourly', 'daily', 'monthly' (default: 'auto')
 * @return {Object} { data, loading, error, refetch }
 */
function useMetricsSeries(
  startDate,
  endDate,
  granularity = "day",
  source = "auto"
) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const orgId = sessionDetails?.orgId;

  const fetchSeries = useCallback(
    async (skipCache = false) => {
      // Guard: don't fetch if required params are missing
      if (!startDate || !endDate || !orgId) {
        setLoading(false);
        return;
      }

      setError(null);
      const endpoint = "series";
      const cacheParams = {
        org: orgId,
        startDate,
        endDate,
        granularity,
        source,
      };

      // Check cache first (unless skip requested)
      if (!skipCache) {
        const cached = getCached(endpoint, cacheParams);
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
        params.append("granularity", granularity);
        if (source) params.append("source", source);

        const url = `/api/v1/unstract/${orgId}/metrics/${endpoint}/?${params}`;
        const response = await axiosPrivate.get(url);
        setData(response.data);
        // Cache the response
        setCache(endpoint, cacheParams, response.data);
      } catch (err) {
        setError(err.response?.data?.message || "Failed to fetch series");
      } finally {
        setLoading(false);
      }
    },
    [axiosPrivate, startDate, endDate, granularity, source, orgId]
  );

  useEffect(() => {
    if (startDate && endDate && orgId) {
      fetchSeries();
    }
  }, [orgId, startDate, endDate, granularity, source]); // eslint-disable-line

  // refetch bypasses cache
  const refetch = useCallback(() => fetchSeries(true), [fetchSeries]);

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
    }
  }, [orgId, limit]); // eslint-disable-line

  return { data, loading, error, refetch: fetchActivity };
}

export {
  useMetricsData,
  useMetricsOverview,
  useMetricsSummary,
  useMetricsSeries,
  useRecentActivity,
  clearMetricsCache,
};
