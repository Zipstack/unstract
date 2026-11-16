import { renderV1 } from "@v1/test";
import { useEffect } from "react";
import { it } from "vitest";

// Known bad, first test only: its unmount request must fail it, not the next.
it("first: requests on unmount", () => {
  function Editor() {
    useEffect(
      () => () => {
        fetch("/api/v1/unstract/org-1/unmount/").catch(() => undefined);
      },
      [],
    );
    return <p>editing</p>;
  }
  renderV1(<Editor />);
});

it("second: makes no request", async () => {
  await new Promise((resolve) => setTimeout(resolve, 50));
});
