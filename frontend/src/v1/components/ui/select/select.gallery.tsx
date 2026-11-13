import {
  Braces,
  Cloud,
  Database,
  FileImage,
  FileText,
  HardDrive,
  Server,
  Table,
} from "lucide-react";
import type { ReactElement } from "react";
import { Combobox } from "./Combobox";
import { MultiSelect } from "./MultiSelect";
import type { SelectOption } from "./options";
import { SegmentedControl } from "./SegmentedControl";
import { Select } from "./Select";

/*
 * Every closed state of the selection inputs, for the component gallery
 * (P1-T01, not merged yet: register these there, where each entry is shown in
 * Light, Dark and Unstract). Until then markup.test.tsx renders each one and
 * snapshots its markup. Open lists are not here: Radix portals them out of
 * the rendered container, so the behaviour tests and `Listbox.test.tsx`
 * cover them.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const MODES: readonly SelectOption[] = [
  { value: "native_text", label: "Native text" },
  { value: "low_cost", label: "Low cost" },
  { value: "high_quality", label: "High quality" },
  { value: "form", label: "Form" },
];

const STORAGE: readonly SelectOption[] = [
  { value: "s3", label: "Amazon S3", leading: <Cloud /> },
  { value: "postgres", label: "PostgreSQL", leading: <Database /> },
  { value: "local", label: "Local storage", leading: <HardDrive /> },
  { value: "sftp", label: "SFTP", leading: <Server /> },
];

const MODELS: readonly SelectOption[] = [
  {
    value: "gpt-4o",
    label: "GPT-4o",
    description: "OpenAI",
    keywords: ["gpt-4o-2024-08-06"],
  },
  {
    value: "claude-sonnet",
    label: "Claude Sonnet",
    description: "Anthropic",
  },
  { value: "gemini-pro", label: "Gemini Pro", description: "Google" },
];

const TAGS: readonly SelectOption[] = [
  { value: "invoices", label: "Invoices" },
  { value: "receipts", label: "Receipts" },
  { value: "contracts", label: "Contracts" },
  { value: "statements", label: "Statements" },
];

const THREE_TAGS = ["invoices", "receipts", "contracts"] as const;

export const SELECT_GALLERY: readonly GalleryEntry[] = [
  {
    name: "select placeholder",
    element: (
      <Select
        aria-label="Mode"
        options={MODES}
        value=""
        placeholder="Select a mode"
      />
    ),
  },
  {
    name: "select with value",
    element: <Select aria-label="Mode" options={MODES} value="form" />,
  },
  {
    name: "select with leading icons and a selected value",
    element: <Select aria-label="Storage" options={STORAGE} value="postgres" />,
  },
  {
    name: "select disabled",
    element: (
      <Select aria-label="Mode" options={MODES} value="low_cost" disabled />
    ),
  },
  {
    name: "select invalid",
    element: (
      <Select
        aria-label="Mode"
        options={MODES}
        value=""
        placeholder="Select a mode"
        invalid
      />
    ),
  },
  {
    name: "combobox empty",
    element: (
      <Combobox
        aria-label="Model"
        options={MODELS}
        value={null}
        placeholder="Search models"
      />
    ),
  },
  {
    name: "combobox with value",
    element: (
      <Combobox aria-label="Model" options={MODELS} value="claude-sonnet" />
    ),
  },
  {
    name: "combobox disabled",
    element: (
      <Combobox aria-label="Model" options={MODELS} value="gpt-4o" disabled />
    ),
  },
  {
    name: "combobox invalid",
    element: (
      <Combobox
        aria-label="Model"
        options={MODELS}
        value={null}
        placeholder="Search models"
        invalid
      />
    ),
  },
  {
    name: "multi-select empty",
    element: (
      <MultiSelect
        aria-label="Tags"
        options={TAGS}
        value={[]}
        placeholder="Add tags"
      />
    ),
  },
  {
    name: "multi-select with three chips",
    element: (
      <MultiSelect aria-label="Tags" options={TAGS} value={THREE_TAGS} />
    ),
  },
  {
    name: "multi-select disabled",
    element: (
      <MultiSelect
        aria-label="Tags"
        options={TAGS}
        value={["statements"]}
        disabled
      />
    ),
  },
  {
    name: "multi-select invalid",
    element: (
      <MultiSelect
        aria-label="Tags"
        options={TAGS}
        value={[]}
        placeholder="Add tags"
        invalid
      />
    ),
  },
  {
    name: "segmented two options",
    element: (
      <SegmentedControl
        aria-label="Layout"
        options={[
          { value: "split", label: "Split" },
          { value: "unified", label: "Unified" },
        ]}
        value="split"
      />
    ),
  },
  {
    name: "segmented five options with icons",
    element: (
      <SegmentedControl
        aria-label="Output"
        options={[
          { value: "text", label: "Text", icon: <FileText /> },
          { value: "table", label: "Table", icon: <Table /> },
          { value: "json", label: "JSON", icon: <Braces /> },
          { value: "image", label: "Image", icon: <FileImage /> },
          { value: "raw", label: "Raw", icon: <FileText /> },
        ]}
        value="json"
      />
    ),
  },
  {
    name: "segmented disabled",
    element: (
      <SegmentedControl
        aria-label="Layout"
        options={[
          { value: "split", label: "Split" },
          { value: "unified", label: "Unified" },
        ]}
        value="unified"
        disabled
      />
    ),
  },
];
