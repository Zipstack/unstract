/*
 * Every provider the supported-adapters and supported-connectors endpoints
 * return (Zipstack/unstract @ 3c59e85, unstract-cloud @ c6e32e0), with the
 * `icon` each one sends. `hasMark` says whether the design draws a mark for it.
 * The rows are JSON so they stay data, not code.
 */
import type { ProviderCategory } from "@v1/lib/icons";
import rows from "./providers.fixture.json";

export type ProviderFixture = Readonly<{
  kind: "adapter" | "connector";
  category: ProviderCategory;
  key: string;
  name: string;
  icon: string;
  hasMark: boolean;
}>;

const KINDS: ReadonlySet<string> = new Set(["adapter", "connector"]);
const CATEGORIES: ReadonlySet<string> = new Set<ProviderCategory>([
  "llm",
  "embedding",
  "vector-db",
  "text-extractor",
  "connector",
]);

for (const row of rows) {
  if (!KINDS.has(row.kind) || !CATEGORIES.has(row.category)) {
    throw new Error(`providers.fixture.json: bad kind/category in ${row.key}`);
  }
}

export const PROVIDERS = rows as readonly ProviderFixture[];
