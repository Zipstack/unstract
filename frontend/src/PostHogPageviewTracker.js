import { usePostHog } from "posthog-js/react";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const PostHogPageviewTracker = () => {
  const location = useLocation();
  const posthog = usePostHog();
  const timeoutRef = useRef(null);

  useEffect(() => {
    // Clear any pending pageview capture
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Debounce pageview capture to avoid rapid-fire requests
    // This prevents multiple pageviews when navigating quickly
    timeoutRef.current = setTimeout(() => {
      if (posthog) {
        try {
          // Use non-blocking capture
          posthog.capture("$pageview", {
            $current_url: window.location.href,
            $pathname: location.pathname,
          });
        } catch (error) {
          // Silently fail - don't block app functionality
          console.debug("PostHog pageview capture failed:", error);
        }
      }
    }, 300); // 300ms debounce

    // Cleanup timeout on unmount
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [location, posthog]);

  return null;
};

export default PostHogPageviewTracker;
