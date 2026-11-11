import { cva } from "class-variance-authority";

export const box = cva("ui:rounded-md", {
  variants: { variant: { outline: "border", solid: "ui:bg-primary" } },
  defaultVariants: { variant: "outline" },
});
