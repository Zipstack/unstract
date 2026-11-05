# Code and structured data

The one way v1 shows code, JSON, diffs and Markdown (P1-T16, UN-4400).
Import everything from `@v1/components/ui/code`:

```tsx
import {
  CodeBlock,
  CodeEditor,
  CopyButton,
  DiffView,
  formatJson,
  InlineCode,
  JsonView,
  Markdown,
} from "@v1/components/ui/code";
```

| Component | Use it for | Frames |
| --- | --- | --- |
| `CodeBlock` | Read-only, highlighted code: snippets, prompts, request bodies | V10, P09 (LLMW), API Hub E01 |
| `JsonView` | JSON as an expandable tree or raw text, any size | V14, V15, D01–D03, L07, L09, B08, API Hub P01 |
| `DiffView` | Before and after, side by side or unified | V12, H20 |
| `Markdown` | Model output and API Hub `long_description` | D01, PA-T03 |
| `CopyButton` | Any "copy this" control | P09, API keys |
| `CodeEditor` | Editable code (Monaco) | V08, B04 |
| `InlineCode` | Mono text inside other text: code spans, IDs, token counts | everywhere |

## Rules

- **Mono font through the token only.** Geist Mono comes from the `font-mono`
  token (`ui:font-mono`, paired with the `ui:text-mono` type role). Never load
  or name a monospace font. For an ID or a token count in a table, use
  `<InlineCode variant="plain">` rather than adding the classes yourself.
  (Decision FrontendV1:MonoFontToken; `base.css` also sets `<code>`, `<pre>`,
  `<kbd>` and `<samp>` to the token.)
- **Colours are tokens.** Syntax colours are `code-key`, `code-string`,
  `code-number`, `code-literal`, `code-keyword` and `code-comment`; diff
  colours are `diff-added`, `diff-removed` and their `-foreground`s. All are in
  `styles/tokens.json`, in every mode. Never colour code by hand.
- **Monaco loads from its default CDN, and v1 never configures it.**
  `CodeEditor` lazy-loads `@monaco-editor/react`, whose loader fetches the
  runtime from `cdn.jsdelivr.net`, as v0's editors do (nginx's CSP allows it).
  Never call `loader.config()` in v1: the loader is a singleton shared with v0
  in the same bundle, so configuring it from v1 would change v0.
- **Height.** Each component grows with its content. Constrain it with a class
  and its body scrolls: `className="ui:max-h-80"`, or
  `className="ui:h-full ui:max-h-none"` to fill a sized panel. `JsonView`
  defaults to `ui:max-h-120` (480px) so a large document scrolls (and
  virtualises) instead of stretching the page.

## CodeBlock

```tsx
<CodeBlock code={snippet} language="python" title="Python" />
<CodeBlock code={prompt} language="markdown" showLineNumbers copyable={false} />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `code` | `string` | required | |
| `language` | `"json" \| "bash" \| "python" \| "javascript" \| "typescript" \| "yaml" \| "markdown" \| "text"` | `"text"` | `text` is not highlighted |
| `title` | `ReactNode` | — | header, left |
| `actions` | `ReactNode` | — | header, before the copy button |
| `copyable` | `boolean` | `true` | copy button in the header |
| `showLineNumbers` | `boolean` | `false` | numbers are never copied |
| `wrap` | `boolean` | `false` | wrap instead of scrolling sideways |
| `aria-label` | `string` | title, else "Python code" | names the scrollable region |

The header shows when there is a title, actions or a copy button. Other `div`
props pass through to the root.

## JsonView

```tsx
<JsonView value={extraction} title="Extracted data" />
<JsonView text={responseBody} defaultMode="raw" />
<JsonView value={doc} mode={mode} onModeChange={setMode} actions={<FindButton />} />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `value` | `unknown` | — | any JSON-serialisable value; pass this **or** `text` |
| `text` | `string` | — | JSON source; invalid text shows an error and the text as received |
| `mode` / `defaultMode` / `onModeChange` | `"tree" \| "raw"` | `"tree"` | controlled or not |
| `defaultExpandDepth` | `number` | all, or 2 above 300 lines | containers at this depth or deeper start folded (root is 0) |
| `showLineNumbers` | `boolean` | `true` | |
| `showModeToggle` | `boolean` | `true` | the Tree / Raw switch |
| `title`, `actions`, `copyable` | | `copyable` on | toolbar, as CodeBlock; Copy copies the pretty print |
| `aria-label` | `string` | `"JSON"` | names the tree or raw region |

- Both modes render one line model, the exact `JSON.stringify(value, null, 2)`
  text. Above 300 showing lines only the rows in view are rendered
  (`@tanstack/react-virtual`), so the 5,000-line case stays responsive.
- The tree is an ARIA `tree` with `aria-activedescendant`: Up/Down move,
  Home/End jump, Right expands (or enters), Left collapses (or goes to the
  parent), Enter or Space toggles. Expand all / Collapse all are in the
  toolbar. Folded containers show `{…} 3 keys`.
