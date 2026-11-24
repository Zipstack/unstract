import type { ReactElement } from "react";
import { Checkbox } from "./Checkbox";
import { Radio, RadioGroup } from "./RadioGroup";
import { Slider } from "./Slider";
import { Switch } from "./Switch";

/*
 * Every variant and state of the toggles, for the component gallery (P1-T01,
 * not merged yet: register these there, where each entry is shown in Light,
 * Dark and Unstract). Until then markup.test.tsx renders each one and
 * snapshots its markup. Every entry is controlled and static, so the
 * snapshot is stable.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const twoPlaces = (value: number) => value.toFixed(2);

export const TOGGLES_GALLERY: readonly GalleryEntry[] = [
  {
    name: "checkbox unchecked",
    element: <Checkbox label="Include page numbers" checked={false} />,
  },
  {
    name: "checkbox checked",
    element: <Checkbox label="Include page numbers" checked />,
  },
  {
    name: "checkbox mixed",
    element: <Checkbox label="Select all documents" checked="indeterminate" />,
  },
  {
    name: "checkbox disabled unchecked",
    element: <Checkbox label="Include page numbers" checked={false} disabled />,
  },
  {
    name: "checkbox disabled checked",
    element: <Checkbox label="Include page numbers" checked disabled />,
  },
  {
    name: "checkbox with description",
    element: (
      <Checkbox
        label="Highlight sources"
        description="Shows where each value was found in the document."
        checked
      />
    ),
  },
  {
    name: "checkbox bare",
    element: <Checkbox aria-label="Select row" checked={false} />,
  },
  {
    name: "switch off",
    element: <Switch label="Enable webhook" checked={false} />,
  },
  {
    name: "switch on",
    element: <Switch label="Enable webhook" checked />,
  },
  {
    name: "switch disabled off",
    element: <Switch label="Enable webhook" checked={false} disabled />,
  },
  {
    name: "switch disabled on",
    element: <Switch label="Enable webhook" checked disabled />,
  },
  {
    name: "switch with description",
    element: (
      <Switch
        label="Single pass extraction"
        description="Sends every prompt to the model in one request."
        checked
      />
    ),
  },
  {
    name: "radio group vertical",
    element: (
      <RadioGroup label="Extraction mode" value="form">
        <Radio value="native" label="Native text" />
        <Radio value="form" label="Form" />
        <Radio value="high" label="High quality" disabled />
      </RadioGroup>
    ),
  },
  {
    name: "radio group horizontal",
    element: (
      <RadioGroup label="Output" value="json" orientation="horizontal">
        <Radio value="json" label="JSON" />
        <Radio value="csv" label="CSV" />
        <Radio value="text" label="Text" />
      </RadioGroup>
    ),
  },
  {
    name: "radio group with description, no visible label",
    element: (
      <RadioGroup
        aria-label="Retrieval strategy"
        description="Chunks are only used when the document is larger than the context."
        value="simple"
      >
        <Radio value="simple" label="Simple" />
        <Radio value="fusion" label="Fusion" />
      </RadioGroup>
    ),
  },
  {
    name: "radio group disabled",
    element: (
      <RadioGroup
        label="Extraction mode"
        description="Set by the workspace administrator."
        value="form"
        disabled
      >
        <Radio value="native" label="Native text" />
        <Radio value="form" label="Form" />
      </RadioGroup>
    ),
  },
  {
    name: "radio with description",
    element: (
      <RadioGroup label="Chunking" value="none">
        <Radio value="none" label="None" />
        <Radio
          value="fixed"
          label="Fixed size"
          description="Splits the document into chunks of equal length."
        />
      </RadioGroup>
    ),
  },
  {
    name: "slider single with value shown",
    element: (
      <Slider
        label="Temperature"
        min={0}
        max={1}
        step={0.1}
        value={[0.7]}
        formatValue={twoPlaces}
        showValue
      />
    ),
  },
  {
    name: "slider range with thumb labels",
    element: (
      <Slider
        label="Pages"
        min={1}
        max={20}
        step={1}
        value={[3, 12]}
        thumbLabels={["First page", "Last page"]}
        showValue
      />
    ),
  },
  {
    name: "slider disabled",
    element: (
      <Slider
        label="Top K"
        min={0}
        max={10}
        step={1}
        value={[5]}
        showValue
        disabled
      />
    ),
  },
  {
    name: "slider with description",
    element: (
      <Slider
        label="Chunk overlap"
        description="Characters shared by neighbouring chunks."
        min={0}
        max={200}
        step={10}
        value={[20]}
        showValue
      />
    ),
  },
];
