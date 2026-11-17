import { expect, it } from "vitest";

// Known bad: an unmocked XHR (the transport axios uses), error handled.
it("posts without a handler", async () => {
  const outcome = await new Promise<string>((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/unstract/org-1/workflow/");
    xhr.onload = () => resolve("loaded");
    xhr.onerror = () => resolve("error");
    xhr.send("{}");
  });
  expect(outcome).toBe("error");
});
