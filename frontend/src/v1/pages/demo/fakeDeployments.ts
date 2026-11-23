// TEMP (UN-4346): for dev testing only. Removed before merging; never merge this.
/*
 * A dummy "API deployments" endpoint that lives in the browser, so the
 * DataTable preview can be tried against server paging, sorting, filtering,
 * latency, errors and bulk POSTs without a backend. Requests are parsed from
 * a URL like a real endpoint's (`?page=2&page_size=25&ordering=-total_runs&search=masa`)
 * and answered after a delay, with the shape a DRF list returns.
 */

export type FakeDeployment = Readonly<{
  id: string;
  name: string;
  workflow: string;
  owner: string;
  last_run_at: string;
  total_runs: number;
  failing: boolean;
}>;

export type FakePage = Readonly<{
  count: number;
  results: readonly FakeDeployment[];
}>;

/** What the page's toggles change. */
export type FakeServerSettings = {
  latencyMs: number;
  failNext: "never" | "list" | "bulk" | "both";
  forceEmpty: boolean;
  slow: boolean;
};

export const fakeServer: FakeServerSettings = {
  latencyMs: 500,
  failNext: "never",
  forceEmpty: false,
  slow: false,
};

const NAMES = [
  "health-monitoring API",
  "API Hub - Purchase Order API",
  "masa_cms",
  "masa_eob_extraction",
  "UCC_Formatting API",
  "forsys_ami_api",
  "invoice-parser",
  "bank-statement-extractor",
  "kyc-documents",
];
const OWNERS = ["ritwik", "milan", "vikash", "jagadeeswaran", "deepak"];

const DATASET: FakeDeployment[] = Array.from({ length: 1000 }, (_, i) => {
  const base = NAMES[i % NAMES.length];
  const round = Math.floor(i / NAMES.length);
  const day = (i * 7) % 31;
  return {
    id: `fake-${i + 1}`,
    name: round === 0 ? base : `${base} ${round + 1}`,
    workflow: `${base.toLowerCase().replaceAll(/[^a-z0-9]+/g, "_")}_workflow`,
    owner: OWNERS[(i * 3) % OWNERS.length],
    last_run_at: new Date(
      Date.UTC(2026, 7, day + 1, (i * 5) % 24),
    ).toISOString(),
    total_runs: (i * 7919) % 300_000,
    failing: i % 11 === 1,
  };
});

/** Fields `ordering` accepts, as a DRF OrderingFilter would. */
export const ORDERING_FIELDS = [
  "name",
  "workflow",
  "owner",
  "last_run_at",
  "total_runs",
] as const;

function wait(): Promise<void> {
  const base = fakeServer.slow ? 3000 : fakeServer.latencyMs;
  // ±25% jitter, so responses do not all land at once.
  const ms = base * (0.75 + Math.random() * 0.5);
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class FakeHttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** GET /fake/api-deployments/?page&page_size&ordering&search */
export async function fakeGet(url: string): Promise<FakePage> {
  await wait();
  if (fakeServer.failNext === "list" || fakeServer.failNext === "both") {
    throw new FakeHttpError(503, "The server did not answer (forced error).");
  }
  const params = new URL(url, "https://fake.local").searchParams;
  const page = Math.max(1, Number(params.get("page") ?? 1));
  const size = Math.max(1, Number(params.get("page_size") ?? 25));
  const search = (params.get("search") ?? "").trim().toLowerCase();
  const ordering = params.get("ordering") ?? "";

  let rows = fakeServer.forceEmpty ? [] : DATASET;
  if (search) {
    rows = rows.filter(
      (row) =>
        row.name.toLowerCase().includes(search) ||
        row.workflow.includes(search) ||
        row.owner.includes(search),
    );
  }
  const field = ordering.replace(/^-/, "") as keyof FakeDeployment;
  if ((ORDERING_FIELDS as readonly string[]).includes(field)) {
    const sign = ordering.startsWith("-") ? -1 : 1;
    rows = [...rows].sort((a, b) => {
      const x = a[field];
      const y = b[field];
      const order =
        typeof x === "number" && typeof y === "number"
          ? x - y
          : String(x).localeCompare(String(y), undefined, { numeric: true });
      return order * sign;
    });
  }
  const start = (page - 1) * size;
  return { count: rows.length, results: rows.slice(start, start + size) };
}

/** POST /fake/api-deployments/bulk/ {action, ids} */
export async function fakePost(
  action: string,
  ids: readonly string[],
): Promise<{ updated: number }> {
  await wait();
  if (fakeServer.failNext === "bulk" || fakeServer.failNext === "both") {
    throw new FakeHttpError(500, `Could not ${action} (forced error).`);
  }
  return { updated: ids.length };
}
