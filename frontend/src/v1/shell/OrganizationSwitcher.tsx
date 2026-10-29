import {
  describeOrganization,
  initial,
  landingPath,
  organizationInitials,
} from "@v1/lib/organizations";
import {
  listOrganizations,
  type Organization,
  switchOrganization,
} from "@v1/services/organizations";
import axios from "axios";
import {
  ArrowLeftRight,
  ArrowRightLeft,
  ChevronRight,
  ChevronsUpDown,
  Search,
} from "lucide-react";
import { AlertDialog, Popover } from "radix-ui";
import { useCallback, useRef, useState } from "react";

// Frames NEW10 (1638:44855) and page 19, O01 to O04 (2259:182 to 2259:656).
const AVATAR_COLOURS = [
  "bg-blue-100 text-blue-700",
  "bg-teal-100 text-teal-700",
  "bg-amber-100 text-amber-700",
  "bg-rose-100 text-rose-700",
  "bg-violet-100 text-violet-700",
];
const SIGN_IN_PATH = "/landing";
const BUTTON =
  "inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-[var(--border)] bg-[var(--card)] px-3 text-[13px] font-medium text-[var(--foreground)] hover:bg-[var(--muted)] disabled:opacity-50";

export interface CurrentOrganization {
  id: string;
  /** The URL name: paths are /<name>/... */
  name: string;
  displayName: string;
}

type ListState =
  | { status: "idle" | "loading" | "error" }
  | { status: "ready"; organizations: Organization[] };

function useOrganizationList() {
  const [state, setState] = useState<ListState>({ status: "idle" });
  const latest = useRef(0);
  const load = useCallback(() => {
    const request = ++latest.current;
    setState({ status: "loading" });
    listOrganizations().then(
      (organizations) => {
        if (request === latest.current) {
          setState({ status: "ready", organizations });
        }
      },
      (error: unknown) => {
        if (request !== latest.current) {
          return;
        }
        // 412: the backend logged the session out while building the list.
        if (axios.isAxiosError(error) && error.response?.status === 412) {
          window.location.assign(SIGN_IN_PATH);
          return;
        }
        setState({ status: "error" });
      },
    );
  }, []);
  return { state, load };
}

