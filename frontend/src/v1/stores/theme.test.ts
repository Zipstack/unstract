import { expect, it } from "vitest";
import { createThemeStore } from "./theme";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
    data,
  };
}

it("starts as system and resolves from the system flag", () => {
  const store = createThemeStore({
    storage: memoryStorage(),
    systemPrefersDark: true,
  });
  expect(store.getState().preference).toBe("system");
  expect(store.getState().mode).toBe("dark");
});

it("hydrate reads the stored preference and setPreference persists it", () => {
  const storage = memoryStorage({ "unstract.v1.theme": "unstract" });
  const store = createThemeStore({ storage, systemPrefersDark: false });
  store.getState().hydrate(storage);
  expect(store.getState().mode).toBe("unstract");
  store.getState().setPreference("dark");
  expect(store.getState().mode).toBe("dark");
  expect(storage.data["unstract.v1.theme"]).toBe("dark");
});

it("follows system flips only while the preference is system", () => {
  const store = createThemeStore({
    storage: memoryStorage(),
    systemPrefersDark: false,
  });
  store.getState().setSystemPrefersDark(true);
  expect(store.getState().mode).toBe("dark");
  store.getState().setPreference("light");
  store.getState().setSystemPrefersDark(false);
  store.getState().setSystemPrefersDark(true);
  expect(store.getState().mode).toBe("light");
});

it("falls back when storage throws", () => {
  const broken = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("blocked");
    },
  };
  const store = createThemeStore({ storage: broken, systemPrefersDark: false });
  expect(() => store.getState().hydrate(broken)).not.toThrow();
  expect(store.getState().preference).toBe("system");
  expect(() => store.getState().setPreference("dark")).not.toThrow();
  expect(store.getState().mode).toBe("dark");
});
