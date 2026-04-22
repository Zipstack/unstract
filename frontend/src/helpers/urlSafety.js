const SAFE_URL_SCHEMES = ["http:", "https:", "mailto:", "tel:"];

// Guards against unsafe schemes (e.g. `javascript:`, `data:`) when
// rendering links built from user- or tool-derived content.
const isSafeExternalUrl = (url) => {
  if (!url) {
    return false;
  }
  try {
    const parsed = new URL(url, window.location.origin);
    return SAFE_URL_SCHEMES.includes(parsed.protocol);
  } catch {
    return false;
  }
};

export { isSafeExternalUrl, SAFE_URL_SCHEMES };
