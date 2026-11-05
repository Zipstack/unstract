import { expect, it } from "vitest";

// Known bad: an unmocked WebSocket (v0's socket.io uses this transport).
it("opens a socket without a handler", async () => {
  const closed = await new Promise<boolean>((resolve) => {
    const socket = new WebSocket("ws://localhost:3000/api/v1/socket");
    socket.onclose = () => resolve(true);
    setTimeout(() => resolve(false), 1000);
  });
  expect(closed).toBe(true);
});
