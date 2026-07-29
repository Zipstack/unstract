import { ChevronLeft, ChevronRight } from "lucide-react";
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
        months: "flex flex-row gap-4",
        // `relative` anchors the absolutely-positioned prev/next buttons to
        // each month rather than to the page.
        month: "relative flex flex-col gap-4",
        month_caption: "flex items-center justify-center pt-1",
        caption_label: "text-sm font-medium",
        nav: "flex items-center gap-1",
        button_previous: cn(
          "absolute left-1 top-3 z-10 inline-flex size-7 items-center justify-center",
          "rounded-md border border-input bg-transparent",
          "opacity-50 hover:opacity-100 hover:bg-accent hover:text-accent-foreground",
          "disabled:pointer-events-none disabled:opacity-25",
        ),
        button_next: cn(
          "absolute right-1 top-3 z-10 inline-flex size-7 items-center justify-center",
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
        Chevron: ({ orientation, ...rest }) =>
          orientation === "left" ? (
            <ChevronLeft className="size-4" {...rest} />
          ) : (
            <ChevronRight className="size-4" {...rest} />
          ),
      }}
      {...props}
    />
  );
}

export { Calendar };
