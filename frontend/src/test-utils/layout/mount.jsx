import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, onTestFinished } from "vitest";

const settle = async () => {
  // Fonts change text metrics and antd injects its CSS-in-JS on mount; both
  // must be done before anything is measured.
  await document.fonts.ready;
  await new Promise((resolve) => requestAnimationFrame(resolve));
};

/**
 * Mount `ui` with the list rendered at `width` px and wait for layout to settle.
 *
 * Returns the wrapper element plus the usual RTL result.
 */
export const mountAtWidth = async (ui, width) => {
  const host = document.createElement("div");
  host.style.width = `${width}px`;
  document.body.appendChild(host);
  // Testing Library unmounts the React tree but leaves the container behind,
  // and every test in a file shares one browser page — so without this the
  // body accumulates a dead host per mount, alongside the portals antd hangs
  // off it.
  onTestFinished(() => host.remove());

  const result = render(<MemoryRouter>{ui}</MemoryRouter>, {
    container: host,
  });
  await settle();

  const wrapper = host.querySelector(".list-view-wrapper");
  expect(wrapper, "list did not render").not.toBeNull();

  // ListView sizes itself as a percentage of an ancestor that also carries
  // padding, so the host width needed for a given list width can't be computed
  // up front. Converge on it instead — measure, correct proportionally, repeat.
  // Deriving it beats hard-coding the percentage: a design tweak there changes
  // nothing this suite asserts and must not turn every case red.
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const measured = wrapper.getBoundingClientRect().width;
    if (Math.abs(measured - width) <= 0.5) {
      break;
    }
    const hostWidth = Number.parseFloat(host.style.width);
    host.style.width = `${hostWidth + (width - measured) * (hostWidth / measured)}px`;
    await settle();
  }

  // The width is also clamped (min/max on the wrapper). Without this guard a
  // clamp would silently collapse three "different" widths into three runs of
  // the same one, and the suite would look broader than it is.
  const actual = wrapper.getBoundingClientRect().width;
  expect(
    Math.abs(actual - width),
    `asked for a ${width}px list but got ${actual.toFixed(0)}px — the width is being clamped, so this case is not testing what it claims`,
  ).toBeLessThanOrEqual(1.5);

  return { ...result, wrapper, host };
};

/**
 * The rows of a rendered list.
 *
 * Asserts there are some: `.ant-list-item` is antd's class, not ours, so a
 * major bump could rename it — and every per-row assertion in a suite like
 * this one lives inside `for (const row of rowsOf(...))`. Silence there would
 * read as green.
 */
export const rowsOf = (wrapper) => {
  const rows = [...wrapper.querySelectorAll(".ant-list-item")];
  expect(
    rows.length,
    "no list rows found — the row selector no longer matches, so every per-row assertion would pass vacuously",
  ).toBeGreaterThan(0);
  return rows;
};

export const queryAll = (wrapper, selector) => [
  ...wrapper.querySelectorAll(selector),
];
