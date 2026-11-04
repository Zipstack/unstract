import { describe, expect, it } from "vitest";
import {
  isThemePreference,
  readThemePreference,
  resolveThemeMode,
  THEME_MODES,
  THEME_STORAGE_KEY,
  writeThemePreference,
} from "./theme";

describe("resolveThemeMode", () => {
  it("returns the explicit mode unchanged", () => {
    expect(resolveThemeMode("dark", false)).toBe("dark");
    expect(resolveThemeMode("unstract", true)).toBe("unstract");
  });
  it("maps system to dark or light from the media flag", () => {
    expect(resolveThemeMode("system", true)).toBe("dark");
    expect(resolveThemeMode("system", false)).toBe("light");
  });
});

describe("readThemePreference", () => {
  it("returns a stored valid preference", () => {
    const storage = { getItem: () => "unstract" };
    expect(readThemePreference(storage)).toBe("unstract");
  });
  it("returns system for a missing, unknown or unreadable value", () => {
    expect(readThemePreference({ getItem: () => null })).toBe("system");
    expect(readThemePreference({ getItem: () => "sepia" })).toBe("system");
    expect(
      readThemePreference({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toBe("system");
    expect(readThemePreference(null)).toBe("system");
  });
});

describe("writeThemePreference", () => {
  it("writes under the v1 key and swallows storage errors", () => {
    const calls: [string, string][] = [];
    writeThemePreference(
      {
        setItem: (k, v) => {
          calls.push([k, v]);
        },
      },
      "dark",
    );
    expect(calls).toEqual([[THEME_STORAGE_KEY, "dark"]]);
    expect(() =>
      writeThemePreference(
        {
          setItem: () => {
            throw new Error("quota");
          },
        },
        "dark",
      ),
    ).not.toThrow();
    expect(() => writeThemePreference(null, "dark")).not.toThrow();
  });
});

it("THEME_MODES lists exactly the three modes and isThemePreference accepts system", () => {
  expect(THEME_MODES).toEqual(["light", "dark", "unstract"]);
  expect(isThemePreference("system")).toBe(true);
  expect(isThemePreference("v0-dark")).toBe(false);
});
