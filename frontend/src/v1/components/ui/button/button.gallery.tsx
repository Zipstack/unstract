import { ACTION_ICONS } from "@v1/lib/icons";
import type { LucideIcon } from "lucide-react";
import type { ReactElement } from "react";
import { Button, type ButtonProps } from "./Button";
import { ButtonGroup } from "./ButtonGroup";
import { IconButton } from "./IconButton";
import { Kbd } from "./Kbd";
import { Link } from "./Link";

// Every variant, size and state of the buttons and links, for the component gallery.

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

type Variant = NonNullable<ButtonProps["variant"]>;
type State = "default" | "disabled" | "loading";

const VARIANTS: Readonly<Record<Variant, { label: string; icon: LucideIcon }>> =
  {
    primary: { label: "New project", icon: ACTION_ICONS.add },
    secondary: { label: "Duplicate", icon: ACTION_ICONS.copy },
    outline: { label: "Import project", icon: ACTION_ICONS.download },
    ghost: { label: "Refresh", icon: ACTION_ICONS.refresh },
    destructive: { label: "Delete", icon: ACTION_ICONS.delete },
    link: { label: "View logs", icon: ACTION_ICONS.view },
  };
const SIZES = ["lg", "md", "sm", "xs"] as const;
const STATES: readonly State[] = ["default", "disabled", "loading"];

/** One variant in one state, at all four heights (36, 32, 28, 24). */
function SizeRow({ variant, state }: { variant: Variant; state: State }) {
  const { label, icon } = VARIANTS[variant];
  return (
    <div className="ui:flex ui:items-center ui:gap-3">
      {SIZES.map((size) => (
        <Button
          key={size}
          variant={variant}
          size={size}
          leadingIcon={icon}
          disabled={state === "disabled"}
          loading={state === "loading"}
        >
          {label}
        </Button>
      ))}
    </div>
  );
}

const buttonEntries: GalleryEntry[] = Object.keys(VARIANTS).flatMap((key) =>
  STATES.map((state) => ({
    name: `button ${key} ${state}`,
    element: <SizeRow variant={key as Variant} state={state} />,
  })),
);

const ICON_STATES = [
  { state: "default", label: "Edit", icon: ACTION_ICONS.edit },
  {
    state: "selected",
    label: "Filter",
    icon: ACTION_ICONS.filter,
    selected: true,
  },
  {
    state: "disabled",
    label: "Delete",
    icon: ACTION_ICONS.delete,
    disabled: true,
  },
] as const;

/** One icon-button variant at 32 and 28, in each state. */
function IconButtonRow({ variant }: { variant: "ghost" | "outline" }) {
  return (
    <div className="ui:flex ui:items-center ui:gap-3">
      {(["md", "sm"] as const).flatMap((size) =>
        ICON_STATES.map(({ state, label, ...rest }) => (
          <IconButton
            key={`${size}-${state}`}
            variant={variant}
            size={size}
            aria-label={label}
            {...rest}
          />
        )),
      )}
    </div>
  );
}

export const BUTTON_GALLERY: readonly GalleryEntry[] = [
  ...buttonEntries,
  {
    name: "button icon positions",
    element: (
      <div className="ui:flex ui:items-center ui:gap-3">
        <Button variant="outline" leadingIcon={ACTION_ICONS.back}>
          Back
        </Button>
        <Button variant="outline" trailingIcon={ACTION_ICONS.next}>
          Next
        </Button>
        <Button variant="outline">Cancel</Button>
      </div>
    ),
  },
  { name: "icon button ghost", element: <IconButtonRow variant="ghost" /> },
  { name: "icon button outline", element: <IconButtonRow variant="outline" /> },
  {
    name: "link inline",
    element: (
      <p className="ui:m-0 ui:text-body">
        Read the <Link href="/guide">setup guide</Link> before you start.
      </p>
    ),
  },
  {
    name: "link external",
    element: (
      <p className="ui:m-0 ui:text-body">
        See the{" "}
        <Link href="https://docs.unstract.com" external>
          documentation
        </Link>{" "}
        for every option.
      </p>
    ),
  },
  {
    name: "link in small text",
    element: (
      <p className="ui:m-0 ui:text-caption ui:text-muted-foreground">
        Usage resets monthly. <Link href="/billing">Manage plan</Link>
      </p>
    ),
  },
  {
    name: "kbd",
    element: (
      <div className="ui:flex ui:items-center ui:gap-1">
        <Kbd>⌘</Kbd>
        <Kbd>K</Kbd>
      </div>
    ),
  },
  {
    name: "button group",
    element: (
      <ButtonGroup aria-label="Range">
        <Button variant="outline">Day</Button>
        <Button variant="outline">Week</Button>
        <Button variant="outline">Month</Button>
      </ButtonGroup>
    ),
  },
  {
    name: "button group icons",
    element: (
      <ButtonGroup aria-label="View">
        <IconButton
          variant="outline"
          icon={ACTION_ICONS.document}
          aria-label="List view"
          selected
        />
        <IconButton
          variant="outline"
          icon={ACTION_ICONS.view}
          aria-label="Preview"
          selected={false}
        />
      </ButtonGroup>
    ),
  },
];
