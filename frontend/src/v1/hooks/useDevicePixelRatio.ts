import { useEffect, useState } from "react";

function currentRatio(): number {
  return typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
}

/**
 * The screen's device pixel ratio, kept current: it changes when the window
 * moves to a screen with another density or the browser zoom changes, and a
 * canvas drawn at the old ratio would then look blurry.
 */
export function useDevicePixelRatio(): number {
  const [ratio, setRatio] = useState(currentRatio);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    // A query matches one ratio only, so it is replaced on every change.
    const query = window.matchMedia(`(resolution: ${ratio}dppx)`);
    const onChange = () => setRatio(currentRatio());
    query.addEventListener("change", onChange);
    // The ratio may have moved between the render and this effect.
    onChange();
    return () => query.removeEventListener("change", onChange);
  }, [ratio]);
  return ratio;
}
