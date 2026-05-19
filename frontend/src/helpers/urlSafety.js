const SAFE_URL_SCHEMES = ["http:", "https:", "mailto:", "tel:"];

// Block unsafe schemes (e.g. `javascript:`, `data:`) in user/tool-derived links.
const isSafeExternalUrl = (url) => {
  if (typeof url !== "string" || url === "") {
    return false;
  }
  // No base URL — bare strings ("javascript", "../foo") must fail rather than
  // silently resolve to the current origin.
  try {
    const parsed = new URL(url);
    return SAFE_URL_SCHEMES.includes(parsed.protocol);
  } catch {
    return false;
  }
};

export { isSafeExternalUrl, SAFE_URL_SCHEMES };
