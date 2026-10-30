import { cn } from "@v1/lib/cn";

export function Box() {
  return (
    <div
      className={cn(
        "ui:bg-background ui:p-5 ui:rounded-md ui:text-body ui:shadow-sm ui:focus-ring ui:dark:bg-card ui:border-[currentcolor] ui:[color:transparent]",
      )}
    />
  );
}
