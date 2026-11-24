/*
 * Development-only gallery of the document viewer (UN-4645): every entry of
 * VIEWER_GALLERY, PDFs included, in a real browser. Reachable only with
 * VITE_V1_DEV_ROUTES=true, like the other demo pages; the browser tests in
 * tests/e2e/ui-v1/specs/P1-T21.spec.ts run on it. Stands in until the
 * component gallery (P1-T01) can host these entries.
 */

import { VIEWER_GALLERY } from "@v1/components/patterns/document-viewer/document-viewer.gallery";
import { VIEWER_GALLERY_TEST_ID_PREFIX as PREFIX } from "@v1/components/patterns/document-viewer/gallery.targets";
import type { JSX } from "react";

export function DemoViewerPage(): JSX.Element {
  return (
    <main
      className="ui:flex ui:flex-col ui:gap-8 ui:p-6"
      data-testid="v1-demo-viewer"
    >
      <h1 className="ui:text-page-title">Document viewer gallery</h1>
      {VIEWER_GALLERY.map(({ id, name, element }) => (
        <section
          key={id}
          aria-labelledby={`${PREFIX}${id}-title`}
          data-testid={`${PREFIX}${id}`}
          className="ui:flex ui:flex-col ui:gap-2"
        >
          <h2 id={`${PREFIX}${id}-title`} className="ui:text-section-title">
            {name}
          </h2>
          {element}
        </section>
      ))}
    </main>
  );
}
