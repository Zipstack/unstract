/*
 * Development-only demo pages that prove the version switch (UN-4271). They
 * ship in every build but are reachable only with VITE_V1_DEV_ROUTES=true.
 * DemoReviewPage stands in for Human Review: its "Switch to old version"
 * control is the shape of the one P6-T07 builds. DemoPage also lists the
 * organisation's LLM adapters, the sample of the data layer (UN-4313).
 */

import { useQuery } from "@tanstack/react-query";
import { QueryView } from "@v1/components/patterns/QueryView";
// TEMP (UN-4346): for dev testing only. Removed before merging; never merge this.
import { DATA_TABLE_GALLERY } from "@v1/components/ui/data-table/data-table.gallery";
import { THEME_MODES } from "@v1/lib/theme";
import { adapterQueries } from "@v1/services/adapters";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import { selectThemeMode, useThemeStore } from "@v1/stores/theme";
import type { JSX } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTablePlayground } from "./DataTablePlayground";

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

// TEMP (UN-4346): for dev testing only. Removed before merging; never merge this.
function DataTablePreview(): JSX.Element {
  const mode = useThemeStore(selectThemeMode);
  const setPreference = useThemeStore((s) => s.setPreference);
  return (
    <section className="ui:flex ui:flex-col ui:gap-8">
      <div className="ui:flex ui:items-center ui:gap-2">
        <h2 className="ui:text-section-title ui:text-foreground">
          DataTable preview (UN-4346)
        </h2>
        {THEME_MODES.map((theme) => (
          <button
            key={theme}
            type="button"
            aria-pressed={mode === theme}
            onClick={() => setPreference(theme)}
            className="ui:cursor-pointer ui:rounded-md ui:border ui:border-solid ui:border-border ui:bg-card ui:px-3 ui:py-1 ui:text-body-small ui:text-foreground ui:aria-pressed:bg-primary-muted"
          >
            {theme}
          </button>
        ))}
      </div>
      <DataTablePlayground />
      {DATA_TABLE_GALLERY.map(({ name, element }) => (
        <div key={name} className="ui:flex ui:flex-col ui:gap-2">
          <h3 className="ui:m-0 ui:text-body ui:font-semibold ui:text-foreground">
            {name}
          </h3>
          {element}
        </div>
      ))}
    </section>
  );
}

export function DemoPage(): JSX.Element {
  return (
    <main
      className="ui:flex ui:min-h-full ui:flex-col ui:gap-4 ui:bg-background ui:p-6"
      data-testid="v1-demo"
    >
      <h1 className="ui:text-page-title ui:text-foreground">v1 demo page</h1>
      <section className="ui:flex ui:flex-col ui:gap-2">
        <h2 className="ui:text-section-title">LLM adapters</h2>
        <LlmAdapters />
      </section>
      {/* TEMP (UN-4346): for dev testing only. Removed before merging; never merge this. */}
      <DataTablePreview />
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
