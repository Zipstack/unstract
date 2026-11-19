import { expectGalleryAccessible, galleryMarkup } from "@v1/test";
import { expect, it } from "vitest";
import { BUTTON_GALLERY } from "./button.gallery";

// Markdown rather than a `.snap`, because v1 holds no `.snap` files.
it("matches the committed markup of every gallery entry", async () => {
  await expect(
    galleryMarkup("Buttons and links markup", BUTTON_GALLERY),
  ).toMatchFileSnapshot("./__snapshots__/markup.md");
});

it("every gallery entry passes axe", () =>
  expectGalleryAccessible(BUTTON_GALLERY));
