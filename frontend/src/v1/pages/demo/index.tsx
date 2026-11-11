/*
 * Development-only demo pages that prove the version switch (UN-4271). They
 * ship in every build but are reachable only with VITE_V1_DEV_ROUTES=true.
 * DemoReviewPage stands in for Human Review: its "Switch to old version"
 * control is the shape of the one P6-T07 builds.
 */

import { useOldVersionStore } from "@v1/stores/oldVersion";
import type { JSX } from "react";
import { Link, useParams } from "react-router-dom";

export function DemoPage(): JSX.Element {
  return (
    <main className="ui:p-6" data-testid="v1-demo">
      <h1 className="ui:text-page-title">v1 demo page</h1>
    </main>
  );
}

export function DemoReviewPage(): JSX.Element {
  // useParams decodes, so encode again to keep e.g. `a%2Fb` one segment.
  const org = encodeURIComponent(useParams().orgName ?? "");
  const setOldVersion = useOldVersionStore((s) => s.setOldVersion);
  return (
    <main className="ui:p-6" data-testid="v1-demo-review">
      <h1 className="ui:text-page-title">v1 demo review</h1>
      <nav className="ui:flex ui:gap-4">
        <Link to={`/${org}/v1-demo-review`}>Queue</Link>
        <Link to={`/${org}/v1-demo-review/details`}>Details</Link>
      </nav>
      <button type="button" onClick={() => setOldVersion(true)}>
        Switch to old version
      </button>
    </main>
  );
}
