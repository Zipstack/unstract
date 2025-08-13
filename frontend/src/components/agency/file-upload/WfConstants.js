/**
 * Workflow-related constants
 */

// Maximum number of files allowed per workflow execution
export const MAX_WORKFLOW_EXECUTION_FILES = 2;

// Error messages for workflow validation
export const WORKFLOW_VALIDATION_MESSAGES = {
  MAX_FILES_EXCEEDED: `Maximum ${MAX_WORKFLOW_EXECUTION_FILES} files are allowed for workflow execution.`,
  NO_FILES_SELECTED: "Please select at least one file to proceed.",
  WORKFLOW_ID_REQUIRED: "Workflow ID is required for execution.",
};