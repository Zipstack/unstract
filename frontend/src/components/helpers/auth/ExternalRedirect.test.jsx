import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExternalRedirect } from "./ExternalRedirect";

describe("ExternalRedirect", () => {
  let restore;

  const stubLocation = () => {
    const assign = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      value: { assign, href: "https://host/landing" },
      writable: true,
      configurable: true,
    });
    restore = () =>
      Object.defineProperty(window, "location", {
        value: original,
        writable: true,
        configurable: true,
      });
    return assign;
  };

  afterEach(() => {
    restore?.();
    restore = undefined;
  });

  it("navigates out of the app", () => {
    // The reason this exists rather than a `<Navigate>`: the router has no
    // route for an address belonging to a different app, so it would
    // render its catch-all instead of leaving.
    const assign = stubLocation();

    render(<ExternalRedirect to="/flow" />);

    expect(assign).toHaveBeenCalledWith("/flow");
  });

  it("renders nothing while the browser leaves", () => {
    // Anything rendered here flashes a page the visitor is not staying on,
    // and anything that navigates would race the assign above.
    stubLocation();

    const { container } = render(<ExternalRedirect to="/elsewhere" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("goes nowhere when there is no destination", () => {
    // `propTypes.isRequired` is a dev-only warning, not a guard. Without the
    // check this was `assign(undefined)`, which navigates to `/undefined`
    // — the same class of bug as `flowAppPath()`'s in the paired cloud PR.
    const assign = stubLocation();

    const { container } = render(<ExternalRedirect to={undefined} />);

    expect(assign).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it("navigates once per destination, not on every render", () => {
    const assign = stubLocation();

    const { rerender } = render(<ExternalRedirect to="/flow" />);
    rerender(<ExternalRedirect to="/flow" />);

    expect(assign).toHaveBeenCalledTimes(1);
  });
});
