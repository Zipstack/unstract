import { afterEach, describe, expect, it, vi } from "vitest";

import { saasOnlyErrorProps } from "./PostHogDeployment";

const setHost = (hostname) =>
  vi.spyOn(window, "location", "get").mockReturnValue({ hostname });

describe("saasOnlyErrorProps", () => {
  afterEach(() => vi.restoreAllMocks());

  it("drops error text on self-hosted deployments", () => {
    setHost("unstract.customer.internal");
    expect(saasOnlyErrorProps("connect to https://10.0.0.5 failed")).toEqual(
      {},
    );
  });

  it("keeps error text, capped at 200 chars, on SaaS", () => {
    setHost("us-central.unstract.com");
    const props = saasOnlyErrorProps("x".repeat(500));
    expect(props.error).toHaveLength(200);
  });

  it("adds nothing when there is no string error", () => {
    setHost("eu-west.unstract.com");
    expect(saasOnlyErrorProps(undefined)).toEqual({});
    expect(saasOnlyErrorProps([{ detail: "limit" }])).toEqual({});
  });
});
