import { expect, it } from "vitest";
import { expectGalleryAccessible } from "./gallery";

it("starts an accessibility failure with the entry's name", async () => {
  const entries = [
    { name: "named button", element: <button type="button">Save</button> },
    { name: "unnamed button", element: <button type="button" /> },
  ];
  await expect(expectGalleryAccessible(entries)).rejects.toThrow(
    /^unnamed button: .*button-name/s,
  );
});
