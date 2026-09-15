import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
} from "lucide-react";
import * as React from "react";
import { DayPicker } from "react-day-picker";

import { cn } from "@/lib/utils";

/**
 * shadcn-style Calendar over react-day-picker v10.
 *
 * v10 ships NO stylesheet — it emits semantic class slots and expects the app
 * to supply the look. That suits us: every colour below is a Midnight Bloom
 * token, so the calendar tracks light/dark with everything else rather than
 * carrying a second palette the way antd's did.
 *
 * Slot names come from the library's `UI` / `DayFlag` / `SelectionState`
 * enums, so they are checked against the installed version rather than being
 * guessed strings.
 */
export type CalendarProps = React.ComponentProps<typeof DayPicker>;

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: CalendarProps) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-3", className)}
      classNames={{
        // Row, not `sm:flex-row`. Tailwind breakpoints measure the VIEWPORT,
        // and this renders inside a popover whose own width is what matters —
        // on a wide screen the months still stacked, making the popover 250px
        // wide and ~700px tall, which ran off the bottom of the window.
        /*
         * `relative` here, NOT on `month`. react-day-picker renders ONE nav for
         * the whole calendar, so anchoring the absolute prev/next buttons to
         * `.month` pinned both of them to the FIRST month — with
         * `numberOfMonths={2}` the "next" arrow landed mid-popover instead of
         * at the right edge. antd puts one pair at each outer edge.
         */
        months: "relative flex flex-row gap-4",
        month: "flex flex-col gap-4",
        /*
         * `px-8` clears the nav arrows. They are absolutely positioned at the
         * calendar's outer edges (below) while the caption centres itself in
         * the month, so a wide caption slid straight under them.
         */
        month_caption: "flex h-7 items-center justify-center px-8",
        caption_label: "inline-flex items-center gap-1 text-sm font-medium",
        /*
         * `captionLayout="dropdown"` swaps the caption for month/year selects
         * (antd's clickable month and year buttons). react-day-picker ships no
         * styles, so without these the selects render as raw browser controls.
         *
         * The shape it renders is a <select> AND a visible `caption_label`
         * span holding the same text — the select is meant to lie invisibly
         * over the span and take the clicks. Styling the SELECT as the visible
         * control instead drew both, so every caption read "August August ›"
         * and "2026 2026 ›" across two boxes and ran under the arrows.
         *
         * So: the root is the control users see, the select is a transparent
         * overlay on top of it, and the span supplies the text.
         */
        dropdowns: "flex items-center gap-1 text-sm font-medium",
        dropdown_root: cn(
          "relative inline-flex items-center rounded-md border border-input",
          "bg-transparent px-2 py-0.5",
          "hover:bg-accent",
          // The focus ring belongs to the border the user sees, but focus
          // lands on the invisible <select> inside it.
          "has-[:focus-visible]:ring-1 has-[:focus-visible]:ring-ring",
        ),
        dropdown: cn(
          "absolute inset-0 size-full cursor-pointer opacity-0",
          // Safari renders a zero-opacity select as unclickable unless it is
          // still laid out as a control.
          "appearance-none bg-transparent",
        ),
        nav: "flex items-center gap-1",
        button_previous: cn(
          "absolute left-0 top-0 z-10 inline-flex size-7 items-center justify-center",
          "rounded-md border border-input bg-transparent",
          "opacity-50 hover:opacity-100 hover:bg-accent hover:text-accent-foreground",
          "disabled:pointer-events-none disabled:opacity-25",
        ),
        button_next: cn(
          "absolute right-0 top-0 z-10 inline-flex size-7 items-center justify-center",
          "rounded-md border border-input bg-transparent",
          "opacity-50 hover:opacity-100 hover:bg-accent hover:text-accent-foreground",
          "disabled:pointer-events-none disabled:opacity-25",
        ),
        month_grid: "w-full border-collapse space-y-1",
        weekdays: "flex",
        weekday:
          "w-8 rounded-md text-[0.8rem] font-normal text-muted-foreground",
        week: "mt-2 flex w-full",
        day: cn(
          "relative p-0 text-center text-sm",
          // Range middle needs a continuous band, so the rounding is applied
          // to the ends only (below) rather than to every cell.
          "focus-within:relative focus-within:z-20",
          "[&:has([aria-selected])]:bg-accent",
          "[&:has([aria-selected].day-range-end)]:rounded-r-md",
          "[&:has([aria-selected].day-range-start)]:rounded-l-md",
        ),
        day_button: cn(
          "inline-flex size-8 cursor-pointer items-center justify-center rounded-md p-0",
          "font-normal aria-selected:opacity-100 disabled:cursor-not-allowed",
          "hover:bg-accent hover:text-accent-foreground",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        ),
        range_start:
          "day-range-start rounded-l-md bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
        range_end:
          "day-range-end rounded-r-md bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
        range_middle:
          "rounded-none bg-accent text-accent-foreground hover:bg-accent hover:text-accent-foreground",
        selected:
          "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
        today: "bg-accent text-accent-foreground",
        outside: "text-muted-foreground opacity-50",
        disabled: "text-muted-foreground opacity-50",
        hidden: "invisible",
        ...classNames,
      }}
      components={{
        /*
         * react-day-picker asks for four orientations, not two: the nav arrows
         * are left/right, but the dropdown captions ask for "down". Falling
         * through to ChevronRight gave the month and year controls a
         * rightward chevron, so neither read as a dropdown.
         */
        Chevron: ({ orientation, ...rest }) => {
          const Icon = {
            left: ChevronLeft,
            right: ChevronRight,
            up: ChevronUp,
            down: ChevronDown,
          }[orientation ?? "right"];
          return <Icon className="size-4" {...rest} />;
        },
      }}
      {...props}
    />
  );
}

export { Calendar };
