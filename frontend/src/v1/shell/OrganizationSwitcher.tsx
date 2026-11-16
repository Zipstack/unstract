import {
  InlineAlert,
  Skeleton,
  SkeletonAvatar,
  SkeletonText,
} from "@v1/components/ui/feedback";
import { ACTION_ICONS, SHELL_ICONS } from "@v1/lib/icons";
import {
  describeOrganization,
  initial,
  landingPath,
  organizationInitials,
} from "@v1/lib/organizations";
import { getPortalContainer } from "@v1/lib/portal";
import {
  listOrganizations,
  type Organization,
  OrganizationError,
  organizationLoginUrl,
  switchOrganization,
} from "@v1/services/organizations";
import { ArrowRightLeft } from "lucide-react";
import { AlertDialog, Popover as RadixPopover } from "radix-ui";
import { useCallback, useRef, useState } from "react";

// Frames NEW10 (1638:44855) and page 19, O01 to O04 (2259:182 to 2259:656).
// ponytail: one colour for every organisation avatar; the frames rotate five,
// which have no tokens yet. Rotate again once the tokens include an avatar palette.
const AVATAR_COLOUR = "ui:bg-primary-muted ui:text-primary";
const SIGN_IN_PATH = "/landing";
const PillIcon = SHELL_ICONS.orgSwitcher;
const SearchIcon = SHELL_ICONS.search;
const NextIcon = ACTION_ICONS.next;
const BUTTON =
  "ui:inline-flex ui:h-8 ui:items-center ui:gap-1.5 ui:rounded-lg ui:border ui:border-border ui:bg-card ui:text-body ui:font-medium ui:text-foreground ui:hover:bg-muted ui:disabled:opacity-50";

export interface CurrentOrganization {
  id: string;
  /** The URL name: paths are /<name>/... */
  name: string;
  displayName: string;
  /** The session's `org_switch_via_login`: switch by signing in again. */
  switchViaLogin?: boolean;
}

/**
 * Where an ended session sends the user. A known cause carries `code` and
 * `domain`, which v0's /error page explains (useSessionValid.js); signing in
 * again would only fail the same way. An empty body goes back to sign-in.
 * These are app routes, not API URLs, so they live here and not in services/.
 */
export function sessionEndedPath(body: unknown): string {
  const { code, domain } = (body ?? {}) as { code?: unknown; domain?: unknown };
  if (typeof code !== "string" || code === "") {
    return SIGN_IN_PATH;
  }
  const query = new URLSearchParams({ code });
  if (typeof domain === "string" && domain !== "") {
    query.set("domain", domain);
  }
  return `/error?${query}`;
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
        if (
          error instanceof OrganizationError &&
          error.kind === "session-ended"
        ) {
          window.location.assign(sessionEndedPath(error.body));
          return;
        }
        console.error("Could not load the organisations", error);
        setState({ status: "error" });
      },
    );
  }, []);
  return { state, load };
}

function OrgAvatar({ name, size }: { name: string; size: "md" | "sm" }) {
  const box =
    size === "md"
      ? "ui:size-8 ui:rounded-lg ui:text-caption"
      : "ui:size-7 ui:rounded-sm ui:text-overline";
  return (
    <span
      aria-hidden
      className={`ui:flex ui:shrink-0 ui:items-center ui:justify-center ui:font-semibold ${box} ${AVATAR_COLOUR}`}
    >
      {organizationInitials(name)}
    </span>
  );
}

function OrgLine({ org }: { org: Organization }) {
  return (
    <span className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col">
      <span className="ui:truncate ui:text-body-small ui:font-medium ui:text-foreground">
        {org.display_name}
      </span>
      <span className="ui:truncate ui:text-caption ui:text-muted-foreground">
        {describeOrganization(org)}
      </span>
    </span>
  );
}

