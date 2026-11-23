import { Button } from "@v1/components/ui/button";
import type { JSX, ReactNode } from "react";
import { selectedText } from "./announce";

export type BulkBarProps = Readonly<{
  /** The table's label: the bar is named "Bulk actions for <label>". */
  label: string;
  count: number;
  onClear: () => void;
  children?: ReactNode;
}>;

/**
 * Frame L10 (1252:4201): a 44-tall primary-muted bar between the toolbar and
 * the table, with the count, "Clear selection" and the page's actions at the
 * end. It sits before the table in the tab order: Shift+Tab from a row
 * goes back through the header's controls to it. The count is not live
 * here: the table's own status region announces selection changes once.
 */
export function BulkBar({
  label,
  count,
  onClear,
  children,
}: BulkBarProps): JSX.Element {
  return (
    <section
      aria-label={`Bulk actions for ${label}`}
      data-slot="data-table-bulk-bar"
      className="ui:box-border ui:flex ui:min-h-11 ui:flex-wrap ui:items-center ui:gap-x-4 ui:gap-y-2 ui:rounded-lg ui:border ui:border-solid ui:border-primary/20 ui:bg-primary-muted ui:px-5 ui:py-1.5"
    >
      <p className="ui:m-0 ui:text-body-small ui:font-medium ui:text-foreground">
        {selectedText(count)}
      </p>
      <Button variant="link" size="sm" onClick={onClear} className="ui:px-0">
        Clear selection
      </Button>
      <div className="ui:ml-auto ui:flex ui:flex-wrap ui:items-center ui:gap-2">
        {children}
      </div>
    </section>
  );
}
