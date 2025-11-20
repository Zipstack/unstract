export const formatDate = (dateString) => {
  if (!dateString) return "N/A";
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const rounded = Math.round((bytes / Math.pow(k, i)) * 100) / 100;
  return rounded + " " + sizes[i];
};

export const formatAccuracy = (accuracy) => {
  if (accuracy === null || accuracy === undefined) return "N/A";
  return `${accuracy.toFixed(1)}%`;
};

export const getStatusColor = (status) => {
  const colorMap = {
    complete: "success",
    processing: "processing",
    pending: "default",
    error: "error",
    match: "success",
    partial: "warning",
    mismatch: "error",
    queued: "default",
    started: "processing",
    finished: "success",
    failed: "error",
  };
  return colorMap[status] || "default";
};

export const getStatusText = (status) => {
  if (!status) return "Unknown";
  return status.charAt(0).toUpperCase() + status.slice(1);
};

export const flattenObject = (obj, prefix = "") => {
  const flattened = {};

  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const newKey = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(flattened, flattenObject(value, newKey));
    } else {
      flattened[newKey] = value;
    }
  });

  return flattened;
};

export const getValueByPath = (obj, path) => {
  if (!obj || !path) return undefined;
  return path.split(".").reduce((acc, part) => {
    // Handle array indices like "items[0]"
    const arrayMatch = part.match(/(\w+)\[(\d+)\]/);
    if (arrayMatch) {
      const [, key, index] = arrayMatch;
      return acc?.[key]?.[parseInt(index, 10)];
    }
    return acc?.[part];
  }, obj);
};

export const setValueByPath = (obj, path, value) => {
  const keys = path.split(".");
  const lastKey = keys.pop();
  const target = keys.reduce((acc, key) => {
    if (!acc[key]) acc[key] = {};
    return acc[key];
  }, obj);
  target[lastKey] = value;
  return obj;
};

export const deepClone = (obj) => {
  if (obj === null || typeof obj !== "object") return obj;
  if (obj instanceof Date) return new Date(obj);
  if (obj instanceof Array) return obj.map((item) => deepClone(item));

  const cloned = {};
  Object.keys(obj).forEach((key) => {
    cloned[key] = deepClone(obj[key]);
  });
  return cloned;
};

export const isEqual = (val1, val2) => {
  if (val1 === val2) return true;
  if (
    val1 === null ||
    val1 === undefined ||
    val2 === null ||
    val2 === undefined
  )
    return val1 === val2;
  if (typeof val1 !== typeof val2) return false;

  if (typeof val1 === "object") {
    if (Array.isArray(val1) && Array.isArray(val2)) {
      if (val1.length !== val2.length) return false;
      return val1.every((item, index) => isEqual(item, val2[index]));
    }

    const keys1 = Object.keys(val1);
    const keys2 = Object.keys(val2);
    if (keys1.length !== keys2.length) return false;

    return keys1.every((key) => isEqual(val1[key], val2[key]));
  }

  return false;
};

export const calculateAccuracy = (extracted, verified) => {
  if (!extracted || !verified) return { accuracy: 0, matches: 0, total: 0 };

  const flatExtracted = flattenObject(extracted);
  const flatVerified = flattenObject(verified);

  const allKeys = new Set([
    ...Object.keys(flatExtracted),
    ...Object.keys(flatVerified),
  ]);

  let matches = 0;
  const total = allKeys.size;

  allKeys.forEach((key) => {
    if (isEqual(flatExtracted[key], flatVerified[key])) {
      matches++;
    }
  });

  const accuracy = total > 0 ? (matches / total) * 100 : 0;

  return { accuracy, matches, total };
};

export const truncateText = (text, maxLength = 50) => {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "...";
};

export const debounce = (func, wait = 300) => {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
};

export const isValidJSON = (str) => {
  try {
    JSON.parse(str);
    return true;
  } catch (e) {
    return false;
  }
};

export const prettyJSON = (obj) => {
  try {
    return JSON.stringify(obj, null, 2);
  } catch (e) {
    return String(obj);
  }
};

export const parseFieldPath = (path) => {
  if (!path) return [];
  return path.split(".").map((part) => {
    const arrayMatch = part.match(/(\w+)\[(\d+)\]/);
    if (arrayMatch) {
      return {
        key: arrayMatch[1],
        index: parseInt(arrayMatch[2], 10),
        isArray: true,
      };
    }
    return { key: part, isArray: false };
  });
};

export const generateId = (prefix = "id") => {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};

export const downloadFile = (content, filename, contentType = "text/plain") => {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // Fallback for older browsers
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand("copy");
      document.body.removeChild(textArea);
      return true;
    } catch (err) {
      document.body.removeChild(textArea);
      return false;
    }
  }
};

export const groupBy = (array, key) => {
  return array.reduce((result, item) => {
    const groupKey = typeof key === "function" ? key(item) : item[key];
    if (!result[groupKey]) {
      result[groupKey] = [];
    }
    result[groupKey].push(item);
    return result;
  }, {});
};

export const sortBy = (array, key, order = "asc") => {
  return [...array].sort((a, b) => {
    const aVal = typeof key === "function" ? key(a) : a[key];
    const bVal = typeof key === "function" ? key(b) : b[key];

    if (aVal < bVal) return order === "asc" ? -1 : 1;
    if (aVal > bVal) return order === "asc" ? 1 : -1;
    return 0;
  });
};

export const searchFilter = (array, searchTerm) => {
  if (!searchTerm) return array;
  const term = searchTerm.toLowerCase();

  return array.filter((item) => {
    return Object.values(item).some((value) => {
      if (typeof value === "string") {
        return value.toLowerCase().includes(term);
      }
      return false;
    });
  });
};
