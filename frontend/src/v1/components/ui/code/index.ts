/*
 * The public API of the code and data components: import from here. The
 * helpers under `@v1/lib/code/` are internals and may change; this file is
 * what other pages build on.
 */
export type { CopyResult } from "@v1/lib/code/clipboard";
export {
  type DiffStats,
  describeChanges,
  diffStats,
} from "@v1/lib/code/diff";
export { CODE_LANGUAGES, type CodeLanguage } from "@v1/lib/code/highlight";
export {
  formatJson,
  formatJsonText,
  type JsonParseResult,
  parseJson,
} from "@v1/lib/code/json-lines";
export { CodeBlock, type CodeBlockProps, LANGUAGE_NAME } from "./CodeBlock";
export { CodeEditor, type CodeEditorProps } from "./CodeEditor";
export { CopyButton, type CopyButtonProps } from "./CopyButton";
export {
  type DiffLayout,
  DiffSummary,
  type DiffSummaryProps,
  DiffView,
  type DiffViewProps,
} from "./DiffView";
export { InlineCode, type InlineCodeProps } from "./InlineCode";
export {
  type JsonSource,
  JsonView,
  type JsonViewMode,
  type JsonViewOptions,
  type JsonViewProps,
} from "./JsonView";
export { Markdown, type MarkdownProps } from "./Markdown";
