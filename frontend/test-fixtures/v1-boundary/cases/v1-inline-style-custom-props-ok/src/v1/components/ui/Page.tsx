import { cn } from "@v1/lib/cn";

type Props = { width: number; height: number; x: number; y: number };

// Runtime geometry goes through custom properties; the classes read them.
export function Page({ width, height, x, y }: Props) {
  return (
    <div
      className={cn("ui:relative ui:w-full ui:aspect-(--page-aspect)")}
      style={{
        "--page-aspect": width / height,
        "--page-h": `${height}px`,
      }}
    >
      <mark
        className="ui:absolute ui:left-(--hl-x) ui:top-(--hl-y) ui:bg-primary"
        style={{ "--hl-x": `${x}%`, "--hl-y": `${y}%` }}
      />
    </div>
  );
}
