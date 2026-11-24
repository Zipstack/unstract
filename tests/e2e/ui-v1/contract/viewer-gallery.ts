/**
 * The document viewer's gallery (UN-4645), as its browser tests need it: the
 * route, the section test ids, the long PDF's page count and the target marks.
 * Read from the frontend's own module, which imports nothing, so the spec and
 * the page cannot drift.
 */

export {
  GALLERY_IDS,
  LONG_PDF_PAGES,
  MARK_RGB,
  TARGETS,
  VIEWER_GALLERY_ROUTE,
  VIEWER_GALLERY_TEST_ID_PREFIX,
  type ViewerTarget,
} from "../../../../frontend/src/v1/components/patterns/document-viewer/gallery.targets.ts";
