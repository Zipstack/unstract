import { cn } from "@v1/lib/cn";
import type { JSX } from "react";
import type { DocumentState } from "./documentFacts";

/*
 * ponytail: the core status badge does not exist yet; when it lands, this
 * maps a DocumentState to its tone and nothing else changes.
 */

const LABEL: Record<DocumentState, string> = {
  parsed: "Parsed",
  pending: "Pending",
  processing: "Processing",
  failed: "Failed",
};

const TONE: Record<DocumentState, string> = {
  parsed: "ui:bg-success/15 ui:text-success",
  pending: "ui:bg-warning/15 ui:text-warning",
  processing: "ui:bg-primary-muted ui:text-primary",
  failed: "ui:bg-destructive/15 ui:text-destructive",
};

/** A document's state as a pill: Parsed, Pending, Processing or Failed. */
export function StatusBadge({
  state,
}: Readonly<{ state: DocumentState }>): JSX.Element {
  return (
    <span
      data-state={state}
      className={cn(
        "ui:inline-flex ui:h-5 ui:items-center ui:rounded-md ui:px-2 ui:text-caption ui:font-medium",
        TONE[state],
      )}
    >
      {LABEL[state]}
    </span>
  );
}
