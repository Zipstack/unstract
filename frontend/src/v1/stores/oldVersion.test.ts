import {
  LAST_USER_STORAGE_KEY,
  oldVersionStorageKey,
  readOldVersion,
  writeOldVersion,
} from "@v1/lib/oldVersion";
import { describe, expect, it } from "vitest";
import { createOldVersionStore } from "./oldVersion";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
}

const refusing = {
  getItem: () => {
    throw new Error("denied");
  },
  setItem: () => {
    throw new Error("denied");
  },
  removeItem: () => {
    throw new Error("denied");
  },
};

describe("old-version storage", () => {
  it("is keyed per user and absent means v1", () => {
    const s = memoryStorage();
    expect(readOldVersion(s, "7")).toBe(false);
    expect(writeOldVersion(s, "7", true)).toBe(true);
    expect(s.data.get(oldVersionStorageKey("7"))).toBe("true");
    expect(readOldVersion(s, "7")).toBe(true);
    expect(readOldVersion(s, "8")).toBe(false);
    writeOldVersion(s, "7", false);
    expect(s.data.has(oldVersionStorageKey("7"))).toBe(false);
  });

  it("unreadable or refusing storage reads as v1 and reports the failed write", () => {
    expect(readOldVersion(refusing, "7")).toBe(false);
    expect(writeOldVersion(refusing, "7", true)).toBe(false);
    expect(writeOldVersion(null, "7", true)).toBe(false);
  });
});

describe("old-version store", () => {
  it("knows no user and no choice on a fresh browser, and cannot be set", () => {
    const store = createOldVersionStore(memoryStorage());
    expect(store.getState()).toMatchObject({ userId: null, oldVersion: null });
    expect(store.getState().setOldVersion(true)).toBe(false);
    expect(store.getState().oldVersion).toBeNull();
  });

  it("survives reload and re-login: a new store reads the last user's choice", () => {
    const s = memoryStorage();
    const first = createOldVersionStore(s);
    first.getState().setUser("7");
    expect(first.getState().oldVersion).toBe(false);
    expect(first.getState().setOldVersion(true)).toBe(true);
    expect(s.data.get(LAST_USER_STORAGE_KEY)).toBe("7");

    const reloaded = createOldVersionStore(s);
    expect(reloaded.getState()).toMatchObject({
      userId: "7",
      oldVersion: true,
    });
    reloaded.getState().setUser(null); // signed out: keeps the last user
    expect(reloaded.getState()).toMatchObject({
      userId: "7",
      oldVersion: true,
    });
    reloaded.getState().setUser("7");
    expect(reloaded.getState().oldVersion).toBe(true);
  });

  it("is per user", () => {
    const s = memoryStorage({ [oldVersionStorageKey("7")]: "true" });
    const store = createOldVersionStore(s);
    store.getState().setUser("8");
    expect(store.getState().oldVersion).toBe(false);
    store.getState().setUser("7");
    expect(store.getState().oldVersion).toBe(true);
  });

  it("with refusing storage, defaults to v1 and the choice still holds for the session", () => {
    const store = createOldVersionStore(refusing);
    store.getState().setUser("7");
    expect(store.getState().oldVersion).toBe(false);
    expect(store.getState().setOldVersion(true)).toBe(true);
    expect(store.getState().oldVersion).toBe(true);
    store.getState().setUser("8");
    store.getState().setUser("7");
    expect(store.getState().oldVersion).toBe(true);
  });
});
