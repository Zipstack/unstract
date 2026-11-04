import { useQuery, useQueryClient } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import {
  apiPath,
  axeViolations,
  DEFAULT_SESSION,
  expectNoA11yViolations,
  HttpResponse,
  http,
  installIntersectionObserver,
  installResizeObserver,
  makeSession,
  mockApi,
  mockMatchMedia,
  PORTAL_CONTAINER_ID,
  renderHookV1,
  renderV1,
} from "@v1/test";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useParams } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { takeUnhandledRequests, unhandledRequestsMessage } from "./network";

describe("renderV1", () => {
  it("wraps the UI in the v1 root with the theme, and creates a themed portal", () => {
    const { portal } = renderV1(<p>hello</p>, { theme: "dark" });
    const root = screen.getByText("hello").parentElement as HTMLElement;
    expect(root).toHaveClass("v1");
    expect(root.dataset.uiVersion).toBe("v1");
    expect(root.dataset.theme).toBe("dark");
    expect(portal.id).toBe(PORTAL_CONTAINER_ID);
    expect(portal).toHaveClass("v1");
    expect(portal.dataset.theme).toBe("dark");
  });

  it("removes the portal between tests", () => {
    expect(document.getElementById(PORTAL_CONTAINER_ID)).toBeNull();
    renderV1(<p>again</p>);
    expect(document.getElementById(PORTAL_CONTAINER_ID)?.dataset.theme).toBe(
      "light",
    );
  });

  it("renders portalled content into #v1-portal", () => {
    function Menu() {
      return createPortal(
        <div role="menu">items</div>,
        document.getElementById(PORTAL_CONTAINER_ID) as HTMLElement,
      );
    }
    const { portal } = renderV1(<Menu />);
    expect(portal).toContainElement(screen.getByRole("menu"));
  });

  it("starts the router at `route` and resolves params under `path`", () => {
    function Page() {
      const { id } = useParams();
      const location = useLocation();
      return (
        <p>
          {id} at {location.pathname}
        </p>
      );
    }
    renderV1(<Page />, { route: "/workflows/42", path: "/workflows/:id" });
    expect(screen.getByText("42 at /workflows/42")).toBeInTheDocument();
  });

  it("returns the session and distribution it rendered with", () => {
    const session = makeSession({ organization: { id: "org-9" } });
    const harness = renderV1(<p>x</p>, { session, distribution: "cloud" });
    expect(harness.session?.organization).toEqual({
      id: "org-9",
      name: DEFAULT_SESSION.organization.name,
    });
    expect(harness.distribution).toBe("cloud");
    expect(renderV1(<p>y</p>, { session: null }).session).toBeNull();
  });

  it("gives each render a fresh query client with retries off", () => {
    const first = renderV1(<p>a</p>).queryClient;
    const second = renderV1(<p>b</p>).queryClient;
    expect(first).not.toBe(second);
    expect(first.getDefaultOptions().queries?.retry).toBe(false);
    expect(first.getDefaultOptions().mutations?.retry).toBe(false);
  });

  it("returns a user-event instance bound to the render", async () => {
    function Counter() {
      const [count, setCount] = useState(0);
      return (
        <button type="button" onClick={() => setCount(count + 1)}>
          {count}
        </button>
      );
    }
    const { user } = renderV1(<Counter />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByRole("button")).toHaveTextContent("1");
  });
});

describe("renderHookV1", () => {
  it("runs the hook inside the providers", () => {
    const { result, queryClient } = renderHookV1(() => useQueryClient());
    expect(result.current).toBe(queryClient);
  });

  it("passes initialProps", () => {
    const { result, rerender } = renderHookV1((n: number) => n * 2, {
      initialProps: 2,
    });
    expect(result.current).toBe(4);
    rerender(5);
    expect(result.current).toBe(10);
  });
});

describe("network mocking", () => {
  it("serves typed handlers registered with mockApi", async () => {
    type Adapter = { id: string; name: string };
    const url = apiPath(DEFAULT_SESSION, "/adapter/");
    expect(url).toBe("/api/v1/unstract/org-1/adapter/");
    mockApi(
      http.get<never, never, Adapter[]>(url, () =>
        HttpResponse.json([{ id: "a1", name: "OpenAI" }]),
      ),
    );
    function Adapters() {
      const { data } = useQuery({
        queryKey: ["adapters"],
        queryFn: async (): Promise<Adapter[]> => (await fetch(url)).json(),
      });
      return (
        <ul>
          {data?.map((a) => (
            <li key={a.id}>{a.name}</li>
          ))}
        </ul>
      );
    }
    renderV1(<Adapters />);
    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
  });

  it("records an unmocked request with its method and absolute URL", async () => {
    await expect(fetch("/api/v1/unmocked?x=1")).rejects.toThrow();
    const unhandled = takeUnhandledRequests();
    expect(unhandled).toEqual([
      "GET http://localhost:3000/api/v1/unmocked?x=1",
    ]);
    expect(unhandledRequestsMessage(unhandled)).toContain(
      "Unmocked request (add a handler",
    );
  });

  it("errors an unmocked request made by a component, and names it", async () => {
    function Loader() {
      const [state, setState] = useState("loading");
      useEffect(() => {
        fetch("/api/v1/unstract/org-1/missing/").then(
          () => setState("loaded"),
          () => setState("failed"),
        );
      }, []);
      return <p>{state}</p>;
    }
    renderV1(<Loader />);
    expect(await screen.findByText("failed")).toBeInTheDocument();
    // Drained here so this test passes; setup.ts would otherwise fail it.
    expect(takeUnhandledRequests()).toEqual([
      "GET http://localhost:3000/api/v1/unstract/org-1/missing/",
    ]);
  });

  it("answers an unmocked XHR (axios's transport) with a network error", async () => {
    const outcome = await new Promise<string>((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/v1/xhr");
      xhr.onload = () => resolve(`loaded ${xhr.status}`);
      xhr.onerror = () => resolve("error");
      xhr.send("{}");
    });
    expect(outcome).toBe("error");
    expect(takeUnhandledRequests()).toEqual([
      "POST http://localhost:3000/api/v1/xhr",
    ]);
  });

  it("pluralises the message for several requests", () => {
    expect(unhandledRequestsMessage(["GET /a", "POST /b"])).toBe(
      "Unmocked requests (add a handler with mockApi() or server.use()):\n  GET /a\n  POST /b",
    );
  });
});

