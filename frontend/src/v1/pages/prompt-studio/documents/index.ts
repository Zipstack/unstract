/*
 * Prompt Studio's documents: the viewer pane and Manage Documents. The
 * workspace frame mounts both and owns the selection (useDocumentSelection).
 */

export {
  DocumentsPanel,
  type DocumentsPanelProps,
} from "./DocumentsPanel";
export {
  DocumentViewerPane,
  type DocumentViewerPaneProps,
  type ViewerHighlights,
} from "./DocumentViewerPane";
export type { PromptCoverage } from "./removal";
export {
  OSS_UPLOAD_POLICY,
  profileGate,
  type UploadPolicy,
  type UploadType,
} from "./uploadPolicy";
export {
  type DocumentSelection,
  useDocumentSelection,
} from "./useDocumentSelection";
