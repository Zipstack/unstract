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
 * It also renders nothing — and now goes nowhere — when `to` is falsy.
 * `propTypes.isRequired` is a development-only warning, not a guard, so
 * without the check below a missing destination became
 * `window.location.assign(undefined)`, which navigates to `/undefined`
 * rather than failing (Wicky, review on #2475). Callers are expected to
 * decide BEFORE rendering this — `RequireGuest` does, and so must any
 * future one — so the guard is a backstop rather than a supported way to
 * call it. A missing destination there means the caller's own answer was
 * wrong, and staying put is the recoverable half of that.
 *
 * `assign`, not `replace`: the visitor is leaving this app, so Back should
 * bring them back to it rather than to whatever preceded it.
 */
function ExternalRedirect({ to }) {
  useEffect(() => {
    if (!to) {
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
