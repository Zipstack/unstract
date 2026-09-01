import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JsxInJsProbe } from "./__fixtures__/jsx-in-js-probe.js";

/**
 * Guards the JSX-in-`.js` transform, which exists for the cloud plugin tree.
 *
 * Two failures shipped from this one line of config, and NEITHER failed the
 * build — both produced a green `vite build` and HTTP 200:
 *
 *   1. No transform at all. Removing Vite's `esbuild: { loader: "jsx" }`
 *      override was safe for OSS (its JSX-bearing .js files were renamed to
 *      .jsx) but broke the Docker image, which also compiles src/plugins/
 *      copied in from the unstract-cloud repo — nine of those files put JSX
 *      in .js. That one at least failed the cloud build loudly.
 *   2. The WRONG transform. Restoring it via a standalone
 *      `transformWithEsbuild` call defaulted to the CLASSIC JSX runtime,
 *      emitting `React.createElement(...)`. Those plugin files use JSX
 *      without importing React, so the app threw
 *      `ReferenceError: React is not defined` while rendering the router and
 *      showed a blank white page. The build was green throughout.
 *
 * The fixture deliberately mirrors the cloud files: JSX in a `.js` file with
 * NO React import. Rendering it is what distinguishes a correct transform
 * from one that merely compiles.
 */
describe("JSX in .js files (the cloud plugin tree depends on this)", () => {
  it("renders a .js module that uses JSX without importing React", () => {
    render(<JsxInJsProbe />);
    expect(screen.getByTestId("jsx-in-js-probe")).toHaveTextContent("ok");
  });
});