- `value` (or `text`) is compared by identity: a new object re-flattens the
  document and resets folding, so pass a stable or memoised value, not an
  inline literal.
- `value` goes through `JSON.stringify` rules (`toJSON`, dropped `undefined`).
  A value it cannot serialise (a BigInt, a cycle) shows the error state;
  `undefined` shows "No data".

## DiffView

```tsx
<DiffView
  oldText={v1.prompt}
  newText={v2.prompt}
  language="markdown"
  oldLabel="v1 - Auto-generated prompt"
  newLabel="v2 - Tightened date handling"
/>
<DiffView oldText={formatJson(before)} newText={formatJson(after)} language="json"
  oldLabel="BEFORE" newLabel="AFTER" />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `oldText`, `newText` | `string` | required | for JSON, pass `formatJson(value)` |
| `language` | as CodeBlock | `"text"` | highlights both sides |
| `layout` | `"split" \| "unified"` | `"split"` | |
| `oldLabel`, `newLabel` | `ReactNode` | — | column heads, split layout only |
| `showSummary` | `boolean` | `true` | the "1 change +2 −1" bar |
| `showLineNumbers` | `boolean` | `true` | |
| `wrap` | `boolean` | `true` | so no change hides off the side |
| `aria-label` | `string` | `"Changes"` | names the scrollable region |

Changed lines are tinted, marked `+` / `−`, and read as "Added:" / "Removed:"
by screen readers. `DiffSummary` (with `computeLineDiff(old, new).stats`)
shows the summary on its own, for a row like H20's "what changed".

## Markdown

```tsx
<Markdown>{api.long_description}</Markdown>
```

GitHub Markdown (tables, task lists, strikethrough) via react-markdown 8 and
remark-gfm 3, the versions v0 uses. Raw HTML is dropped (no rehype-raw); link
and image URLs pass react-markdown's safe-URL filter, so `javascript:` never
survives. External `http(s)` links open in a new tab with
`rel="noopener noreferrer"`. Fenced code renders as a `CodeBlock` in its
language (`py`, `sh`, `yml`… are understood; unknown names are plain text).
Styled with the v1 type roles, not `prose`.

## CopyButton

```tsx
<CopyButton text={apiKey} label="Copy key" />
<CopyButton text={() => bigValue()} label="Copy code" showLabel />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `text` | `string \| () => string` | required | a function is read at click time |
| `label` | `string` | `"Copy"` | accessible name; visible with `showLabel` |
| `showLabel` | `boolean` | `false` | icon only by default |
| `toastOnCopy` | `boolean` | `true` | confirm through `toast` from `@v1/lib/notify` |
| `copiedMessage` | `string` | `"Copied to clipboard"` | the success toast |
| `onCopy` | `(result: "copied" \| "failed" \| "unavailable") => void` | — | |

Every attempt also gives inline feedback for two seconds: a check, or "Copy
failed" / "Copy unavailable". With `toastOnCopy={false}` a polite live region
announces the result instead, so it is heard once. The toast needs the
`Toaster` mounted in the v1 root (see the v1 README, Feedback).

## CodeEditor

```tsx
<CodeEditor aria-label="JSON schema" language="json" value={schema} onChange={setSchema} />
<CodeEditor aria-label="Reference" defaultValue={text} readOnly height="100%" />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `value` / `defaultValue` / `onChange` | `string` / `(value: string) => void` | — | controlled or not |
| `language` | as CodeBlock | `"text"` | |
| `readOnly` | `boolean` | `false` | |
| `lineNumbers` | `boolean` | `true` | |
| `height` | `number \| string` | `320` | pixels or a CSS length |
| `aria-label` | `string` | required | the editor has no visible label of its own |

It follows the v1 theme (dark → Monaco's `vs-dark`, otherwise `light`) and the
mono font token, and shows a skeleton while Monaco loads. Monaco keeps Tab
inside the editor; its own "Toggle Tab Key Moves Focus" binding (Ctrl+M, or
Ctrl+Shift+M on macOS) lets keyboard users leave.

In tests, mock Monaco, whose loader would fetch from the CDN:
`vi.mock("@monaco-editor/react", () => ({ default: (props) => <textarea … /> }))`
(see `CodeEditor.test.tsx`).

## InlineCode

`<InlineCode>mode</InlineCode>` sets code on a muted chip;
`<InlineCode variant="plain">1,204</InlineCode>` is the mono font alone.

## Gallery and tests

`code.gallery.tsx` lists every variant and state. Until the component gallery
(P1-T01) lands, `markup.test.tsx` renders each entry, snapshots its markup in
`__snapshots__/markup.md` and runs axe on it. The 5,000-line performance case
is in `JsonView.test.tsx`; its fixture is `largeJson()` in
`test/fixtures/json.ts`.
