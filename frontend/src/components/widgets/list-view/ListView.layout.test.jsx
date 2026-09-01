import { describe, expect, it } from "vitest";
import { useSessionStore } from "../../../store/session-store";
import {
  expectAlignedX,
  expectContained,
  expectNoHorizontalOverflow,
  expectNoHorizontalOverlap,
  expectTruncated,
} from "../../../test-utils/layout/assertions";
import {
  mountAtWidth,
  queryAll,
  rowsOf,
} from "../../../test-utils/layout/mount";
import { ListView } from "./ListView";

// The list row is a table drawn with flexbox: four columns that must line up
// across rows even though every row lays itself out independently. These tests
// hold that contract. Two shipped regressions motivated them — an owner column
// that sized itself to its own text and so started at a different x on every
// row, and pinned columns inside a shrinkable wrapper that spilled out of it
// and printed over the action icons. Neither is visible in a CSS diff.

const SESSION_EMAIL = "me@example.com";

// The widths .list-view-wrapper itself declares support for (min 800, max
// 1400) plus the midpoint. Keep in step with ListView.css if that range moves.
const WIDTHS = [800, 1100, 1400];

// Owner labels of wildly different lengths are the whole point: a column that
// sizes to content only misaligns when its content differs row to row.
// Long enough that no plausible width cap could ever fit it: the truncation
// case must fail because truncation broke, never because someone widened a
// column.
const LONG_EMAIL = `a-really-long-service-account-name-${"x".repeat(300)}@example.com`;

const ITEMS = [
  {
    id: "1",
    tool_name: "S3",
    description: "Short one",
    created_by_email: SESSION_EMAIL,
    created_at: "2026-01-02T03:04:05Z",
    modified_at: "2026-07-20T03:04:05Z",
  },
  {
    id: "2",
    tool_name:
      "A deliberately long project name that has to ellipsize somewhere",
    description:
      "A long description that runs past the width cap and gets clipped with a tooltip",
    created_by_email: LONG_EMAIL,
    created_at: "2025-03-02T03:04:05Z",
    modified_at: "2025-04-02T03:04:05Z",
  },
  {
    // No description: the left column collapses to a single line, so the row
    // is shorter than its neighbours. Column alignment must not care.
    id: "3",
    tool_name: "KYC extractor",
    created_by_email: "someone.else@example.com",
    created_at: "2026-06-02T03:04:05Z",
    modified_at: "2026-07-21T03:04:05Z",
  },
  {
    // Membership model: renders "Me +2" rather than an address.
    id: "4",
    tool_name: "Co-owned invoice parser",
    description: "Owned with two other people",
    co_owners_count: 3,
    is_owner: true,
    created_at: "2026-07-01T03:04:05Z",
    modified_at: "2026-07-22T03:04:05Z",
  },
];

// Handlers only need to exist: their presence decides which columns and
// controls ListView renders, and nothing here clicks anything.
const noop = () => undefined;

// Adapters and Prompt Studio: owner + updated, share and co-owner enabled.
const fullConfig = {
  listOfTools: ITEMS,
  handleEdit: noop,
  handleDelete: noop,
  handleShare: noop,
  handleCoOwner: noop,
  titleProp: "tool_name",
  descriptionProp: "description",
  idProp: "id",
  showOwner: true,
  showModified: true,
  type: "Tool",
};

// Connectors and Workflows: owner only, no updated column, no co-owner button
// (so the badge renders as a div rather than a button).
const ownerOnlyConfig = {
  ...fullConfig,
  handleShare: undefined,
  handleCoOwner: undefined,
  showModified: false,
  centered: true,
};

const mountList = (props, width) => {
  useSessionStore.setState({ sessionDetails: { email: SESSION_EMAIL } });
  return mountAtWidth(<ListView {...props} />, width);
};

