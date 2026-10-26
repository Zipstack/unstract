// TEST BRANCH ONLY (UN-4257-fev1-lane-b-test): a page to see Lane B's v1
// shell pieces against a real backend before the v1 shell (P2-T01) exists.
// Never merged; delete when the shell renders these components.
import { AccountMenu } from "@v1/shell/AccountMenu";
import { OrganizationSwitcher } from "@v1/shell/OrganizationSwitcher";
import { useEffect } from "react";

export interface V1PreviewProps {
  user: { name: string; email: string };
  organization: { id: string; name: string; displayName: string };
}

// The one design token v0's stylesheet lacks (P0-T04 will own it). Set on the
// document root so the menus, which render in portals outside this page, see it.
const TOKENS = { "--primary-muted": "#f1effd" };

export function V1Preview({ user, organization }: V1PreviewProps) {
  useEffect(() => {
    const root = document.documentElement.style;
    for (const [name, value] of Object.entries(TOKENS)) {
      root.setProperty(name, value);
    }
    return () => {
      for (const name of Object.keys(TOKENS)) {
        root.removeProperty(name);
      }
    };
  }, []);

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <header className="flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--sidebar)] px-3">
        <span className="text-sm font-semibold text-[var(--foreground)]">
          v1 preview · test branch only
        </span>
        <div className="flex items-center gap-1.5">
          <OrganizationSwitcher current={organization} />
          <AccountMenu
            user={user}
            profileHref={`/${organization.name}/profile`}
          />
        </div>
      </header>
    </div>
  );
}
