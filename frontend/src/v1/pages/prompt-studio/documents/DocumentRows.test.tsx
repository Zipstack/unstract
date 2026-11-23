import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { UploadingRow } from "./DocumentRows";

const file = new File([new Uint8Array(611 * 1024)], "chase_feb_2026.pdf");

it("shows bytes sent of the total while uploading (D06)", () => {
  renderV1(
    <ul>
      <UploadingRow
        row={{ key: "k", file, loaded: 380 * 1024, started: true }}
      />
    </ul>,
  );
  expect(screen.getByText("Uploading · 380 KB of 611 KB")).toBeInTheDocument();
  expect(
    screen.getByRole("progressbar", { name: "Uploading chase_feb_2026.pdf" }),
  ).toHaveAttribute("aria-valuenow", String(380 * 1024));
});

it("says a queued file is waiting", () => {
  renderV1(
    <ul>
      <UploadingRow row={{ key: "k", file, loaded: 0, started: false }} />
    </ul>,
  );
  expect(screen.getByText("Waiting to upload · 611 KB")).toBeInTheDocument();
});

it("never reports more sent than the file holds", () => {
  renderV1(
    <ul>
      <UploadingRow
        row={{ key: "k", file, loaded: 700 * 1024, started: true }}
      />
    </ul>,
  );
  expect(screen.getByText("Uploading · 611 KB of 611 KB")).toBeInTheDocument();
});
