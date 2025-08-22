/**
 * Workflow-related constants
 */

// Maximum number of files allowed per workflow page execution
export const WORKFLOW_PAGE_MAX_FILES = 2;

// Error messages for workflow validation
export const WORKFLOW_VALIDATION_MESSAGES = {
  MAX_FILES_EXCEEDED: `Maximum ${WORKFLOW_PAGE_MAX_FILES} files are allowed for workflow execution.`,
  NO_FILES_SELECTED: "Please select at least one file to proceed.",
  WORKFLOW_ID_REQUIRED: "Workflow ID is required for execution.",
};
