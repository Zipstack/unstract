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

  it("still leaves for a root-relative path, which every deployment uses", () => {
    // The guard must NOT require an absolute URL. `config.flowUrl` is `/flow`
    // in the staging values and in the chart's own unit test, because Flow is
    // served under a path on the shared host rather than at its own origin.
    // An absolute-only check would reject the one destination this component
    // exists for (review on #2494, 2026-11).
    const assign = stubLocation();

    render(<ExternalRedirect to="/flow" />);

    expect(assign).toHaveBeenCalledWith("/flow");
  });

  it("leaves for an absolute http(s) URL", () => {
    const assign = stubLocation();

    render(<ExternalRedirect to="https://flow.example/app" />);

    expect(assign).toHaveBeenCalledWith("https://flow.example/app");
  });

  it("refuses a protocol-relative address, which names another origin", () => {
    // `//evil.example` begins with `/` and so passes a naive "is it a path"
    // test, but the browser reads it as another origin entirely.
    const assign = stubLocation();

    render(<ExternalRedirect to="//evil.example/app" />);

    expect(assign).not.toHaveBeenCalled();
  });

  it("refuses an address that is neither a path nor http(s)", () => {
    // Defence in depth for `RequireGuest`, which now resolves part of its
    // destination from `?selectedProduct=`. The plugin answers only from a
    // closed map, but that map is in another repository and no CI here can
    // enforce it, so this file does not rely on it.
    const assign = stubLocation();

    for (const bad of [
      "javascript:alert(1)",
      "[object Object]",
      "evil.example",
      "data:text/html,<script>",
    ]) {
      render(<ExternalRedirect to={bad} />);
    }

    expect(assign).not.toHaveBeenCalled();
  });
});
