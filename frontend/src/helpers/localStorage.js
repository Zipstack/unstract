/**
 * Safe localStorage utilities with SSR/test environment support
 */

const isLocalStorageAvailable = () => {
  try {
    return typeof localStorage !== "undefined";
  } catch {
    return false;
  }
};

export const getLocalStorageValue = (key, defaultValue) => {
  if (!isLocalStorageAvailable()) return defaultValue;
  try {
    const item = localStorage.getItem(key);
    return item ? JSON.parse(item) : defaultValue;
  } catch {
    try {
      localStorage.removeItem(key);
    } catch {
      // Ignore storage errors
    }
    return defaultValue;
  }
};

export const setLocalStorageValue = (key, value) => {
  if (!isLocalStorageAvailable()) return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage errors
  }
};
