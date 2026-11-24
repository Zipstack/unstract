import type { RunEventName } from "@v1/services/promptRuns";

/** Receives an event's raw payload; the engine parses it. */
export type RunEventHandler = (payload: unknown) => void;

/** All the run engine needs from the real-time channel. */
export type RunChannel = Readonly<{
  /** Listens for one event name; returns the unsubscribe. */
  subscribe: (event: RunEventName, handler: RunEventHandler) => () => void;
}>;

export type LocalRunChannel = RunChannel &
  Readonly<{ emit: (event: RunEventName, payload: unknown) => void }>;

/**
 * ponytail: an in-memory channel so the engine can be built and tested before
 * the real-time channel exists. The real-time channel's socket subscription
 * replaces it (same `subscribe` shape, room = the session's log events id);
 * nothing else in the engine changes.
 */
export function createLocalRunChannel(): LocalRunChannel {
  const handlers = new Map<RunEventName, Set<RunEventHandler>>();
  return {
    subscribe: (event, handler) => {
      const set = handlers.get(event) ?? new Set<RunEventHandler>();
      set.add(handler);
      handlers.set(event, set);
      return () => {
        set.delete(handler);
      };
    },
    emit: (event, payload) => {
      for (const handler of [...(handlers.get(event) ?? [])]) {
        handler(payload);
      }
    },
  };
}
