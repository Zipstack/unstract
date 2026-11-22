import { ProviderLogo } from "@v1/components/ui/BrandMark";
import { Button, IconButton, Link } from "@v1/components/ui/button";
import {
  InlineAlert,
  Skeleton,
  SkeletonBlock,
  SkeletonText,
} from "@v1/components/ui/feedback";
import { SearchField } from "@v1/components/ui/form";
import { ACTION_ICONS, STATUS_ICONS } from "@v1/lib/icons";
import type { ReactElement, ReactNode } from "react";
import { Drawer, type DrawerProps, DrawerSection } from "./Drawer";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "./HoverCard";
import { Popover, PopoverContent, PopoverTrigger } from "./Popover";
import { Tooltip } from "./Tooltip";

// Every overlay open, with the drawer's loading and error states, for the component gallery (P1-T01).

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const noop = (): void => undefined;

function Rows({ rows }: { rows: readonly (readonly [string, string])[] }) {
  return (
    <dl className="ui:m-0 ui:grid ui:grid-cols-2 ui:gap-y-2 ui:text-body-small">
      {rows.flatMap(([label, value]) => [
        <dt key={`${label}-label`} className="ui:text-muted-foreground">
          {label}
        </dt>,
        <dd key={`${label}-value`} className="ui:m-0 ui:text-right">
          {value}
        </dd>,
      ])}
    </dl>
  );
}

function StatusChip({ children }: { children: ReactNode }) {
  return (
    <span className="ui:rounded-sm ui:bg-success/10 ui:px-1.5 ui:py-0.5 ui:text-caption ui:font-medium ui:text-success">
      {children}
    </span>
  );
}

const DEPLOYMENT_ACTIONS = (
  <>
    <Button>View logs</Button>
    <Button variant="outline">Code snippets</Button>
    <Button variant="outline">Postman</Button>
  </>
);

const DEPLOYMENT_SECTIONS = (
  <>
    <DrawerSection title="Last 5 runs" meta="most recent 20 Aug, 16:30">
      <p className="ui:m-0 ui:text-body-small">All five succeeded.</p>
    </DrawerSection>
    <DrawerSection>
      <Rows
        rows={[
          ["Workflow", "health_monitoring_workflow"],
          ["API keys", "1 active key"],
          ["Created", "12 Mar 2026 by ritwik"],
        ]}
      />
    </DrawerSection>
  </>
);

/** Frame A05, the API deployment detail; `children` replaces its sections. */
function DeploymentDrawer({ children, ...props }: Partial<DrawerProps>) {
  return (
    <Drawer
      defaultOpen
      trigger={<Button variant="outline">Open drawer</Button>}
      title="health-monitoring API"
      description="API deployment for health-monitoring · owner ritwik"
      badge={<StatusChip>Success</StatusChip>}
      actions={DEPLOYMENT_ACTIONS}
      {...props}
    >
      {children ?? DEPLOYMENT_SECTIONS}
    </Drawer>
  );
}

const drawerEntries: GalleryEntry[] = [
  { name: "drawer md (480)", element: <DeploymentDrawer /> },
  {
    name: "drawer lg (640) with a logo",
    element: (
      <DeploymentDrawer
        size="lg"
        title="Unstract's google drive"
        description="Google Drive · drive.google.com"
        badge={undefined}
        leading={
          <ProviderLogo
            provider="google_drive"
            name="Google Drive"
            size="lg"
            decorative
          />
        }
      />
    ),
  },
  {
    name: "drawer loading",
    element: (
      <DeploymentDrawer badge={undefined}>
        <Skeleton label="Loading deployment">
          <SkeletonBlock className="ui:h-16" />
          <SkeletonText lines={4} />
        </Skeleton>
      </DeploymentDrawer>
    ),
  },
  {
    name: "drawer error",
    element: (
      <DeploymentDrawer badge={undefined}>
        <InlineAlert title="Could not load this deployment" onRetry={noop}>
          The server did not answer. Try again in a moment.
        </InlineAlert>
      </DeploymentDrawer>
    ),
  },
];

const popoverEntries: GalleryEntry[] = [
  {
    // Frame C13, the LLM profile behind a model column.
    name: "popover with a title and rows",
    element: (
      <Popover defaultOpen>
        <PopoverTrigger asChild>
          <IconButton aria-label="Profile details" icon={STATUS_ICONS.info} />
        </PopoverTrigger>
        <PopoverContent
          title="test3"
          description="LLM profile used by this model column"
        >
          <Rows
            rows={[
              ["LLM", "claude-sonnet-4-6"],
              ["Chunk size", "0"],
              ["Reindex", "No"],
            ]}
          />
        </PopoverContent>
      </Popover>
    ),
  },
  {
    name: "popover with controls",
    element: (
      <Popover defaultOpen>
        <PopoverTrigger asChild>
          <Button variant="outline" leadingIcon={ACTION_ICONS.filter}>
            Columns
          </Button>
        </PopoverTrigger>
        <PopoverContent aria-label="Choose columns">
          <div className="ui:flex ui:flex-col ui:gap-3">
            <SearchField aria-label="Find a column" />
            <Button size="sm">Apply</Button>
          </div>
        </PopoverContent>
      </Popover>
    ),
  },
];

const hintEntries: GalleryEntry[] = [
  {
    name: "hover card",
    element: (
      <HoverCard defaultOpen>
        <HoverCardTrigger asChild>
          <Link href="#gpt-4o">gpt-4o</Link>
        </HoverCardTrigger>
        <HoverCardContent>
          <p className="ui:m-0 ui:text-body-small">
            OpenAI · 128k context · default for this project
          </p>
        </HoverCardContent>
      </HoverCard>
    ),
  },
  {
    name: "tooltip",
    element: (
      <Tooltip content="Copy endpoint" defaultOpen>
        <IconButton aria-label="Copy" icon={ACTION_ICONS.copy} />
      </Tooltip>
    ),
  },
];

export const OVERLAY_GALLERY: readonly GalleryEntry[] = [
  ...drawerEntries,
  ...popoverEntries,
  ...hintEntries,
];
