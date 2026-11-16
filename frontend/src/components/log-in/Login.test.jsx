/**
 * Which products survive into the login URL (UN-4626).
 *
 * `knownProducts` used to be the literal `["unstract", "llm-whisperer"]`
 * here, which made THIS file the place a deployment's product set was
 * decided — and it is not: the plugin owns that set, and already does for
 * the product chooser and the session check. A product the plugin knew but
 * this literal did not was dropped from the login URL silently, so the
 * backend never learned which product the visitor came for and the identity
 * provider showed them the wrong branding.
 *
 * **That change is wider than the ticket's own product**, which is the
 * point of the `verticals` case below (Wicky, review on #2475). Reaching
 * for `Object.values(PRODUCT_NAMES)` admits every product the plugin
 * declares, not just `flow` — so `?selectedProduct=verticals` now survives
 * where the old literal dropped it. That is a fix rather than a regression,
 * but it is a second behaviour change on the backend's view of the login
 * and it is pinned here rather than left to be rediscovered.
 *
 * Both halves are driven through mocked plugin modules rather than through
 * whatever happens to be on disk, because this file lives in the PUBLIC
 * repo and its tests run both with the cloud plugins overlaid and without
 * them. A test that read the real set would assert different things in the
 * two builds.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const AT_LOGIN = "https://host.example/login";

let restoreLocation;

/** `getBaseUrl()` does `new URL(window.location.href)`, so href must be real. */
const stubLocation = () => {
  const original = window.location;
  const stub = { href: AT_LOGIN, assign: vi.fn() };
  Object.defineProperty(window, "location", {
    value: stub,
    writable: true,
    configurable: true,
  });
  restoreLocation = () =>
    Object.defineProperty(window, "location", {
      value: original,
      writable: true,
      configurable: true,
    });
  return stub;
};

/**
 * Load `Login` with the plugin set the test wants.
 *
 * `null` means no plugins at all — the OSS-only build, which must keep the
 * exact behaviour this file had before the change.
 */
const loadLogin = async (productNames) => {
  vi.resetModules();
  vi.doMock("../../plugins/login-form/LoginForm", () => {
    throw new Error("plugin absent");
  });
  vi.doMock("../../plugins/helpers/common", () => {
    if (!productNames) {
      throw new Error("plugin absent");
    }
    return { PRODUCT_NAMES: productNames };
  });
  const { Login } = await import("./Login");
  return Login;
};

const clickLogin = () => fireEvent.click(screen.getByText("Login"));

describe("Login", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    restoreLocation?.();
    restoreLocation = undefined;
    vi.doUnmock("../../plugins/login-form/LoginForm");
    vi.doUnmock("../../plugins/helpers/common");
    vi.resetModules();
  });

  it("carries a product the plugin declares", async () => {
    const Login = await loadLogin({ unstract: "unstract", flow: "flow" });
    const location = stubLocation();
    localStorage.setItem("selectedProduct", "flow");

    render(<Login />);
    clickLogin();

    expect(location.href).toBe(
      "https://host.example/api/v1/login?selectedProduct=flow",
    );
  });

  it("carries `verticals` too, which the old literal dropped", async () => {
    // The wider half of the change. Not what this ticket is about, and
    // deliberately pinned so nobody reads it as an accident later.
    const Login = await loadLogin({
      unstract: "unstract",
      llmWhisperer: "llm-whisperer",
      verticals: "verticals",
      flow: "flow",
    });
    const location = stubLocation();
    localStorage.setItem("selectedProduct", "verticals");

    render(<Login />);
    clickLogin();

    expect(location.href).toContain("selectedProduct=verticals");
  });

  it("drops a product nothing declares", async () => {
    // The allowlist still IS one: an arbitrary stored value must not reach
    // the backend as a product.
    const Login = await loadLogin({ unstract: "unstract", flow: "flow" });
    const location = stubLocation();
    localStorage.setItem("selectedProduct", "not-a-product");

    render(<Login />);
    clickLogin();

    expect(location.href).toBe("https://host.example/api/v1/login");
  });

  it("keeps the original pair when there are no plugins", async () => {
    // The OSS-only build. `FALLBACK_PRODUCTS` is exactly the literal this
    // file always had, so its behaviour is unchanged.
    const Login = await loadLogin(null);
    const location = stubLocation();
    localStorage.setItem("selectedProduct", "llm-whisperer");

    render(<Login />);
    clickLogin();

    expect(location.href).toContain("selectedProduct=llm-whisperer");
  });

  it("drops Flow when there are no plugins to declare it", async () => {
    const Login = await loadLogin(null);
    const location = stubLocation();
    localStorage.setItem("selectedProduct", "flow");

    render(<Login />);
    clickLogin();

    expect(location.href).toBe("https://host.example/api/v1/login");
  });
});
