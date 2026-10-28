import { render, screen } from "@testing-library/react";
import { getPortalContainer } from "@v1/lib/portal";
import { useThemeStore } from "@v1/stores/theme";
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ThemeProvider } from "./ThemeProvider";

type Listener = (e: { matches: boolean }) => void;
let listeners: Listener[] = [];
let matches = false;

beforeEach(() => {
  listeners = [];
  matches = false;
  document.body.innerHTML = "";
  window.localStorage.clear();
  useThemeStore.setState({
    preference: "system",
    systemPrefersDark: false,
    mode: "light",
  });
  vi.stubGlobal("matchMedia", (query: string) => ({
    media: query,
    matches,
    addEventListener: (_: string, l: Listener) => {
      listeners.push(l);
    },
    removeEventListener: (_: string, l: Listener) => {
      listeners = listeners.filter((x) => x !== l);
    },
  }));
});
afterEach(() => vi.unstubAllGlobals());

it("renders the v1 root with the stored mode and syncs the portal container", () => {
  window.localStorage.setItem("unstract.v1.theme", "unstract");
  render(
    <ThemeProvider>
      <span>hi</span>
    </ThemeProvider>,
  );
  const root = screen.getByText("hi").parentElement as HTMLElement;
  expect(root.classList.contains("v1")).toBe(true);
  expect(root.dataset.uiVersion).toBe("v1");
  expect(root.dataset.theme).toBe("unstract");
  expect(getPortalContainer().dataset.theme).toBe("unstract");
});

it("follows the system preference while set to system and stops after an explicit choice", () => {
  render(
    <ThemeProvider>
      <span>hi</span>
    </ThemeProvider>,
  );
  const root = screen.getByText("hi").parentElement as HTMLElement;
  act(() => {
    for (const l of listeners) {
      l({ matches: true });
    }
  });
  expect(root.dataset.theme).toBe("dark");
  act(() => {
    useThemeStore.getState().setPreference("light");
  });
  act(() => {
    for (const l of listeners) {
      l({ matches: false });
    }
  });
  act(() => {
    for (const l of listeners) {
      l({ matches: true });
    }
  });
  expect(root.dataset.theme).toBe("light");
  expect(getPortalContainer().dataset.theme).toBe("light");
});

it("removes the media listener on unmount", () => {
  const { unmount } = render(
    <ThemeProvider>
      <span>hi</span>
    </ThemeProvider>,
  );
  expect(listeners).toHaveLength(1);
  unmount();
  expect(listeners).toHaveLength(0);
});
