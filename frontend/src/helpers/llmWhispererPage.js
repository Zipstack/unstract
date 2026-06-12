let SELECTED_PRODUCT_PAGE;
let LLM_WHISPERER_PAGES = [];
try {
  const commonMod = await import("../plugins/helpers/common");
  SELECTED_PRODUCT_PAGE = commonMod.SELECTED_PRODUCT_PAGE;
  LLM_WHISPERER_PAGES = commonMod.LLM_WHISPERER_PAGES ?? [];
} catch {
  // Plugins are not available in the OSS build
}

/**
 * Resolves which LLMWhisperer portal page to redirect to after login.
 *
 * The `selectedProductPage` query param (e.g. from adapter helper-text deep
 * links like /landing?selectedProduct=llm-whisperer&selectedProductPage=api-keys)
 * takes priority over the value persisted in the product store, since store
 * persistence happens in an effect that may not have run before the redirect
 * is rendered. Only whitelisted page slugs are honored.
 *
 * @param {string} search - `location.search` of the current route
 * @param {string|null} storedPage - `selectedProductPage` from the product store
 * @returns {string} a safe page slug, defaulting to "playground"
 */
function getLlmWhispererPage(search, storedPage) {
  const pageQueryParam = SELECTED_PRODUCT_PAGE
    ? new URLSearchParams(search).get(SELECTED_PRODUCT_PAGE)
    : null;
  return (
    [pageQueryParam, storedPage].find((page) =>
      LLM_WHISPERER_PAGES.includes(page),
    ) || "playground"
  );
}

export { getLlmWhispererPage };