function OrgAvatar({
  id,
  name,
  size,
}: {
  id: string;
  name: string;
  size: "md" | "sm";
}) {
  const colour =
    AVATAR_COLOURS[
      [...id].reduce((sum, c) => sum + c.charCodeAt(0), 0) %
        AVATAR_COLOURS.length
    ];
  const box =
    size === "md"
      ? "size-8 rounded-[10px] text-xs"
      : "size-7 rounded-md text-[11px]";
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center font-semibold ${box} ${colour}`}
    >
      {organizationInitials(name)}
    </span>
  );
}

function OrgLine({ org }: { org: Organization }) {
  return (
    <span className="flex min-w-0 flex-1 flex-col">
      <span className="truncate text-[13px] font-medium leading-5 text-[var(--foreground)]">
        {org.display_name}
      </span>
      <span className="truncate text-xs leading-4 text-[var(--muted-foreground)]">
        {describeOrganization(org)}
      </span>
    </span>
  );
}

function ConfirmSwitch({
  from,
  to,
  onClose,
}: {
  from: Organization;
  to: Organization;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function confirm() {
    setBusy(true);
    setFailed(false);
    try {
      await switchOrganization(to.id);
      // A full load clears every client store, so nothing of the old organisation survives.
      window.location.assign(
        landingPath(window.location.pathname, from.name, to.name),
      );
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <AlertDialog.Root open onOpenChange={(open) => !open && !busy && onClose()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
        <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[520px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[var(--border)] bg-[var(--sidebar)] shadow-[0_12px_32px_0_#0000002e]">
          <div className="flex gap-3 p-6">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-[var(--primary-muted)]">
              <ArrowRightLeft
                aria-hidden
                className="size-[18px] text-[var(--primary)]"
              />
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <AlertDialog.Title className="text-base font-semibold leading-6 text-[var(--foreground)]">
                Switch to {to.display_name}?
              </AlertDialog.Title>
              <AlertDialog.Description className="text-[13px] leading-5 text-[var(--muted-foreground)]">
                Every screen is replaced — projects, workflows, deployments,
                logs, members and the plan. Nothing is lost; you can switch back
                from here.
              </AlertDialog.Description>
            </div>
          </div>
          <div className="mx-6 mb-6 flex items-center gap-3 rounded-[10px] bg-[var(--muted)] px-4 py-3.5">
            <OrgAvatar id={from.id} name={from.display_name} size="sm" />
            <OrgLine org={{ ...from, region: undefined }} />
            <ChevronRight
              aria-hidden
              className="size-[18px] text-[var(--muted-foreground)]"
            />
            <OrgAvatar id={to.id} name={to.display_name} size="sm" />
            <OrgLine org={{ ...to, region: undefined }} />
          </div>
          {failed && (
            <p
              role="alert"
              className="mx-6 -mt-3 mb-4 text-[13px] text-[var(--destructive)]"
            >
              Could not switch. Try again.
            </p>
          )}
          <div className="flex justify-end gap-2 border-t border-[var(--border)] px-6 py-5">
            <AlertDialog.Cancel disabled={busy} className={`${BUTTON} h-9`}>
              Cancel
            </AlertDialog.Cancel>
            <button
              type="button"
              disabled={busy}
              onClick={() => void confirm()}
              className="inline-flex h-9 items-center gap-2 rounded-[10px] bg-[var(--primary)] px-3.5 text-sm font-medium text-[var(--primary-foreground)] disabled:opacity-60"
            >
              <ArrowRightLeft aria-hidden className="size-4" />
              Switch organisation
            </button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

/**
 * The organisation pill and its switcher (page 19). The list loads when the
 * switcher opens; until then, and if it fails, the pill shows the current name.
 * ponytail: no Create organisation item yet; v0 has none and the plan rule that
 * hides it is undecided (P2-T02 plan, gap 6).
 */
export function OrganizationSwitcher({
  current,
}: {
  current: CurrentOrganization;
}) {
  const { state, load } = useOrganizationList();
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<Organization>();

  const organizations = state.status === "ready" ? state.organizations : [];
  const shown = organizations.filter((org) =>
    org.display_name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const count = organizations.length;

  return (
    <>
      <Popover.Root
        onOpenChange={(open) => {
          if (open && state.status !== "ready") {
            load();
          }
          if (!open) {
            setQuery("");
          }
        }}
      >
        <Popover.Trigger
          aria-label={`Organisation: ${current.displayName}`}
          className="flex h-9 w-[171px] items-center gap-2 rounded-[10px] border border-[var(--border)] bg-[var(--card)] px-2 outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-[var(--primary)] text-[11px] font-semibold text-[var(--primary-foreground)]">
            {initial(current.displayName)}
          </span>
          <span className="flex-1 truncate text-left text-[13px] font-medium leading-5 text-[var(--foreground)]">
            {current.displayName}
          </span>
          <ChevronsUpDown
            aria-hidden
            className="size-3.5 text-[var(--muted-foreground)]"
          />
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            align="end"
            sideOffset={8}
            collisionPadding={8}
            className="z-50 flex max-h-[var(--radix-popover-content-available-height)] w-[360px] flex-col rounded-xl border border-[var(--border)] bg-[var(--popover)] p-1.5 shadow-[0_8px_24px_-4px_#0000001a]"
          >
            <label className="mb-1 flex h-9 items-center gap-2 rounded-lg px-2.5 text-[var(--muted-foreground)]">
              <Search aria-hidden className="size-4" />
              <input
                type="search"
                aria-label="Find an organisation"
                placeholder="Find an organisation"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="flex-1 bg-transparent text-[13px] text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
              />
            </label>
            {(state.status === "loading" || state.status === "idle") && (
              <p
                aria-live="polite"
                className="px-3 py-4 text-[13px] text-[var(--muted-foreground)]"
              >
                Loading…
              </p>
            )}
            {state.status === "error" && (
              <div
                role="alert"
                className="flex items-center justify-between gap-3 px-3 py-3"
              >
                <span className="text-[13px] text-[var(--muted-foreground)]">
                  Could not load your organisations.
                </span>
                <button type="button" className={BUTTON} onClick={load}>
                  Retry
                </button>
              </div>
            )}
            {state.status === "ready" && (
              <>
                {shown.length === 0 ? (
                  <p className="px-3 py-4 text-[13px] text-[var(--muted-foreground)]">
                    No organisations match
                  </p>
                ) : (
                  <p className="px-1.5 pt-1 pb-2 text-[11px] font-semibold uppercase leading-4 tracking-[0.08em] text-[var(--muted-foreground)]">
                    You belong to {count} organisation{count === 1 ? "" : "s"}
                  </p>
                )}
                <ul className="flex min-h-0 flex-col overflow-y-auto">
                  {shown.map((org) => {
                    const isCurrent = org.id === current.id;
                    return (
                      <li
                        key={org.id}
                        {...(isCurrent ? { "aria-current": "true" } : {})}
                        className={`flex h-14 items-center gap-2.5 rounded-lg px-2.5 ${isCurrent ? "bg-[#f5f5fa]" : ""}`}
                      >
                        <OrgAvatar
                          id={org.id}
                          name={org.display_name}
                          size="md"
                        />
                        <OrgLine org={org} />
                        {isCurrent ? (
                          <span className="rounded bg-[var(--primary-muted)] px-2 py-[3px] text-xs font-medium text-[var(--primary)]">
                            Current
                          </span>
                        ) : (
                          <button
                            type="button"
                            aria-label={`Switch to ${org.display_name}`}
                            className={BUTTON}
                            onClick={() => setTarget(org)}
                          >
                            <ArrowLeftRight aria-hidden className="size-4" />
                            Switch
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {count === 1 && (
                  <p className="px-3 py-2 text-[13px] text-[var(--muted-foreground)]">
                    Nothing to switch to.
                  </p>
                )}
              </>
            )}
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
      {target && (
        <ConfirmSwitch
          from={{
            ...organizations.find((org) => org.id === current.id),
            id: current.id,
            name: current.name,
            display_name: current.displayName,
          }}
          to={target}
          onClose={() => setTarget(undefined)}
        />
      )}
    </>
  );
}
