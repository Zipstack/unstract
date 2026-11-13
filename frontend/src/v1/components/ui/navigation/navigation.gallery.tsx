import type { ReactElement } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "./Accordion";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "./Breadcrumb";
import { Checklist, type ChecklistStep } from "./Checklist";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./Collapsible";
import { Pagination } from "./Pagination";
import { Stepper, type StepperStep } from "./Stepper";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs";

/*
 * Every variant and state of the navigation primitives, for the component
 * gallery (P1-T01, not merged yet: register these there, where each entry is
 * shown in Light, Dark and Unstract). Until then markup.test.tsx renders each
 * one, snapshots its markup and runs the accessibility scan on it.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const noop = (): void => undefined;

/** Frame 789:3765: one step of each state. */
export const CHECKLIST_STEPS: readonly ChecklistStep[] = [
  {
    id: "source",
    label: "Source connector",
    value: "s3_staging · /invoice",
    state: "done",
  },
  {
    id: "destination",
    label: "Destination connector",
    value: "Not configured",
    state: "in-progress",
  },
  {
    id: "project",
    label: "Prompt Studio project",
    value: "Not selected",
    state: "not-started",
  },
  {
    id: "deploy",
    label: "Deploy workflow",
    value: "s3_staging · not reachable",
    state: "failed",
  },
];

export const STEPPER_STEPS: readonly StepperStep[] = [
  { id: "upload", label: "Upload", value: "12 files", state: "done" },
  { id: "extract", label: "Extract", value: "4 of 12", state: "in-progress" },
  { id: "review", label: "Review", state: "not-started" },
  { id: "export", label: "Export", value: "Quota reached", state: "failed" },
];

function tabs(variant: "bar" | "segmented", disabled = false): ReactElement {
  return (
    <Tabs variant={variant} defaultValue="parser">
      <TabsList aria-label="Output">
        <TabsTrigger value="parser">Document Parser</TabsTrigger>
        <TabsTrigger value="combined">Combined Output</TabsTrigger>
        <TabsTrigger value="raw" disabled={disabled}>
          Raw text
        </TabsTrigger>
      </TabsList>
      <TabsContent value="parser">Parser output</TabsContent>
      <TabsContent value="combined">Combined output</TabsContent>
      <TabsContent value="raw">Raw text</TabsContent>
    </Tabs>
  );
}

export const NAVIGATION_GALLERY: readonly GalleryEntry[] = [
  { name: "tabs bar", element: tabs("bar") },
  { name: "tabs bar with a disabled tab", element: tabs("bar", true) },
  { name: "tabs segmented", element: tabs("segmented") },
  {
    name: "tabs segmented with a disabled tab",
    element: tabs("segmented", true),
  },
  {
    name: "breadcrumb",
    element: (
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="#workflows">Workflows</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="#invoices">Invoices</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Settings</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
    ),
  },
  {
    name: "accordion one open",
    element: (
      <Accordion type="single" collapsible defaultValue="general">
        <AccordionItem value="general">
          <AccordionTrigger>General</AccordionTrigger>
          <AccordionContent>Name, description and owner.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="advanced">
          <AccordionTrigger>Advanced</AccordionTrigger>
          <AccordionContent>Retries and timeouts.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="locked" disabled>
          <AccordionTrigger>Billing</AccordionTrigger>
          <AccordionContent>Plan details.</AccordionContent>
        </AccordionItem>
      </Accordion>
    ),
  },
  {
    name: "collapsible closed",
    element: (
      <Collapsible>
        <CollapsibleTrigger>Debug panel</CollapsibleTrigger>
        <CollapsibleContent>Step-by-step output</CollapsibleContent>
      </Collapsible>
    ),
  },
  {
    name: "collapsible open",
    element: (
      <Collapsible defaultOpen>
        <CollapsibleTrigger>Logs</CollapsibleTrigger>
        <CollapsibleContent>Run started</CollapsibleContent>
      </Collapsible>
    ),
  },
  {
    name: "checklist interactive, every state",
    element: (
      <Checklist
        aria-label="Workflow setup"
        steps={CHECKLIST_STEPS}
        currentId="destination"
        onSelect={noop}
      />
    ),
  },
  {
    name: "checklist read-only",
    element: <Checklist aria-label="Workflow setup" steps={CHECKLIST_STEPS} />,
  },
  {
    name: "stepper, every state",
    element: <Stepper aria-label="Run stages" steps={STEPPER_STEPS} />,
  },
  {
    name: "pagination first page",
    element: (
      <Pagination
        page={1}
        pageSize={10}
        total={42}
        onPageChange={noop}
        onPageSizeChange={noop}
      />
    ),
  },
  {
    name: "pagination middle page",
    element: (
      <Pagination page={3} pageSize={10} total={42} onPageChange={noop} />
    ),
  },
  {
    name: "pagination last page",
    element: (
      <Pagination page={5} pageSize={10} total={42} onPageChange={noop} />
    ),
  },
  {
    name: "pagination empty",
    element: (
      <Pagination page={1} pageSize={10} total={0} onPageChange={noop} />
    ),
  },
];
