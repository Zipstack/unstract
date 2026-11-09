import type { ReactElement } from "react";
import { CodeBlock } from "./CodeBlock";
import { CopyButton } from "./CopyButton";
import { DiffView } from "./DiffView";
import { InlineCode } from "./InlineCode";
import { JsonView } from "./JsonView";
import { Markdown } from "./Markdown";

/*
 * Every variant and state of the code components, for the component gallery
 * (P1-T01, not merged yet: register these there, where each entry is shown in
 * Light, Dark and Unstract). Until then markup.test.tsx renders each one and
 * snapshots its markup. CodeEditor is not here: it needs the Monaco CDN, and
 * its markup is Monaco's.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const PYTHON = `from unstract.llmwhisperer import LLMWhispererClientV2

client = LLMWhispererClientV2(api_key="lw-****")
# Wait for the result
result = client.whisper(file_path="form.pdf", mode="form")
print(result["extraction"]["result_text"])`;

const PROMPT_V1 = `# Document Data Extraction Task

## Objective
Extract structured data from the statement.
returning \`null\` for any field not found.`;

const PROMPT_V2 = `# Document Data Extraction Task

## Objective
Extract structured data from the statement.
returning \`null\` for any field not found. Return dates as printed
(MM/DD/YY) and keep amounts as numbers.`;

const EXTRACTION = {
  fees: 0,
  rewards: {
    reward_dollars: 1087.93,
    rewards_website: "americanexpress.com/cashbackrewards",
  },
  autopay: true,
  previous_balance: null,
  tags: [],
};

const MARKDOWN = `## Extract invoices

Pulls **line items** from PDFs. See [the docs](https://docs.unstract.com) or run:

\`\`\`bash
curl -X POST https://api.example.com/v1/extract
\`\`\`

| Field | Type |
| --- | --- |
| \`total\` | number |

- [x] Tables
- [ ] Handwriting`;

export const CODE_GALLERY: readonly GalleryEntry[] = [
  {
    name: "code block python with title",
    element: <CodeBlock code={PYTHON} language="python" title="Python" />,
  },
  {
    name: "code block markdown with line numbers",
    element: <CodeBlock code={PROMPT_V1} language="markdown" showLineNumbers />,
  },
  {
    name: "code block wrapped, no copy",
    element: (
      <CodeBlock
        code={'{"long": "a value long enough to wrap in a narrow panel"}'}
        language="json"
        wrap
        copyable={false}
      />
    ),
  },
  {
    name: "json view tree",
    element: <JsonView value={EXTRACTION} title="Extracted data" />,
  },
  {
    name: "json view tree collapsed to depth 1",
    element: <JsonView value={EXTRACTION} defaultExpandDepth={1} />,
  },
  {
    name: "json view raw",
    element: <JsonView value={EXTRACTION} defaultMode="raw" />,
  },
  {
    name: "json view invalid text",
    element: <JsonView text={'{"fees": 0,, }'} />,
  },
  {
    name: "json view empty",
    element: <JsonView value={undefined} showModeToggle={false} />,
  },
  {
    name: "diff split with labels",
    element: (
      <DiffView
        oldText={PROMPT_V1}
        newText={PROMPT_V2}
        language="markdown"
        oldLabel="v1 - Auto-generated prompt"
        newLabel="v2 - Tightened date handling"
      />
    ),
  },
  {
    name: "diff unified",
    element: (
      <DiffView oldText={PROMPT_V1} newText={PROMPT_V2} layout="unified" />
    ),
  },
  {
    name: "diff no changes",
    element: <DiffView oldText="same" newText="same" />,
  },
  {
    name: "markdown",
    element: <Markdown>{MARKDOWN}</Markdown>,
  },
  {
    name: "inline code chip and plain",
    element: (
      <p>
        Set <InlineCode>mode</InlineCode> to form; used{" "}
        <InlineCode variant="plain">1,204</InlineCode> tokens.
      </p>
    ),
  },
  {
    name: "copy button icon and labelled",
    element: (
      <div>
        <CopyButton text="x" />
        <CopyButton text="x" label="Copy code" showLabel />
        <CopyButton text="x" label="Copy key" toastOnCopy={false} />
      </div>
    ),
  },
];