describe("ListView row layout", () => {
  it("renders the owner column as a straight column, whatever the owner is called", async () => {
    const { wrapper } = await mountList(fullConfig, 1100);

    const owners = queryAll(wrapper, ".adapters-list-profile-container");
    expect(owners).toHaveLength(ITEMS.length);
    // Guard the fixture itself: if every row rendered the same label, the
    // alignment assertion below would pass for the wrong reason.
    const labels = queryAll(wrapper, ".shared-username").map((el) =>
      el.textContent.trim(),
    );
    expect(new Set(labels).size).toBeGreaterThan(1);

    expectAlignedX(owners, "owner column");
  });

  it("renders the updated column as a straight column, whatever the timestamps are", async () => {
    const { wrapper } = await mountList(fullConfig, 1100);

    const updated = queryAll(wrapper, ".list-view-modified-container");
    expect(updated).toHaveLength(ITEMS.length);
    const labels = queryAll(wrapper, ".list-view-modified-text").map((el) =>
      el.textContent.trim(),
    );
    expect(new Set(labels).size).toBeGreaterThan(1);

    expectAlignedX(updated, "updated column");
  });

  it.each(
    WIDTHS,
  )("keeps the metadata columns inside their box and clear of the actions at %ipx", async (width) => {
    const { wrapper } = await mountList(fullConfig, width);

    for (const row of rowsOf(wrapper)) {
      const meta = row.querySelector(".list-view-meta");
      const actions = row.querySelector(".action-button-container");

      for (const column of meta.children) {
        expectContained(column, meta, `meta column at ${width}px`);
      }
      expectNoHorizontalOverlap(
        meta,
        actions,
        `metadata vs row actions at ${width}px`,
      );
      // The columns are what a user sees collide, so assert on them too:
      // a contained-but-overlapping child would still print over the icons.
      for (const column of meta.children) {
        expectNoHorizontalOverlap(
          column,
          actions,
          `metadata column vs row actions at ${width}px`,
        );
      }
    }
  });

  it.each(WIDTHS)("never overflows the row at %ipx", async (width) => {
    const { wrapper } = await mountList(fullConfig, width);

    // Rows only: each row is its own clipping context (`overflow: hidden`), so
    // asserting on the wrapper could never fail no matter how badly a row
    // overflowed.
    for (const row of rowsOf(wrapper)) {
      expectNoHorizontalOverflow(row, `row at ${width}px`);
    }
  });

  it("keeps the columns straight when rows carry icons", async () => {
    // The adapter pages render an <Image> beside the title, which settles
    // after mount; the left column absorbs it, so the meta columns must not
    // move. This is the branch those pages actually use.
    const { wrapper } = await mountList(
      {
        ...fullConfig,
        iconProp: "icon",
        listOfTools: ITEMS.map((item) => ({
          ...item,
          icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='38' height='38'%3E%3C/svg%3E",
        })),
      },
      1100,
    );

    expectAlignedX(
      queryAll(wrapper, ".adapters-list-profile-container"),
      "owner column with row icons",
    );
    expectAlignedX(
      queryAll(wrapper, ".list-view-modified-container"),
      "updated column with row icons",
    );
  });

  it("absorbs an over-long owner address by truncating it, not by moving the column", async () => {
    const { wrapper } = await mountList(fullConfig, 800);

    const longLabel = queryAll(wrapper, ".shared-username").find((el) =>
      el.textContent.includes("a-really-long-service-account-name"),
    );
    expectTruncated(longLabel, "over-long owner address");
    expectAlignedX(
      queryAll(wrapper, ".adapters-list-profile-container"),
      "owner column at the narrowest supported width",
    );
  });

  describe("owner-only pages", () => {
    it.each(
      WIDTHS,
    )("stay aligned, contained and overflow-free at %ipx", async (width) => {
      const { wrapper } = await mountList(ownerOnlyConfig, width);

      expect(queryAll(wrapper, ".list-view-modified-container")).toHaveLength(
        0,
      );

      expectAlignedX(
        queryAll(wrapper, ".adapters-list-profile-container"),
        `owner column, owner-only page at ${width}px`,
      );

      for (const row of rowsOf(wrapper)) {
        const meta = row.querySelector(".list-view-meta");
        const actions = row.querySelector(".action-button-container");
        for (const column of meta.children) {
          expectContained(column, meta, `meta column at ${width}px`);
        }
        expectNoHorizontalOverlap(
          meta,
          actions,
          `metadata vs row actions at ${width}px`,
        );
        expectNoHorizontalOverflow(row, `row at ${width}px`);
      }
    });
  });
});
