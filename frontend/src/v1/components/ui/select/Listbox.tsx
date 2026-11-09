import { useVirtualizer } from "@tanstack/react-virtual";
import { Spinner } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import { type JSX, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { OptionRow } from "./OptionRow";
import type { Listbox as ListboxState } from "./useListbox";

/** Above this many visible options, only the rows in view are rendered. */
export const VIRTUALIZE_ABOVE = 100;

// Row heights (`ui:h-8`, `ui:h-12`) and the gap between rows (`ui:gap-0.5`).
const ROW_HEIGHT = 32;
const ROW_HEIGHT_WITH_DESCRIPTION = 48;
const ROW_GAP = 2;
// What the virtualiser assumes before it can measure (and in tests): the
// list surface's cap, `ui:max-h-80`.
const INITIAL_VIEWPORT = { width: 0, height: 320 };

const STATUS_ROW = "ui:flex ui:h-8 ui:items-center ui:px-2";

export type ListboxProps = Readonly<{
  listbox: ListboxState;
  loading?: boolean;
  emptyText?: string;
  multiselectable?: boolean;
  className?: string;
}>;

/**
 * The option list of a Combobox or MultiSelect, for inside the caller's
 * `Popover.Content` (a flex column with `ui:overflow-hidden`): this is its one
 * scroll element. Past `VIRTUALIZE_ABOVE` options only the rows in view are
 * rendered. The loading and empty rows sit beside the listbox, since a
 * listbox may hold only options.
 */
export function Listbox({
  listbox,
  loading = false,
  emptyText,
  multiselectable,
  className,
}: ListboxProps): JSX.Element {
  const { visible, activeIndex, optionId, setActiveIndex } = listbox;
  const scrollRef = useRef<HTMLDivElement>(null);
  const selected = useMemo(() => new Set(listbox.selected), [listbox.selected]);

  const virtual = visible.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (index) =>
      visible[index]?.description ? ROW_HEIGHT_WITH_DESCRIPTION : ROW_HEIGHT,
    gap: ROW_GAP,
    overscan: 8,
    enabled: virtual,
    initialRect: INITIAL_VIEWPORT,
  });
  // Rows are placed from estimateSize, which the virtualiser caches: a new
  // list must re-measure, or rows keep the old heights.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `visible` is the trigger; estimateSize reads it
  useLayoutEffect(() => {
    virtualizer.measure();
  }, [visible, virtualizer]);

  useEffect(() => {
    if (activeIndex < 0) {
      return;
    }
    if (virtual) {
      virtualizer.scrollToIndex(activeIndex);
    } else {
      scrollRef.current?.ownerDocument
        .getElementById(optionId(activeIndex))
        ?.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, virtual, virtualizer, optionId]);

  const renderRow = (index: number) => {
    const option = visible[index];
    return (
      <OptionRow
        key={option.value}
        id={optionId(index)}
        option={option}
        selected={selected.has(option.value)}
        active={index === activeIndex}
        onSelect={() => listbox.onSelect(option)}
        onActivate={() => setActiveIndex(index)}
      />
    );
  };

  return (
    <div
      ref={scrollRef}
      data-slot="listbox-scroll"
      className={cn("ui:min-h-0 ui:flex-1 ui:overflow-auto", className)}
    >
      {loading ? (
        <output className={cn(STATUS_ROW, "ui:gap-2 ui:text-muted-foreground")}>
          <Spinner size="inline" />
          Loading…
        </output>
      ) : null}
      <div
        role="listbox"
        id={listbox.listId}
        aria-multiselectable={multiselectable || undefined}
        aria-busy={loading || undefined}
        style={{
          "--listbox-height": virtual
            ? `${virtualizer.getTotalSize()}px`
            : undefined,
        }}
        className={
          virtual
            ? "ui:relative ui:h-(--listbox-height)"
            : "ui:flex ui:flex-col ui:gap-0.5"
        }
      >
        {virtual
          ? virtualizer.getVirtualItems().map((item) => (
              <div
                key={item.key}
                role="none"
                style={{ "--row-y": `${item.start}px` }}
                className="ui:absolute ui:top-0 ui:left-0 ui:w-full ui:translate-y-(--row-y)"
              >
                {renderRow(item.index)}
              </div>
            ))
          : visible.map((_, index) => renderRow(index))}
      </div>
      {!loading && visible.length === 0 ? (
        <output
          className={cn(STATUS_ROW, "ui:text-caption ui:text-muted-foreground")}
        >
          {emptyText ?? (listbox.query ? "No matches" : "No options")}
        </output>
      ) : null}
    </div>
  );
}
