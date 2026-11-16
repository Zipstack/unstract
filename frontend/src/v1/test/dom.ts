import { act } from "react";
import { vi } from "vitest";

/*
 * Controllable stand-ins for browser APIs happy-dom does not drive. Each
 * install uses vi.stubGlobal, which the v1 config undoes after every test
 * (`unstubGlobals: true`), so no test needs its own afterEach.
 */

type Size = Readonly<{ width: number; height: number }>;

export type ResizeObserverControl = Readonly<{
  /** Elements currently observed, across every observer. */
  observed: () => Element[];
  /** Reports a new size for `target` to every observer watching it. */
  resize: (target: Element, size: Size) => void;
}>;

/** Replaces ResizeObserver with one the test drives through `resize`. */
export function installResizeObserver(): ResizeObserverControl {
  const observers = new Set<FakeResizeObserver>();

  class FakeResizeObserver implements ResizeObserver {
    readonly targets = new Set<Element>();
    constructor(private readonly callback: ResizeObserverCallback) {
      observers.add(this);
    }
    observe(target: Element): void {
      // Re-registers an instance reused after disconnect(), as browsers allow.
      observers.add(this);
      this.targets.add(target);
    }
    unobserve(target: Element): void {
      this.targets.delete(target);
    }
    disconnect(): void {
      this.targets.clear();
      observers.delete(this);
    }
    notify(target: Element, { width, height }: Size): void {
      const contentRect = new DOMRect(0, 0, width, height);
      const boxSize = [{ inlineSize: width, blockSize: height }];
      const entry = {
        target,
        contentRect,
        borderBoxSize: boxSize,
        contentBoxSize: boxSize,
        devicePixelContentBoxSize: boxSize,
      } as unknown as ResizeObserverEntry;
      this.callback([entry], this);
    }
  }

  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  return {
    observed: () => [...observers].flatMap((o) => [...o.targets]),
    resize: (target, size) => {
      act(() => {
        for (const observer of observers) {
          if (observer.targets.has(target)) {
            observer.notify(target, size);
          }
        }
      });
    },
  };
}

export type IntersectionObserverControl = Readonly<{
  /** Elements currently observed, across every observer. */
  observed: () => Element[];
  /** Reports `target` entering (true) or leaving (false) the viewport. */
  intersect: (target: Element, isIntersecting: boolean) => void;
}>;

/** Replaces IntersectionObserver with one the test drives through `intersect`. */
export function installIntersectionObserver(): IntersectionObserverControl {
  const observers = new Set<FakeIntersectionObserver>();

  class FakeIntersectionObserver implements IntersectionObserver {
    readonly root: Element | Document | null;
    readonly rootMargin: string;
    readonly scrollMargin = "0px";
    readonly thresholds: readonly number[];
    readonly targets = new Set<Element>();
    constructor(
      private readonly callback: IntersectionObserverCallback,
      options: IntersectionObserverInit = {},
    ) {
      this.root = options.root ?? null;
      this.rootMargin = options.rootMargin ?? "0px";
      const threshold = options.threshold ?? 0;
      this.thresholds = Array.isArray(threshold) ? threshold : [threshold];
      observers.add(this);
    }
    observe(target: Element): void {
      // Re-registers an instance reused after disconnect(), as browsers allow.
      observers.add(this);
      this.targets.add(target);
    }
    unobserve(target: Element): void {
      this.targets.delete(target);
    }
    disconnect(): void {
      this.targets.clear();
      observers.delete(this);
    }
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
    notify(target: Element, isIntersecting: boolean): void {
      const rect = target.getBoundingClientRect();
      const entry = {
        target,
        isIntersecting,
        intersectionRatio: isIntersecting ? 1 : 0,
        boundingClientRect: rect,
        intersectionRect: isIntersecting ? rect : new DOMRect(),
        rootBounds: null,
        time: performance.now(),
      } as IntersectionObserverEntry;
      this.callback([entry], this);
    }
  }

  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  return {
    observed: () => [...observers].flatMap((o) => [...o.targets]),
    intersect: (target, isIntersecting) => {
      act(() => {
        for (const observer of observers) {
          if (observer.targets.has(target)) {
            observer.notify(target, isIntersecting);
          }
        }
      });
    },
  };
}

export type MatchMediaControl = Readonly<{
  /** Flips `(prefers-color-scheme: dark)` and notifies its listeners. */
  setDark: (dark: boolean) => void;
  /** Number of change listeners currently attached, across all queries. */
  listenerCount: () => number;
}>;

type MediaListener = (event: MediaQueryListEvent) => void;

const DARK_QUERY = "(prefers-color-scheme: dark)";

/**
 * Replaces matchMedia. Only `(prefers-color-scheme: dark)` is ever true, and
 * only while `dark` is set; every other query reports false.
 */
export function mockMatchMedia({
  dark = false,
}: {
  dark?: boolean;
} = {}): MatchMediaControl {
  let prefersDark = dark;
  const listeners = new Map<string, Set<MediaListener>>();
  const listenersFor = (query: string) => {
    let set = listeners.get(query);
    if (!set) {
      set = new Set();
      listeners.set(query, set);
    }
    return set;
  };
  const matches = (query: string) => query === DARK_QUERY && prefersDark;

  vi.stubGlobal(
    "matchMedia",
    (query: string): MediaQueryList =>
      ({
        media: query,
        get matches() {
          return matches(query);
        },
        onchange: null,
        addEventListener: (_type: string, listener: MediaListener) => {
          listenersFor(query).add(listener);
        },
        removeEventListener: (_type: string, listener: MediaListener) => {
          listenersFor(query).delete(listener);
        },
        addListener: (listener: MediaListener) => {
          listenersFor(query).add(listener);
        },
        removeListener: (listener: MediaListener) => {
          listenersFor(query).delete(listener);
        },
        dispatchEvent: () => true,
      }) as unknown as MediaQueryList,
  );

  return {
    setDark: (value) => {
      prefersDark = value;
      act(() => {
        for (const listener of listenersFor(DARK_QUERY)) {
          listener({
            matches: value,
            media: DARK_QUERY,
          } as MediaQueryListEvent);
        }
      });
    },
    listenerCount: () =>
      [...listeners.values()].reduce((sum, set) => sum + set.size, 0),
  };
}
