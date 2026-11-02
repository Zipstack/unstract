import { cn } from "@v1/lib/cn";

export function Box({ open }: { open: boolean }) {
  return (
    <div
      className={cn(
        "ui:bg-background ui:p-5 ui:rounded-md ui:text-body ui:shadow-sm ui:focus-ring ui:dark:bg-card ui:border-[currentcolor] ui:[color:transparent]",
        "ui:hover:bg-primary ui:md:flex ui:grid-cols-[repeat(2,1fr)]",
        { "ui:gap-2": open },
      )}
    >
      <span className={open ? "ui:block" : "ui:hidden"} title="Red Sea" />
      <span className="demo" />
    </div>
  );
}
