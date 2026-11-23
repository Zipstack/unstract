import { Kbd } from "@v1/components/ui/button";
import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Dialog as RadixDialog } from "radix-ui";
import { type JSX, type ReactNode, useEffect, useRef } from "react";
import {
  Command,
  type CommandBaseProps,
  type CommandItem,
  type CommandQuery,
  type CommandRows,
} from "./Command";

/*
 * The command palette shell: a dialog near the top of the screen holding a
 * Command, with key hints in the footer. P2-T10 (global search) builds on
 * it, passing server results with `filter={false}`. Escape or a click outside
 * closes it and returns focus to where it was.
 */

export type CommandPaletteProps = Omit<
  CommandBaseProps,
  "autoFocus" | "label"
> &
  CommandRows &
  CommandQuery &
  Readonly<{
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** The dialog's name, read by screen readers. Default "Command palette". */
    title?: string;
    /** The search box's name. Default "Search commands". */
    label?: string;
    /** Default true: choosing a row closes the palette. */
    closeOnSelect?: boolean;
  }>;

/** The footer's key hints. Pass `footer` to replace them. */
export function CommandPaletteHints(): JSX.Element {
  return (
    <>
      <Hint keys={["↑", "↓"]}>to move</Hint>
      <Hint keys={["↵"]}>to select</Hint>
      <Hint keys={["esc"]}>to close</Hint>
    </>
  );
}

function Hint({
  keys,
  children,
}: Readonly<{ keys: readonly string[]; children: ReactNode }>): JSX.Element {
  return (
    <div className="ui:flex ui:items-center ui:gap-1">
      {keys.map((key) => (
        <Kbd key={key}>{key}</Kbd>
      ))}
      <div>{children}</div>
    </div>
  );
}

export function CommandPalette({
  open,
  onOpenChange,
  title = "Command palette",
  label = "Search commands",
  closeOnSelect = true,
  onSelect,
  footer,
  ...command
}: CommandPaletteProps): JSX.Element {
  // The palette opens from a shortcut, with no Radix trigger to return to, so
  // it returns focus itself to whatever had it when the palette opened.
  const returnFocus = useRef<HTMLElement | null>(null);
  const select = (item: CommandItem) => {
    onSelect?.(item);
    if (closeOnSelect) {
      onOpenChange(false);
    }
  };
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal container={getPortalContainer()}>
        <RadixDialog.Overlay
          data-slot="command-palette-overlay"
          className="ui:fixed ui:inset-0 ui:z-50 ui:bg-scrim"
        />
        {/* The frame keeps the palette 16px inside the viewport's bottom, so a
            short or zoomed window scrolls the list instead of cutting it off.
            It lets clicks through to the overlay, which closes the palette. */}
        <div className="ui:pointer-events-none ui:fixed ui:inset-x-4 ui:top-24 ui:bottom-4 ui:z-50 ui:flex ui:items-start ui:justify-center">
          <RadixDialog.Content
            data-slot="command-palette"
            aria-describedby={undefined}
            onOpenAutoFocus={() => {
              // Runs before Radix moves focus in, so this is still the opener.
              returnFocus.current =
                document.activeElement instanceof HTMLElement
                  ? document.activeElement
                  : null;
            }}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              returnFocus.current?.focus();
              returnFocus.current = null;
            }}
            className="ui:pointer-events-auto ui:flex ui:max-h-full ui:w-full ui:max-w-xl ui:flex-col ui:overflow-hidden ui:rounded-xl ui:border ui:border-border ui:bg-popover ui:text-popover-foreground ui:shadow-xl ui:outline-none"
          >
            <RadixDialog.Title className="ui:sr-only">
              {title}
            </RadixDialog.Title>
            <Command
              {...command}
              label={label}
              // Radix focuses the search box (the first tabbable) on open;
              // its own autofocus would skip onOpenAutoFocus, which records
              // where to return.
              autoFocus={false}
              onSelect={select}
              footer={footer === undefined ? <CommandPaletteHints /> : footer}
              className={cn("ui:min-h-0 ui:flex-1", command.className)}
              listClassName={cn("ui:max-h-96", command.listClassName)}
            />
          </RadixDialog.Content>
        </div>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/** Apple platforms use ⌘ for shortcuts; Ctrl+K there edits text. */
function isApplePlatform(): boolean {
  return /Mac|iPhone|iPad|iPod/.test(globalThis.navigator?.platform ?? "");
}

/**
 * Calls `onOpen` on ⌘K on Apple platforms and Ctrl+K elsewhere, anywhere on
 * the page. On a Mac, Ctrl+K is left to text fields ("delete to end of
 * line"). The key is matched by its position (`event.code`), so it works on
 * any keyboard layout, with the typed letter as a fallback. A key press
 * another control already handled (for example a chord in the code editor)
 * is left alone. Mount it once, in the shell, beside the palette.
 */
export function useCommandPaletteShortcut(onOpen: () => void, key = "k"): void {
  const latest = useRef(onOpen);
  latest.current = onOpen;
  useEffect(() => {
    const target = key.toLowerCase();
    const code = `Key${target.toUpperCase()}`;
    const apple = isApplePlatform();
    const onKeyDown = (event: KeyboardEvent) => {
      // Autofill fires keydown with no key.
      if (!event.key || event.defaultPrevented || event.isComposing) {
        return;
      }
      const modifier = apple
        ? event.metaKey && !event.ctrlKey
        : event.ctrlKey && !event.metaKey;
      const matches = event.code === code || event.key.toLowerCase() === target;
      if (matches && modifier && !event.altKey && !event.shiftKey) {
        event.preventDefault();
        latest.current();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [key]);
}
