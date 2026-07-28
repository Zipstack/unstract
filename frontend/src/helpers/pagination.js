/**
 * Helpers for list endpoints that may or may not be paginated.
 *
 * The shared resource endpoints (workflows, prompt studio, adapters,
 * connectors) return a bare array unless the caller opts into pagination, and
 * a `{count, next, previous, results}` envelope once it does. Callers should
 * not care which they got.
 */

/**
 * Rows out of a list response, whichever shape it arrived in.
 *
 * @param {Object} res - axios response
 * @return {Array} the rows, or [] when the payload is neither shape
 */
function unwrapList(res) {
  const data = res?.data;
  if (Array.isArray(data)) {
    return data;
  }
  return Array.isArray(data?.results) ? data.results : [];
}

/**
 * Every row of a list endpoint, following pagination to exhaustion.
 *
 * For selectors and dropdowns, which must show the full set — reading only the
 * first page would silently hide entries with no error. Pages are requested by
 * number rather than by following `next`, so the call keeps going through the
 * caller's axios instance (base URL, auth interceptors) instead of a
 * server-built absolute URL.
 *
 * @param {Object} axiosInstance - an axios instance (e.g. from useAxiosPrivate)
 * @param {Object} config - axios request config; `url` is required
 * @return {Promise<Array>} all rows across all pages
 */
async function fetchAllPages(axiosInstance, config) {
  const request = (params) =>
    axiosInstance({ ...config, method: "GET", ...(params ? { params } : {}) });

  const first = await request();
  if (Array.isArray(first?.data)) {
    return first.data;
  }

  const rows = [...(first?.data?.results ?? [])];
  const total = first?.data?.count ?? rows.length;
  let page = 1;
  while (rows.length < total) {
    page += 1;
    const res = await request({ ...(config?.params ?? {}), page });
    const nextRows = res?.data?.results ?? [];
    // A page that adds nothing would otherwise spin forever on a bad count.
    if (!nextRows.length) {
      break;
    }
    rows.push(...nextRows);
  }
  return rows;
}

export { fetchAllPages, unwrapList };
