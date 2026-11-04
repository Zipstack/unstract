import { renderV1 } from "@v1/test";
import { useEffect } from "react";
import { it } from "vitest";

// Known bad: the only test in the file; its request starts during cleanup().
it("reports a draft on unmount without a handler", () => {
  function Editor() {
    useEffect(
      () => () => {
        fetch("/api/v1/unstract/org-1/draft/", { method: "POST" }).catch(
          () => undefined,
        );
      },
      [],
    );
    return <p>editing</p>;
  }
  renderV1(<Editor />);
});
