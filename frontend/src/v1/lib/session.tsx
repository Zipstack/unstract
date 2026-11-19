/*
 * The signed-in session. `V1App` loads it once per
 * page load and provides it to every page that is not guest-only; read it
 * with `useSession()`.
 */
import { createContext, type ReactNode, useContext } from "react";

export type SessionUser = Readonly<{
  /** The user's numeric id as a string; v0's session id, so per-user keys match. */
  id: string;
  email: string;
  /** For display: the profile's display name, else its name, else the email. */
  name: string;
  /** The organisation role as stored: `admin`/`user` in OSS, `unstract_*` in cloud. */
  role: string;
  /** Organisation admin. */
  isAdmin: boolean;
  /** Unstract staff. */
  isStaff: boolean;
}>;

export type SessionOrganization = Readonly<{
  id: string;
  /** The URL name: paths are /<name>/... */
  name: string;
  displayName: string;
  /** The session's `org_switch_via_login`: switch by signing in again. */
  switchViaLogin: boolean;
}>;

export type Session = Readonly<{
  user: SessionUser;
  organization: SessionOrganization;
}>;

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({
  session,
  children,
}: Readonly<{ session: Session | null; children: ReactNode }>): ReactNode {
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  );
}

/** The signed-in session; throws on a guest-only page, which has none. */
export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error(
      "useSession() needs a signed-in page; guest pages have no session.",
    );
  }
  return session;
}
