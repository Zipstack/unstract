import { cn } from "@v1/lib/cn";
import { cva } from "class-variance-authority";

export const box = cva("ui:rounded-md ui:p-2", {
  variants: {
    variant: { outline: "ui:border", solid: "ui:bg-primary" },
    size: { "sm": "ui:text-caption", lg: "ui:text-body" },
  },
  compoundVariants: [{ variant: "outline", size: "sm", class: "ui:border-2" }],
  defaultVariants: { variant: "outline", size: "sm" },
});

export function Box({ open }: { open: boolean }) {
  return (
    <div
      className={cn(
        "ui:bg-background ui:p-5 ui:rounded-md ui:text-body ui:shadow-sm ui:focus-ring ui:dark:bg-card ui:border-[currentcolor] ui:[color:transparent]",
        "ui:hover:bg-primary ui:md:flex ui:grid-cols-[repeat(2,1fr)] ui:grid-cols-[1fr_auto]",
        { "ui:gap-2": open },
      )}
    >
      <span className={open ? "ui:block" : "ui:hidden"} title="Red Sea" />
      <span className="demo" />
    </div>
  );
}
