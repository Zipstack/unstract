// TEST BRANCH ONLY (UN-4257-fev1-lane-b-test): a page to see Lane B's v1
// shell pieces against a real backend before the v1 shell (P2-T01) exists.
// Never merged; delete when the shell renders these components.
import { ThemeProvider } from "@v1/app/theme/ThemeProvider";
import { PluginProvider, Slot } from "@v1/lib/plugins";
import { PluginSlot } from "@v1/plugins";
import { AccountMenu } from "@v1/shell/AccountMenu";
import { OrganizationSwitcher } from "@v1/shell/OrganizationSwitcher";

export interface V1PreviewProps {
  user: { name: string; email: string };
  organization: { id: string; name: string; displayName: string };
}

export function V1Preview({ user, organization }: V1PreviewProps) {
  return (
    <ThemeProvider className="ui:min-h-screen ui:bg-background">
      <PluginProvider slot={PluginSlot}>
        <header className="ui:flex ui:h-14 ui:items-center ui:justify-between ui:border-b ui:border-border ui:bg-sidebar ui:px-3">
          <div className="ui:flex ui:items-center ui:gap-3">
            <span className="ui:text-sm ui:font-semibold ui:text-sidebar-foreground">
              v1 preview · test branch only
            </span>
            {/* Cloud fills this with the product switcher (P2-T13). */}
            <Slot id="shell.product-switcher" props={{}} fallback={null} />
          </div>
          <div className="ui:flex ui:items-center ui:gap-1.5">
            <OrganizationSwitcher current={organization} />
            <AccountMenu
              user={user}
              profileHref={`/${organization.name}/profile`}
            />
          </div>
        </header>
      </PluginProvider>
    </ThemeProvider>
  );
}
