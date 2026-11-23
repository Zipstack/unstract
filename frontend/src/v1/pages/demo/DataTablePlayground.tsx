// TEMP (UN-4346): for dev testing only. Removed before merging; never merge this.
/*
 * The DataTable against a dummy endpoint (`fakeDeployments.ts`): server
 * paging, sorting and search through query params, real latency, and
 * toggles that force an error, an empty result or a slow response. Bulk
 * actions POST to the dummy endpoint and toast the result.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@v1/components/ui/button";
import {
  DataTable,
  type DataTableColumn,
  type DataTableSort,
} from "@v1/components/ui/data-table";
import { Field, Input, SearchField } from "@v1/components/ui/form";
import { Radio, RadioGroup, Switch } from "@v1/components/ui/toggles";
import { toast } from "@v1/lib/notify";
import { type JSX, useState } from "react";
import {
  type FakeDeployment,
  FakeHttpError,
  type FakeServerSettings,
  fakeGet,
  fakePost,
  fakeServer,
} from "./fakeDeployments";

const SORT_FIELD: Record<string, string> = {
  name: "name",
  workflow: "workflow",
  owner: "owner",
  lastRun: "last_run_at",
  totalRuns: "total_runs",
};

const dateText = (iso: string): string =>
  new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  });

const COLUMNS: readonly DataTableColumn<FakeDeployment>[] = [
  {
    id: "name",
    header: "Name",
    sortKey: "name",
    width: "xl",
    cell: (row) => (
      <span className="ui:block ui:truncate ui:font-medium">{row.name}</span>
    ),
  },
  {
    id: "workflow",
    header: "Workflow",
    sortKey: "workflow",
    priority: 3,
    cell: (row) => <span className="ui:block ui:truncate">{row.workflow}</span>,
  },
  {
    id: "owner",
    header: "Owner",
    sortKey: "owner",
    priority: 2,
    width: "md",
    cell: (row) => row.owner,
  },
  {
    id: "lastRun",
    header: "Last run",
    sortKey: "last_run_at",
    width: "lg",
    cell: (row) => (
      <span className="ui:flex ui:flex-col">
        <span>{dateText(row.last_run_at)}</span>
        {row.failing && (
          <span className="ui:text-caption ui:text-destructive">failed</span>
        )}
      </span>
    ),
  },
  {
    id: "totalRuns",
    header: "Total runs",
    sortKey: "total_runs",
    align: "end",
    priority: 4,
    width: "md",
    cell: (row) => row.total_runs.toLocaleString("en-US"),
  },
];

const errorText = (error: unknown): string =>
  error instanceof FakeHttpError
    ? `${error.status}: ${error.message}`
    : String(error);

export function DataTablePlayground(): JSX.Element {
  const [settings, setSettings] = useState<FakeServerSettings>({
    ...fakeServer,
  });
  const update = (patch: Partial<FakeServerSettings>): void => {
    const next = { ...settings, ...patch };
    Object.assign(fakeServer, next);
    setSettings(next);
  };

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState<DataTableSort | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (sort) {
    const field = SORT_FIELD[sort.columnId];
    params.set("ordering", sort.direction === "desc" ? `-${field}` : field);
  }
  if (search) {
    params.set("search", search);
  }
  const url = `/fake/api-deployments/?${params}`;

  const query = useQuery({
    queryKey: ["un4346-fake-deployments", url],
    queryFn: () => fakeGet(url),
    placeholderData: keepPreviousData,
    retry: false,
  });

  const bulk = async (
    action: string,
    ids: readonly string[],
    clearSelection: () => void,
  ): Promise<void> => {
    setBusy(action);
    try {
      const { updated } = await fakePost(action, ids);
      toast.success(`${action}: ${updated} deployments`, {
        description: `POST /fake/api-deployments/bulk/ answered 200.`,
      });
      clearSelection();
      void query.refetch();
    } catch (error) {
      toast.error(`${action} failed`, { description: errorText(error) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section
      aria-label="DataTable against a dummy endpoint"
      className="ui:flex ui:flex-col ui:gap-4"
    >
      <h3 className="ui:m-0 ui:text-body ui:font-semibold ui:text-foreground">
        Dummy endpoint: GET {url}
      </h3>
      <div className="ui:flex ui:flex-wrap ui:items-end ui:gap-6 ui:rounded-lg ui:border ui:border-solid ui:border-border ui:bg-card ui:p-4">
        <Field label="Latency (ms)" className="ui:w-40">
          <Input
            type="number"
            min={0}
            step={100}
            value={settings.latencyMs}
            onChange={(event) =>
              update({ latencyMs: Number(event.target.value) || 0 })
            }
          />
        </Field>
        <Switch
          label="Slow (3 s)"
          checked={settings.slow}
          onCheckedChange={(slow) => update({ slow })}
        />
        <Switch
          label="Empty result"
          checked={settings.forceEmpty}
          onCheckedChange={(forceEmpty) => update({ forceEmpty })}
        />
        <RadioGroup
          label="Force an error on"
          value={settings.failNext}
          onValueChange={(value) =>
            update({ failNext: value as FakeServerSettings["failNext"] })
          }
          className="ui:min-w-64"
        >
          <Radio value="never" label="Nothing" />
          <Radio value="list" label="The list (GET)" />
          <Radio value="bulk" label="Bulk actions (POST)" />
          <Radio value="both" label="Both" />
        </RadioGroup>
        <Button variant="outline" onClick={() => void query.refetch()}>
          Refetch
        </Button>
      </div>
      <DataTable
        label="Dummy API deployments"
        columns={COLUMNS}
        rows={query.data?.results ?? []}
        getRowId={(row) => row.id}
        getRowLabel={(row) => row.name}
        getRowTone={(row) => (row.failing ? "failure" : "default")}
        loading={query.isFetching}
        error={
          query.isError
            ? {
                title: "Could not load deployments",
                message: errorText(query.error),
                onRetry: () => void query.refetch(),
              }
            : null
        }
        filtered={search !== ""}
        sort={sort}
        onSortChange={(next) => {
          setSort(next);
          setPage(1);
        }}
        pagination={{
          mode: "server",
          page,
          pageSize,
          total: query.data?.count ?? 0,
          onPageChange: setPage,
          onPageSizeChange: setPageSize,
        }}
        selectable
        selectedIds={selected}
        onSelectionChange={setSelected}
        bulkActions={({ selectedIds, clearSelection }) => (
          <>
            <Button
              variant="outline"
              size="sm"
              loading={busy === "Restart"}
              onClick={() => void bulk("Restart", selectedIds, clearSelection)}
            >
              Restart selected
            </Button>
            <Button
              variant="destructive"
              size="sm"
              loading={busy === "Delete"}
              onClick={() => void bulk("Delete", selectedIds, clearSelection)}
            >
              Delete selected
            </Button>
          </>
        )}
        renderExpanded={(row) => (
          <dl className="ui:m-0 ui:grid ui:grid-cols-4 ui:gap-2 ui:text-body-small">
            <dt className="ui:text-muted-foreground">Id</dt>
            <dd className="ui:m-0">{row.id}</dd>
            <dt className="ui:text-muted-foreground">Workflow</dt>
            <dd className="ui:m-0">{row.workflow}</dd>
          </dl>
        )}
        onRowClick={(row) => toast.info(`Row click: ${row.name}`)}
        rowActions={(row) => [
          {
            id: "edit",
            label: "Edit",
            onSelect: () => toast.info(`Edit ${row.name}`),
          },
          {
            id: "delete",
            label: "Delete",
            destructive: true,
            onSelect: () =>
              void bulk("Delete", [row.id], () => setSelected([])),
          },
        ]}
        toolbar={
          <SearchField
            aria-label="Search deployments"
            placeholder="Search name, workflow or owner"
            value={search}
            onValueChange={(value) => {
              setSearch(value);
              setPage(1);
            }}
            className="ui:max-w-96"
          />
        }
        footer={`Server answered ${query.data?.count ?? 0} matching rows${query.isFetching ? " (fetching…)" : ""}.`}
      />
    </section>
  );
}
