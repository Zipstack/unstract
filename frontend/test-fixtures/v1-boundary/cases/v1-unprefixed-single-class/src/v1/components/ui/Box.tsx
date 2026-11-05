import { cn } from "@v1/lib/cn";

export function Box({ open }: { open: boolean }) {
  return (
    <div className="flex">
      <span className={open ? "hidden" : "ui:hidden"} />
      <span className={cn("ui:p-2", open && "block")} />
    </div>
  );
}
