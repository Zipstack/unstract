import { initial, initials } from "@v1/lib/organizations";
import { Slot } from "@v1/lib/plugins";
import { getPortalContainer } from "@v1/lib/portal";
import { signOutAndLeave } from "@v1/services/session";
import {
  ChevronDown,
  CircleHelp,
  CircleUserRound,
  ExternalLink,
  LogOut,
} from "lucide-react";
import { DropdownMenu } from "radix-ui";
import type { ReactNode } from "react";

const HELP_URL = "https://docs.unstract.com";

// Frame NEW09 (1638:44719). Colours are the design's token names.
const ITEM =
  "ui:flex ui:h-8.5 ui:cursor-pointer ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2.25 ui:text-body-small ui:font-medium ui:text-foreground ui:outline-none ui:data-highlighted:bg-muted";
const ICON = "ui:size-4.5 ui:shrink-0 ui:text-muted-foreground";

export interface AccountMenuProps {
  user: { name: string; email: string };
  /** The profile page (P3-T10) in the current organisation. */
  profileHref: string;
}

function Item({ children, href }: { children: ReactNode; href: string }) {
  const external = href.startsWith("http");
  return (
    <DropdownMenu.Item asChild className={ITEM}>
      <a
        href={href}
        {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
      >
        {children}
      </a>
    </DropdownMenu.Item>
  );
}

/**
 * The avatar menu: identity, Profile & preferences, Plan & billing (a cloud
 * plugin fills the slot, TRIAL badge included), Help & docs, Sign out. No
 * "Switch to old version" item: that control lives only on Human Review (D14).
 */
export function AccountMenu({ user, profileHref }: AccountMenuProps) {
  const label = user.name || user.email;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label="Account menu"
        className="ui:flex ui:h-10 ui:items-center ui:gap-2 ui:rounded-lg ui:pr-1.5 ui:pl-1 ui:outline-none ui:hover:bg-muted ui:focus-visible:focus-ring"
      >
        <span className="ui:flex ui:size-8 ui:items-center ui:justify-center ui:rounded-md ui:bg-primary ui:text-body-small ui:font-semibold ui:text-primary-foreground">
          {initial(label)}
        </span>
        <ChevronDown
          aria-hidden
          className="ui:size-3.25 ui:text-muted-foreground"
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal container={getPortalContainer()}>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="ui:z-50 ui:flex ui:w-70 ui:flex-col ui:gap-0.5 ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:p-1.5 ui:shadow-lg"
        >
          <div className="ui:flex ui:items-center ui:gap-2.5 ui:px-2.25 ui:pt-1.5 ui:pb-2">
            <span className="ui:flex ui:size-9 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-full ui:bg-primary-muted ui:text-body-small ui:font-semibold ui:text-primary">
              {initials(label)}
            </span>
            <span className="ui:flex ui:min-w-0 ui:flex-col ui:gap-px">
              <span className="ui:truncate ui:text-body ui:font-semibold ui:text-foreground">
                {user.name || user.email}
              </span>
              {user.name && (
                <span className="ui:truncate ui:text-caption ui:text-muted-foreground">
                  {user.email}
                </span>
              )}
            </span>
          </div>
          <DropdownMenu.Separator className="ui:h-px ui:bg-border" />
          <Item href={profileHref}>
            <CircleUserRound aria-hidden className={ICON} />
            Profile & preferences
          </Item>
          <Slot id="account-menu.plan-billing" props={{}} fallback={null} />
          <Item href={HELP_URL}>
            <CircleHelp aria-hidden className={ICON} />
            <span className="ui:flex-1">
              Help & docs{" "}
              <span className="ui:sr-only">(opens in a new tab)</span>
            </span>
            <ExternalLink
              aria-hidden
              className="ui:size-4 ui:text-muted-foreground"
            />
          </Item>
          <DropdownMenu.Separator className="ui:h-px ui:bg-border" />
          <DropdownMenu.Item
            className={ITEM}
            onSelect={() => void signOutAndLeave()}
          >
            <LogOut aria-hidden className={ICON} />
            Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
