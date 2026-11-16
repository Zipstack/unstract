import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { useEffect, useState } from "react";
import { expect, it } from "vitest";

// Known bad: the component swallows the network error, so only the harness
// can fail this test.
it("loads adapters without a handler", async () => {
  function Adapters() {
    const [state, setState] = useState("loading");
    useEffect(() => {
      fetch("/api/v1/unstract/org-1/adapter/?type=LLM").then(
        () => setState("loaded"),
        () => setState("failed"),
      );
    }, []);
    return <p>{state}</p>;
  }
  renderV1(<Adapters />);
  expect(await screen.findByText("failed")).toBeInTheDocument();
});
