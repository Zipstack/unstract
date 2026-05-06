const SAFE_URL_SCHEMES = ["http:", "https:", "mailto:", "tel:"];

// Guards against unsafe schemes (e.g. `javascript:`, `data:`) when
// rendering links built from user- or tool-derived content.
const isSafeExternalUrl = (url) => {
  if (typeof url !== "string" || url === "") {
    return false;
  }
  // Parse without a base so bare strings (e.g. "javascript", "../foo") fail
  // instead of silently resolving to `https://<origin>/...` and passing.
  try {
    const parsed = new URL(url);
    return SAFE_URL_SCHEMES.includes(parsed.protocol);
  } catch {
    return false;
  }
};

export { isSafeExternalUrl, SAFE_URL_SCHEMES };