function ConfirmSwitch({
  from,
  to,
  viaLogin,
  onClose,
  onAccessRemoved,
  returnFocus,
}: {
  from: Organization;
  to: Organization;
  viaLogin: boolean;
  onClose: () => void;
  /** The user lost access to `to`: the cached list is stale. */
  onAccessRemoved: () => void;
  /** The pill: the button that opened this dialog unmounted with the popover. */
  returnFocus: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<"retry" | "removed">();

  async function confirm() {
    setBusy(true);
    setFailed(undefined);
    if (viaLogin) {
      window.location.assign(organizationLoginUrl(to.id));
      return;
    }
    try {
      await switchOrganization(to.id);
      // A full load clears every client store, so nothing of the old organisation survives.
      window.location.assign(
        landingPath(window.location.pathname, from.name, to.name),
      );
    } catch (error) {
      console.error("Could not switch organisation", error);
      // Retrying cannot work once the user is out of the organisation.
      if (
        error instanceof OrganizationError &&
        error.kind === "access-removed"
      ) {
        setFailed("removed");
        onAccessRemoved();
        return;
      }
      setFailed("retry");
      setBusy(false);
    }
  }

  return (
    <AlertDialog.Root
      open
      onOpenChange={(open) =>
        !open && (!busy || failed === "removed") && onClose()
      }
    >
      <AlertDialog.Portal container={getPortalContainer()}>
        <AlertDialog.Overlay className="ui:fixed ui:inset-0 ui:z-50 ui:bg-scrim" />
        <AlertDialog.Content
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocus();
          }}
          className="ui:fixed ui:top-1/2 ui:left-1/2 ui:z-50 ui:w-130 ui:max-w-[calc(100vw-var(--space-8))] ui:-translate-x-1/2 ui:-translate-y-1/2 ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:shadow-xl"
        >
          <div className="ui:flex ui:gap-3 ui:px-6 ui:pt-6 ui:pb-1">
            <span className="ui:flex ui:size-9 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-lg ui:bg-primary-muted">
              <ArrowRightLeft
                aria-hidden
                className="ui:size-4.5 ui:text-primary"
              />
            </span>
            <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-1">
              <AlertDialog.Title className="ui:text-section-title ui:font-semibold ui:text-foreground">
                Switch to {to.display_name}?
              </AlertDialog.Title>
              <AlertDialog.Description className="ui:text-body-small ui:text-muted-foreground">
                Every screen is replaced — projects, workflows, deployments,
                logs, members and the plan. Nothing is lost; you can switch back
                from here.
              </AlertDialog.Description>
            </div>
          </div>
          <div className="ui:mx-6 ui:mb-6 ui:flex ui:items-center ui:gap-3 ui:rounded-lg ui:bg-muted ui:px-4 ui:py-3.5">
            <OrgAvatar name={from.display_name} size="sm" />
            <OrgLine org={{ ...from, region: undefined }} />
            <NextIcon
              aria-hidden
              className="ui:size-4.5 ui:text-muted-foreground"
            />
            <OrgAvatar name={to.display_name} size="sm" />
            <OrgLine org={{ ...to, region: undefined }} />
          </div>
          {failed && (
            <InlineAlert
              className="ui:mx-6 ui:-mt-3 ui:mb-4"
              title={
                failed === "removed"
                  ? `You no longer have access to ${to.display_name}.`
                  : "Could not switch. Try again."
              }
            />
          )}
          <div className="ui:flex ui:justify-end ui:gap-2 ui:border-t ui:border-border ui:px-6 ui:py-5">
            <AlertDialog.Cancel
              disabled={busy && failed !== "removed"}
              className={`${BUTTON} ui:h-9 ui:px-3.5`}
            >
              Cancel
            </AlertDialog.Cancel>
            <button
              type="button"
              disabled={busy}
              onClick={() => void confirm()}
              className="ui:inline-flex ui:h-9 ui:items-center ui:gap-2 ui:rounded-lg ui:bg-primary ui:px-3.5 ui:text-body ui:font-medium ui:text-primary-foreground ui:disabled:opacity-60"
            >
              <ArrowRightLeft aria-hidden className="ui:size-4" />
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
  // `from` is captured on Switch, so a reload after a 403 (which empties the
  // list) cannot blank the current organisation's details in the dialog.
  const [pending, setPending] = useState<{
    from: Organization;
    to: Organization;
  }>();
  const pill = useRef<HTMLButtonElement>(null);

  const organizations = state.status === "ready" ? state.organizations : [];
  const shown = organizations.filter((org) =>
    org.display_name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  // The current organisation can be missing from the list; it still counts.
  const count =
    organizations.length +
    (organizations.some((o) => o.id === current.id) ? 0 : 1);
  const nothingToSwitchTo = organizations.every((o) => o.id === current.id);

  return (
    <>
      <RadixPopover.Root
        onOpenChange={(open) => {
          if (open && state.status !== "ready") {
            load();
          }
          if (!open) {
            setQuery("");
          }
        }}
      >
        <RadixPopover.Trigger
          ref={pill}
          aria-label={`Organisation: ${current.displayName}`}
          className="ui:flex ui:h-9 ui:w-42.75 ui:items-center ui:gap-2 ui:rounded-lg ui:border ui:border-border ui:bg-card ui:px-2 ui:outline-none ui:focus-visible:focus-ring "
        >
          <span className="ui:flex ui:size-6 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-sm ui:bg-primary ui:text-overline ui:font-semibold ui:text-primary-foreground">
            {initial(current.displayName)}
          </span>
          <span className="ui:flex-1 ui:truncate ui:text-left ui:text-body-small ui:font-medium ui:text-foreground">
            {current.displayName}
          </span>
          <PillIcon
            aria-hidden
            className="ui:size-3.5 ui:text-muted-foreground"
          />
        </RadixPopover.Trigger>
        <RadixPopover.Portal container={getPortalContainer()}>
          <RadixPopover.Content
            align="end"
            sideOffset={8}
            collisionPadding={8}
            className="ui:z-50 ui:flex ui:max-h-(--radix-popover-content-available-height) ui:w-90 ui:flex-col ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:p-1.5 ui:shadow-md"
          >
            <label className="ui:mb-1 ui:flex ui:h-9 ui:items-center ui:gap-2 ui:rounded-md ui:px-2.5 ui:text-muted-foreground">
              <SearchIcon aria-hidden className="ui:size-4" />
              <input
                type="search"
                aria-label="Find an organisation"
                placeholder="Find an organisation"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="ui:flex-1 ui:bg-transparent ui:text-body-small ui:text-foreground ui:outline-none ui:placeholder:text-muted-foreground"
              />
            </label>
            {(state.status === "loading" || state.status === "idle") && (
              <Skeleton
                label="Loading organisations"
                className="ui:px-2.5 ui:py-2"
              >
                {[0, 1].map((row) => (
                  <span
                    key={row}
                    className="ui:flex ui:items-center ui:gap-2.5"
                  >
                    <SkeletonAvatar className="ui:rounded-lg" />
                    <SkeletonText lines={2} className="ui:flex-1" />
                  </span>
                ))}
              </Skeleton>
            )}
            {state.status === "error" && (
              <InlineAlert
                title="Could not load your organisations."
                onRetry={load}
              />
            )}
            {state.status === "ready" && (
              <>
                {shown.length === 0 ? (
                  query.trim() !== "" && (
                    <p className="ui:px-3 ui:py-4 ui:text-body-small ui:text-muted-foreground">
                      No organisations match
                    </p>
                  )
                ) : (
                  <p className="ui:px-1.5 ui:pt-1 ui:pb-2 ui:text-overline ui:uppercase ui:text-muted-foreground">
                    You belong to {count} organisation{count === 1 ? "" : "s"}
                  </p>
                )}
                <ul className="ui:flex ui:min-h-0 ui:flex-col ui:overflow-y-auto">
                  {shown.map((org) => {
                    const isCurrent = org.id === current.id;
                    return (
                      <li
                        key={org.id}
                        {...(isCurrent ? { "aria-current": "true" } : {})}
                        className={`ui:flex ui:h-14 ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2.5 ${isCurrent ? "ui:bg-muted" : ""}`}
                      >
                        <OrgAvatar name={org.display_name} size="md" />
                        <OrgLine org={org} />
                        {isCurrent ? (
                          <span className="ui:rounded-sm ui:bg-primary-muted ui:px-2 ui:py-0.75 ui:text-caption ui:font-medium ui:text-primary">
                            Current
                          </span>
                        ) : (
                          <button
                            type="button"
                            aria-label={`Switch to ${org.display_name}`}
                            className={`${BUTTON} ui:px-2.5`}
                            onClick={() =>
                              setPending({
                                from: {
                                  ...organizations.find(
                                    (o) => o.id === current.id,
                                  ),
                                  id: current.id,
                                  name: current.name,
                                  display_name: current.displayName,
                                },
                                to: org,
                              })
                            }
                          >
                            <ArrowRightLeft aria-hidden className="ui:size-4" />
                            Switch
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {nothingToSwitchTo && (
                  <p className="ui:px-3 ui:pt-1.5 ui:text-caption ui:text-muted-foreground">
                    Nothing to switch to.
                  </p>
                )}
              </>
            )}
          </RadixPopover.Content>
        </RadixPopover.Portal>
      </RadixPopover.Root>
      {pending && (
        <ConfirmSwitch
          from={pending.from}
          to={pending.to}
          viaLogin={current.switchViaLogin === true}
          onClose={() => setPending(undefined)}
          onAccessRemoved={load}
          returnFocus={() => pill.current?.focus()}
        />
      )}
    </>
  );
}
