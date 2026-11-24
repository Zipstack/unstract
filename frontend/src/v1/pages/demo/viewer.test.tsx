import { screen, within } from "@testing-library/react";
import { VIEWER_GALLERY } from "@v1/components/patterns/document-viewer/document-viewer.gallery";
import { VIEWER_GALLERY_TEST_ID_PREFIX } from "@v1/components/patterns/document-viewer/gallery.targets";
import {
  installIntersectionObserver,
  installResizeObserver,
  renderV1,
} from "@v1/test";
import { beforeEach, expect, it, vi } from "vitest";
import { DemoViewerPage } from "./viewer";

// pdf.js needs a real browser; the PDFs stay loading here.
vi.mock("@v1/lib/pdf/pdfjs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@v1/lib/pdf/pdfjs")>();
  return {
    ...actual,
    openPdfDocument: () => ({
      promise: new Promise(() => undefined),
      destroy: () => undefined,
    }),
  };
});

beforeEach(() => {
  installResizeObserver();
  installIntersectionObserver();
});

it("shows every gallery entry under its own heading, by its test id", () => {
  renderV1(<DemoViewerPage />, {
    route: "/acme/v1-demo-viewer",
    path: "/:orgName/v1-demo-viewer",
  });
  for (const { id, name } of VIEWER_GALLERY) {
    const section = screen.getByTestId(`${VIEWER_GALLERY_TEST_ID_PREFIX}${id}`);
    expect(section).toHaveAccessibleName(name);
    expect(
      within(section).getByRole("heading", { level: 2, name }),
    ).toBeInTheDocument();
  }
});
