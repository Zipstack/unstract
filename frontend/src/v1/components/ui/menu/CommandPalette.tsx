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
        <RadixDialog.Content
          data-slot="command-palette"
          aria-describedby={undefined}
          className="ui:fixed ui:inset-x-4 ui:top-24 ui:z-50 ui:mx-auto ui:flex ui:max-h-120 ui:max-w-xl ui:flex-col ui:overflow-hidden ui:rounded-xl ui:border ui:border-border ui:bg-popover ui:text-popover-foreground ui:shadow-xl ui:outline-none"
        >
          <RadixDialog.Title className="ui:sr-only">{title}</RadixDialog.Title>
          <Command
            {...command}
            label={label}
            onSelect={select}
            footer={footer ?? <CommandPaletteHints />}
            className="ui:min-h-0 ui:flex-1"
          />
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/**
 * Calls `onOpen` on Ctrl+K, or ⌘K on a Mac, anywhere on the page. Mount it
 * once, in the shell, beside the palette.
 */
export function useCommandPaletteShortcut(onOpen: () => void, key = "k"): void {
  const latest = useRef(onOpen);
  latest.current = onOpen;
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key.toLowerCase() === key &&
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
