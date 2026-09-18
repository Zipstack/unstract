import { useEffect, useState } from "react";

// How long a Stop may sit unresolved before the UI admits that the step
// already in flight is still finishing. Abandoning a call normally lands in a
// second or two, so anything past this is the honest exception: an adapter
// that ignores cancellation, or a stage with no way back out (UN-1031).
const LINGERING_STOP_MS = 30 * 1000;

/**
 * True once a Stop has been pending for longer than users should be asked to
 * watch a spinner without explanation.
 *
 * @param {boolean} isStopping Whether a Stop is currently outstanding.
 * @returns {boolean} Whether it has been outstanding long enough to say so.
 */
const useLingeringStop = (isStopping) => {
  const [isLingering, setIsLingering] = useState(false);

  useEffect(() => {
    if (!isStopping) {
      setIsLingering(false);
      return undefined;
    }
    const timer = setTimeout(() => setIsLingering(true), LINGERING_STOP_MS);
    return () => clearTimeout(timer);
  }, [isStopping]);

  return isLingering;
};

export { LINGERING_STOP_MS, useLingeringStop };
