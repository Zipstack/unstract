import { afterAll, it } from "vitest";

// Known bad: the request fires from a timer after the last test's afterEach.
afterAll(async () => {
  await new Promise((resolve) => setTimeout(resolve, 100));
});

it("schedules a late poll without a handler", () => {
  setTimeout(() => {
    fetch("/api/v1/unstract/org-1/poll/").catch(() => undefined);
  }, 30);
});