describe("accessibility assertions", () => {
  it("passes accessible markup", async () => {
    const { container } = renderV1(
      <label>
        Name <input />
      </label>,
    );
    await expect(container).toHaveNoA11yViolations();
    await expectNoA11yViolations(container);
  });

  it("names the rule and the node for a violation", async () => {
    const { container } = renderV1(<input aria-describedby="nowhere" />);
    const violations = await axeViolations(container);
    expect(violations.map((v) => v.id)).toContain("label");
    await expect(expectNoA11yViolations(container)).rejects.toThrow(
      /\[label\] \(critical\) input/,
    );
    await expect(expect(container).toHaveNoA11yViolations()).rejects.toThrow(
      /Expected no accessibility violations/,
    );
  });

  it("rejects a non-element", async () => {
    await expect(expect("text").toHaveNoA11yViolations()).rejects.toThrow(
      /expects a DOM element/,
    );
  });

  it("supports .not for a known violation", async () => {
    // A button with no accessible name: axe's `button-name`.
    const { container } = renderV1(<button type="button" />);
    await expect(container).not.toHaveNoA11yViolations();
  });
});

describe("DOM stand-ins", () => {
  it("drives ResizeObserver callbacks", () => {
    const control = installResizeObserver();
    const target = document.createElement("div");
    const sizes: number[] = [];
    const observer = new ResizeObserver((entries) => {
      sizes.push(entries[0]?.contentRect.width ?? -1);
    });
    observer.observe(target);
    expect(control.observed()).toEqual([target]);
    control.resize(target, { width: 640, height: 480 });
    control.resize(document.createElement("span"), { width: 1, height: 1 });
    expect(sizes).toEqual([640]);
    observer.unobserve(target);
    control.resize(target, { width: 320, height: 240 });
    expect(sizes).toEqual([640]);
    observer.disconnect();
    expect(control.observed()).toEqual([]);
  });

  it("drives IntersectionObserver callbacks", () => {
    const control = installIntersectionObserver();
    const target = document.createElement("div");
    const seen: boolean[] = [];
    const observer = new IntersectionObserver(
      (entries) => {
        seen.push(entries[0]?.isIntersecting ?? false);
      },
      { threshold: [0, 1], rootMargin: "10px" },
    );
    expect(observer.thresholds).toEqual([0, 1]);
    expect(observer.rootMargin).toBe("10px");
    expect(observer.takeRecords()).toEqual([]);
    observer.observe(target);
    control.intersect(target, true);
    control.intersect(target, false);
    expect(seen).toEqual([true, false]);
    observer.unobserve(target);
    control.intersect(target, true);
    expect(seen).toEqual([true, false]);
    expect(new IntersectionObserver(() => undefined).thresholds).toEqual([0]);
    observer.disconnect();
    expect(control.observed()).toEqual([]);
  });

  it("drives the dark-scheme media query", () => {
    const control = mockMatchMedia();
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    expect(query.matches).toBe(false);
    expect(window.matchMedia("(min-width: 1px)").matches).toBe(false);
    const seen: boolean[] = [];
    const listener = (event: MediaQueryListEvent) => seen.push(event.matches);
    query.addEventListener("change", listener);
    query.addListener(listener);
    expect(control.listenerCount()).toBe(1);
    control.setDark(true);
    expect(query.matches).toBe(true);
    expect(seen).toEqual([true]);
    query.removeEventListener("change", listener);
    query.removeListener(listener);
    expect(control.listenerCount()).toBe(0);
  });

  it("starts dark when asked", () => {
    mockMatchMedia({ dark: true });
    expect(window.matchMedia("(prefers-color-scheme: dark)").matches).toBe(
      true,
    );
  });

  it("restores the real globals after each test", () => {
    // Stubbed by the tests above; `unstubGlobals: true` undid them.
    expect(window.ResizeObserver.name).not.toBe("FakeResizeObserver");
    expect(window.IntersectionObserver.name).not.toBe(
      "FakeIntersectionObserver",
    );
  });
});
