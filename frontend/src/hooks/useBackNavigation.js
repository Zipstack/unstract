import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/*
  Generic back-navigation for pages reached from multiple callsites.

  Priority:
   1. location.state.from   — explicit hint from the linking page (also
      reinjects scrollToCardId / backRouteState so list pages can restore
      scroll position on return).
   2. navigate(-1)          — SPA history exists; pop one entry. Covers
      callsites that didn't set state (e.g. markdown links in alerts).
   3. fallbackPath          — deep link / refresh with no history.
*/
function useBackNavigation(fallbackPath, fallbackState = null) {
  const navigate = useNavigate();
  const location = useLocation();

  return useCallback(() => {
    const explicitFrom = location.state?.from;
    if (explicitFrom) {
      const restoredState = location.state?.scrollToCardId
        ? {
            scrollToCardId: location.state.scrollToCardId,
            cardExpanded: location.state.cardExpanded,
          }
        : location.state?.backRouteState || null;
      navigate(explicitFrom, { state: restoredState });
      return;
    }
    if (location.key !== "default") {
      navigate(-1);
      return;
    }
    if (fallbackPath) {
      navigate(fallbackPath, { state: fallbackState });
    }
  }, [location.key, location.state, navigate, fallbackPath, fallbackState]);
}

export { useBackNavigation };
