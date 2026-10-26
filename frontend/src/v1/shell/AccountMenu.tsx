import { initials } from "@v1/lib/organizations";
import { Slot } from "@v1/lib/plugins";
import { signOut } from "@v1/services/session";
import {
  ChevronDown,
  CircleHelp,
  CircleUserRound,
  ExternalLink,
  LogOut,
} from "lucide-react";
import posthog from "posthog-js";
import { DropdownMenu } from "radix-ui";
import type { ReactNode } from "react";

const HELP_URL = "https://docs.unstract.com";

// Frame NEW09 (1638:44719). Colours are the design's token names.
const ITEM =
  "flex h-[34px] cursor-pointer items-center gap-2.5 rounded-lg px-[9px] text-[13px] font-medium leading-5 text-[var(--foreground)] outline-none data-[highlighted]:bg-[var(--muted)]";
const ICON = "size-[18px] shrink-0 text-[var(--muted-foreground)]";

export interface AccountMenuProps {
  user: { name: string; email: string };
  /** The profile page (P3-T10) in the current organisation. */
  profileHref: string;
}

async function leave(): Promise<void> {
  try {
    const url = await signOut();
    posthog.reset();
    window.location.assign(url);
  } catch {
    // The GET logout ends the session too and redirects itself (v0's path).
    window.location.assign("/api/v1/logout");
  }
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
  const mark = initials(user.name || user.email);
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label="Account menu"
        className="flex h-10 items-center gap-2 rounded-[10px] pr-1.5 pl-1 outline-none hover:bg-[var(--muted)] focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
      >
        <span className="flex size-8 items-center justify-center rounded-lg bg-[var(--primary)] text-[13px] font-semibold text-[var(--primary-foreground)]">
          {mark}
        </span>
        <ChevronDown
          aria-hidden
          className="size-[13px] text-[var(--muted-foreground)]"
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 flex w-[280px] flex-col gap-0.5 rounded-[10px] border border-[var(--border)] bg-[var(--sidebar)] p-1.5 shadow-[0_8px_24px_0_#0000001f]"
        >
          <div className="flex items-center gap-2.5 px-[9px] pt-1.5 pb-2">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--primary-muted)] text-[13px] font-semibold text-[var(--primary)]">
              {mark}
            </span>
            <span className="flex min-w-0 flex-col gap-px">
              <span className="truncate text-sm font-semibold leading-5 text-[var(--foreground)]">
                {user.name}
              </span>
              <span className="truncate text-xs leading-4 text-[var(--muted-foreground)]">
                {user.email}
              </span>
            </span>
          </div>
          <DropdownMenu.Separator className="h-px bg-[var(--border)]" />
          <Item href={profileHref}>
            <CircleUserRound aria-hidden className={ICON} />
            Profile & preferences
          </Item>
          <Slot id="account-menu.plan-billing" props={{}} fallback={null} />
          <Item href={HELP_URL}>
            <CircleHelp aria-hidden className={ICON} />
            <span className="flex-1">Help & docs</span>
            <ExternalLink
              aria-hidden
              className="size-4 text-[var(--muted-foreground)]"
            />
          </Item>
          <DropdownMenu.Separator className="h-px bg-[var(--border)]" />
          <DropdownMenu.Item className={ITEM} onSelect={() => void leave()}>
            <LogOut aria-hidden className={ICON} />
            Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
