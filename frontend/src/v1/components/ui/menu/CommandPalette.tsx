import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Dialog as RadixDialog } from "radix-ui";
import { type JSX, type ReactNode, useEffect, useRef } from "react";
import { Command, type CommandItem, type CommandProps } from "./Command";

/*
 * The command palette shell: a dialog near the top of the screen holding a
 * Command, with key hints in the footer. P2-T10 (global search) builds on
 * it, passing server results with `filter={false}`. Escape or a click outside
 * closes it and returns focus to where it was.
 */

export type CommandPaletteProps = Omit<CommandProps, "autoFocus" | "label"> &
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
        <kbd
          key={key}
          className="ui:rounded-sm ui:border ui:border-border ui:bg-muted ui:px-1 ui:font-sans ui:text-caption ui:text-muted-foreground"
        >
          {key}
        </kbd>
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
            className="ui:pointer-events-auto ui:flex ui:max-h-full ui:w-full ui:max-w-xl ui:flex-col ui:overflow-hidden ui:rounded-xl ui:border ui:border-border ui:bg-popover ui:text-popover-foreground ui:shadow-xl ui:outline-none"
          >
            <RadixDialog.Title className="ui:sr-only">
              {title}
            </RadixDialog.Title>
            <Command
              {...command}
              label={label}
              onSelect={select}
              footer={footer ?? <CommandPaletteHints />}
              className="ui:min-h-0 ui:flex-1"
              listClassName={cn("ui:max-h-96", command.listClassName)}
            />
          </RadixDialog.Content>
        </div>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/**
 * Calls `onOpen` on Ctrl+K or ⌘K (either modifier, on any platform)
 * anywhere on the page. A key press another control already handled (for
 * example a Ctrl+K chord in the code editor) is left alone. Mount it once,
 * in the shell, beside the palette.
 */
export function useCommandPaletteShortcut(onOpen: () => void, key = "k"): void {
  const latest = useRef(onOpen);
  latest.current = onOpen;
  useEffect(() => {
    const target = key.toLowerCase();
    const onKeyDown = (event: KeyboardEvent) => {
      // Autofill fires keydown with no key.
      if (!event.key || event.defaultPrevented || event.isComposing) {
        return;
      }
      if (
        event.key.toLowerCase() === target &&
        (event.metaKey || event.ctrlKey) &&
        !event.altKey &&
        !event.shiftKey
      ) {
        event.preventDefault();
        latest.current();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [key]);
}
