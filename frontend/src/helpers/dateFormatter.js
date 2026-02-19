import {
  format,
  formatDistanceToNow,
  isToday,
  isYesterday,
  isThisWeek,
  differenceInHours,
  differenceInMinutes,
  parseISO,
  isValid,
} from "date-fns";

/**
 * Format options for the date formatter
 * @typedef {Object} DateFormatOptions
 * @property {boolean} [includeTime=false] - Include time in the output
 * @property {boolean} [relative=false] - Use relative formatting for recent dates
 * @property {number} [relativeThreshold=24] - Hours threshold for relative formatting
 */

/**
 * Format an ISO date string to a compact, human-readable format
 *
 * @param {string} isoDate - ISO 8601 date string
 * @param {DateFormatOptions} [options={}] - Formatting options
 * @return {string} Formatted date string
 *
 * @example
 * // Standard format
 * formatCompactDate("2024-01-12T14:30:00Z") // "12 Jan 2024"
 *
 * @example
 * // With time
 * formatCompactDate("2024-01-12T14:30:00Z", { includeTime: true }) // "12 Jan 2024 14:30"
 *
 * @example
 * // Relative (if within threshold)
 * formatCompactDate(recentDate, { relative: true }) // "2 hours ago"
 */
function formatCompactDate(isoDate, options = {}) {
  const {
    includeTime = false,
    relative = false,
    relativeThreshold = 24,
  } = options;

  if (!isoDate) {
    return "-";
  }

  let date;
  try {
    date = typeof isoDate === "string" ? parseISO(isoDate) : new Date(isoDate);
    if (!isValid(date)) {
      return isoDate; // Return raw value if invalid
    }
  } catch {
    return isoDate; // Return raw value on parse error
  }

  const now = new Date();

  // Handle relative formatting for recent dates
  if (relative) {
    const hoursAgo = differenceInHours(now, date);
    const minutesAgo = differenceInMinutes(now, date);

    // "Just now" for < 1 minute
    if (minutesAgo < 1) {
      return "Just now";
    }

    // Relative format within threshold
    if (hoursAgo < relativeThreshold) {
      return formatDistanceToNow(date, { addSuffix: true });
    }

    // Yesterday with time
    if (isYesterday(date)) {
      return `Yesterday ${format(date, "HH:mm")}`;
    }

    // This week - show day name with time
    if (isThisWeek(date, { weekStartsOn: 1 })) {
      return format(date, "EEEE HH:mm");
    }
  }

  // Standard formatting
  if (includeTime) {
    return format(date, "dd MMM yyyy HH:mm");
  }

  return format(date, "dd MMM yyyy");
}

/**
 * Format a date to show relative time if recent, absolute otherwise
 *
 * @param {string} isoDate - ISO 8601 date string
 * @return {string} Formatted date string with smart relative/absolute switching
 */
function formatSmartDate(isoDate) {
  return formatCompactDate(isoDate, { relative: true, includeTime: true });
}

/**
 * Format a date for display in tooltips (full date and time)
 *
 * @param {string} isoDate - ISO 8601 date string
 * @return {string} Full formatted date string
 */
function formatFullDate(isoDate) {
  if (!isoDate) {
    return "-";
  }

  let date;
  try {
    date = typeof isoDate === "string" ? parseISO(isoDate) : new Date(isoDate);
    if (!isValid(date)) {
      return isoDate;
    }
  } catch {
    return isoDate;
  }

  return format(date, "EEEE, dd MMMM yyyy 'at' HH:mm:ss");
}

/**
 * Check if a date is today
 *
 * @param {string} isoDate - ISO 8601 date string
 * @return {boolean} True if the date is today
 */
function checkIsToday(isoDate) {
  if (!isoDate) return false;
  try {
    const date =
      typeof isoDate === "string" ? parseISO(isoDate) : new Date(isoDate);
    return isValid(date) && isToday(date);
  } catch {
    return false;
  }
}

export { formatCompactDate, formatSmartDate, formatFullDate, checkIsToday };
