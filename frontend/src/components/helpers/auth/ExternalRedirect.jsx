import PropTypes from "prop-types";
import { useEffect } from "react";

/**
 * Leaves this app for an address it does not serve.
 *
 * `<Navigate>` cannot do this: it hands the path to the router, which has
 * no route for an address belonging to a different app and renders its
 * catch-all instead. A real navigation is the only mechanism, and it has
 * to happen in an effect rather than during render.
 *
 * Renders nothing while the browser leaves. Rendering anything would flash
 * a page the visitor is not going to stay on, and anything that navigates
 * would race this.
 *
 * It also renders nothing — and goes nowhere — when `to` is not an address
 * this app is willing to leave for. `propTypes.isRequired` is a
 * development-only warning, not a guard, so without the check below a
 * missing destination became `window.location.assign(undefined)`, which
 * navigates to `/undefined` rather than failing (review on #2475, 2026-10).
 * Callers are expected to decide BEFORE rendering this — `RequireGuest`
 * does, and so must any future one — so the guard is a backstop rather than
 * a supported way to call it. A wrong destination there means the caller's
 * own answer was wrong, and staying put is the recoverable half of that.
 *
 * THE SHAPE CHECK IS NEW (review on #2494, 2026-11), and it is defence in
 * depth rather than a live hole: `RequireGuest` now resolves part of its
 * destination from `?selectedProduct=`, and while the plugin only ever
 * answers from a closed map of configured products, that map lives in
 * another repository and no CI here can enforce it. This file should not
 * depend on a guarantee it cannot see.
 *
 * A RELATIVE PATH MUST STILL PASS. The obvious guard — require
 * `^https?://` — would reject every real deployment: `config.flowUrl` is
 * `/flow` in the staging values and in the chart's own unit test, because
 * Flow is served under a path on the shared host rather than at its own
 * origin. So the test admits an absolute http(s) URL, or a root-relative
 * path that is not protocol-relative: `//evil.example` begins with `/` but
 * means another origin, and a value that is neither — `[object Object]`,
 * `javascript:…` — goes nowhere.
 *
 * `assign`, not `replace`: the visitor is leaving this app, so Back should
 * bring them back to it rather than to whatever preceded it.
 */
const isLeavableAddress = (to) =>
  typeof to === "string" &&
  (/^https?:\/\//i.test(to) || (to.startsWith("/") && !to.startsWith("//")));

function ExternalRedirect({ to }) {
  useEffect(() => {
    if (!isLeavableAddress(to)) {
      return;
    }
    window.location.assign(to);
  }, [to]);
  return null;
}

ExternalRedirect.propTypes = {
  to: PropTypes.string.isRequired,
};

export { ExternalRedirect };
