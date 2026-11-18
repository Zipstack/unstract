/*
 * Development-only demo pages that prove the version switch (UN-4271). They
 * ship in every build but are reachable only with VITE_V1_DEV_ROUTES=true.
 * DemoReviewPage stands in for Human Review: its "Switch to old version"
 * control is the shape of the one P6-T07 builds. DemoPage also lists the
 * organisation's LLM adapters, the sample of the data layer (UN-4313).
 */

import { useQuery } from "@tanstack/react-query";
import { QueryView } from "@v1/components/patterns/QueryView";
import { adapterQueries } from "@v1/services/adapters";
import { setOrganizationId } from "@v1/services/context";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import type { JSX } from "react";
import { Link, useParams } from "react-router-dom";

function LlmAdapters(): JSX.Element {
  const adapters = useQuery(adapterQueries.list({ adapterType: "LLM" }));
  return (
    <QueryView query={adapters}>
      {(rows) =>
        rows.length === 0 ? (
          <p className="ui:text-body-small">No LLM adapters yet.</p>
        ) : (
          <ul className="ui:flex ui:flex-col ui:gap-1">
            {rows.map((row) => (
              <li key={row.id}>{row.adapter_name}</li>
            ))}
          </ul>
        )
      }
    </QueryView>
  );
}

export function DemoPage(): JSX.Element {
  // Stand-in until UN-4314's session: the URL's org name is the org id on OSS only.
  setOrganizationId(useParams().orgName ?? null);
  return (
    <main className="ui:flex ui:flex-col ui:gap-4 ui:p-6" data-testid="v1-demo">
      <h1 className="ui:text-page-title">v1 demo page</h1>
      <section className="ui:flex ui:flex-col ui:gap-2">
        <h2 className="ui:text-section-title">LLM adapters</h2>
        <LlmAdapters />
      </section>
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
