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
 * `assign`, not `replace`: the visitor is leaving this app, so Back should
 * bring them back to it rather than to whatever preceded it.
 */
function ExternalRedirect({ to }) {
  useEffect(() => {
    window.location.assign(to);
  }, [to]);
  return null;
}

ExternalRedirect.propTypes = {
  to: PropTypes.string.isRequired,
};

export { ExternalRedirect };
