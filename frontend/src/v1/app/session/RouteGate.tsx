/*
 * Loads the session once per page load and guards every v1 page with it
 * (UN-4314). v1 shares v0's cookies, so a user signed in on v0 is signed in
 * here too. Sign-in, organisation selection and the error page are still v0's.
 */
import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { RouteAccess } from "@v1/app/registry/types";
import { V1ErrorBoundary } from "@v1/app/V1ErrorBoundary";
import { NoPermission } from "@v1/components/patterns/NoPermission";
import { QueryView } from "@v1/components/patterns/QueryView";
import { InlineAlert, SkeletonText } from "@v1/components/ui/feedback";
import { identifyUser } from "@v1/lib/analytics";
import { sessionEndedPath } from "@v1/lib/organizations";
import { type GateSlotId, Slot } from "@v1/lib/plugins";
import { type Session, SessionProvider } from "@v1/lib/session";
import { setOrganizationId } from "@v1/services/context";
import {
  loadSession,
  type SessionLoad,
  sessionKeys,
} from "@v1/services/session";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import { type JSX, type ReactNode, Suspense } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { type GuardDecision, guardRoute } from "./guard";

/** v0's sign-in page; for a signed-in user it opens their home instead. */
export const SIGN_IN_PATH = "/landing";
/** v0's organisation picker, for a user with several and none current; it reads them from the navigation state. */
export const CHOOSE_ORGANIZATION_PATH = "/setOrg";

const LOADING = (
  <div className="ui:p-6">
    <SkeletonText />
  </div>
);

// A gate whose plugin fails to load stays closed rather than skip its check.
const GATE_FAILED = (
  <div className="ui:p-6">
    <InlineAlert
      title="This page could not be loaded."
      onRetry={() => window.location.reload()}
      retryLabel="Reload"
    />
  </div>
);

// Before the page renders, so its first org-scoped query has the organisation.
function applySession(session: Session): void {
  setOrganizationId(session.organization.id);
  useOldVersionStore.getState().setUser(session.user.id);
  identifyUser(session);
}

async function loadAndApply({
  signal,
}: Readonly<{ signal: AbortSignal }>): Promise<SessionLoad> {
  const load = await loadSession({ signal });
  if (load.kind === "signed-in") {
    applySession(load.session);
  }
  return load;
}

/** Once per page load: signing in, out or to another organisation reloads the page. */
export function useSessionLoad(): UseQueryResult<SessionLoad> {
  return useQuery({
    queryKey: sessionKeys.current(),
    queryFn: loadAndApply,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  });
}

/** The page's own error boundary and loading state, inside any gate, so a page error is never a plugin's. */
function PageFrame({ children }: Readonly<{ children: ReactNode }>) {
  const { pathname } = useLocation();
  return (
    <V1ErrorBoundary resetKey={pathname}>
      <Suspense fallback={LOADING}>{children}</Suspense>
    </V1ErrorBoundary>
  );
}

/** A cloud gate: waits while its plugin loads, and stays closed if it fails. */
function Gate({
  id,
  page,
  fallback,
}: Readonly<{ id: GateSlotId; page: ReactNode; fallback: ReactNode }>) {
  return (
    <Slot
      id={id}
      props={{ children: page }}
      fallback={fallback}
      loading={LOADING}
      failed={GATE_FAILED}
    />
  );
}

/** A signed-in page: cloud's entitlement gate, and the platform-admin gate where asked. */
function SignedIn({
  session,
  platformAdmin,
  children,
}: Readonly<{
  session: Session;
  platformAdmin: boolean;
  children: ReactNode;
}>) {
  const page = <PageFrame>{children}</PageFrame>;
  const allowed = platformAdmin ? (
    <Gate id="route.platform-admin" page={page} fallback={<NoPermission />} />
  ) : (
    page
  );
  return (
    <SessionProvider session={session}>
      <Gate id="route.entitlement" page={allowed} fallback={allowed} />
    </SessionProvider>
  );
}

/** A page the guard allows: as a guest, or signed in behind the cloud gates. */
function Allowed({
  load,
  platformAdmin,
  children,
}: Readonly<{
  load: SessionLoad;
  platformAdmin: boolean;
  children: ReactNode;
}>) {
  if (load.kind !== "signed-in") {
    return (
      <SessionProvider session={null}>
        <PageFrame>{children}</PageFrame>
      </SessionProvider>
    );
  }
  return (
    <SignedIn session={load.session} platformAdmin={platformAdmin}>
      {children}
    </SignedIn>
  );
}

type Outcome = Readonly<{
  decision: GuardDecision;
  load: SessionLoad;
  children: ReactNode;
}>;

function Decided({ decision, load, children }: Outcome): ReactNode {
  const location = useLocation();
  switch (decision) {
    case "sign-in":
      return <Navigate to={SIGN_IN_PATH} state={{ from: location }} replace />;
    // v0's sign-in page sends a signed-in user to their current organisation's home.
    case "enter-app":
    case "other-organization":
      return <Navigate to={SIGN_IN_PATH} replace />;
    case "no-permission":
      return <NoPermission />;
  }
  return (
    <Allowed load={load} platformAdmin={decision === "platform-admin"}>
      {children}
    </Allowed>
  );
}

function Guarded({
  access,
  load,
  children,
}: Readonly<{ access: RouteAccess; load: SessionLoad; children: ReactNode }>) {
  const urlOrganization = useParams().orgName;
  if (load.kind === "ended") {
    return <Navigate to={sessionEndedPath(load.body)} replace />;
  }
  if (load.kind === "choose-organization") {
    return (
      <Navigate
        to={CHOOSE_ORGANIZATION_PATH}
        state={load.organizations}
        replace
      />
    );
  }
  const session = load.kind === "signed-in" ? load.session : null;
  const decision = guardRoute({ access, session, urlOrganization });
  return (
    <Decided decision={decision} load={load}>
      {children}
    </Decided>
  );
}

export type RouteGateProps = Readonly<{
  access: RouteAccess;
  children: ReactNode;
}>;

/** Renders `children` (a page) once the session allows it, else redirects or explains. */
export function RouteGate({ access, children }: RouteGateProps): JSX.Element {
  const load = useSessionLoad();
  return (
    <QueryView query={load} loading={LOADING}>
      {(found) => (
        <Guarded access={access} load={found}>
          {children}
        </Guarded>
      )}
    </QueryView>
  );
}
