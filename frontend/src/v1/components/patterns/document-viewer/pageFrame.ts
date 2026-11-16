/**
 * The box a page or an image sits in, shared by PdfPage and ImageView. It is
 * sized by `--page-width` and `--page-height`, which each sets in its style
 * attribute: the size is runtime geometry, not a token.
 */
export const PAGE_FRAME_CLASS =
  "ui:relative ui:h-(--page-height) ui:w-(--page-width) ui:shrink-0 ui:bg-card ui:shadow-sm";
