/**
 * Agentic Prompt Studio - Main Export File
 * Phase 1: Self-contained implementation with mock APIs
 * Phase 2: Move to plugins/ with try-catch imports
 *
 * Note: All React components use .jsx extension
 */

// Pages (.jsx files)
export { default as Dashboard } from "./pages/Dashboard.jsx";
export { default as Projects } from "./pages/Projects.jsx";
export { default as ProjectDetail } from "./pages/ProjectDetail.jsx";
// TODO: Export remaining pages when implemented
// export { default as ProjectAnalytics } from "./pages/ProjectAnalytics.jsx";
// export { default as ProjectMismatchMatrix } from "./pages/ProjectMismatchMatrix.jsx";
// export { default as Settings } from "./pages/Settings.jsx";

// Components (.jsx files)
export { default as AccuracyOverviewPanel } from "./components/AccuracyOverviewPanel.jsx";
export { default as ComparePromptsModal } from "./components/ComparePromptsModal.jsx";
export { default as DataRenderer } from "./components/DataRenderer.jsx";
export { default as DocumentManager } from "./components/DocumentManager.jsx";
export { default as FieldComparisonModal } from "./components/FieldComparisonModal.jsx";
export { default as MonacoEditor } from "./components/MonacoEditor.jsx";
export { default as NoteEditorModal } from "./components/NoteEditorModal.jsx";
export { default as PdfViewer } from "./components/PdfViewer.jsx";
export { default as PromptHistoryModal } from "./components/PromptHistoryModal.jsx";
export { default as SavePromptModal } from "./components/SavePromptModal.jsx";
export { default as StatusBadge } from "./components/StatusBadge.jsx";

// Hooks (.js files - not React components)
export { useMockApi } from "./hooks/useMockApi.js";

// Utils (.js files - not React components)
export * as helpers from "./utils/helpers.js";

// Mock Data (.js files - not React components)
export * as mockData from "./mock/mockData.js";
