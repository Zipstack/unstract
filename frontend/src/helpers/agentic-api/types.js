/**
 * Type definitions for Agentic Studio API
 * Mirroring the autoprompt frontend types but adapted for JavaScript
 */

/* eslint-disable camelcase */
// Disable camelcase for this file as we need to match backend API parameter names

// Project types
export const createProjectRequest = (name, description = null) => ({
  name,
  description,
});

export const updateProjectRequest = (name = null, description = null) => {
  const req = {};
  if (name !== null) req.name = name;
  if (description !== null) req.description = description;
  return req;
};

export const updateProjectSettingsRequest = (
  extractor_llm_id = null,
  agent_llm_id = null,
  llmwhisperer_id = null,
  lightweight_llm_id = null
) => {
  const req = {};
  if (extractor_llm_id !== null) req.extractor_llm_id = extractor_llm_id;
  if (agent_llm_id !== null) req.agent_llm_id = agent_llm_id;
  if (llmwhisperer_id !== null) req.llmwhisperer_id = llmwhisperer_id;
  if (lightweight_llm_id !== null) req.lightweight_llm_id = lightweight_llm_id;
  return req;
};

// Document status types
export const STAGE_STATUS = {
  COMPLETE: "complete",
  PENDING: "pending",
  PROCESSING: "processing",
  ERROR: "error",
};

export const PROCESSING_STATUS = {
  PENDING: "pending",
  PROCESSING: "processing",
  COMPLETE: "complete",
  ERROR: "error",
};

export const JOB_STATUS = {
  QUEUED: "queued",
  STARTED: "started",
  FINISHED: "finished",
  FAILED: "failed",
};

// Prompt types
export const TUNING_STRATEGY = {
  SINGLE: "single",
  MULTIAGENT: "multiagent",
};

export const PROMPT_GENERATION_STATUS = {
  QUEUED: "queued",
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
};

// Connector types
export const CONNECTOR_TYPE = {
  LLM: "LLM",
  LLM_WHISPERER: "LLMWhisperer",
};

export const LLM_PROVIDER = {
  OPENAI: "OpenAI",
  ANTHROPIC: "Anthropic",
  AWS_BEDROCK: "AWS Bedrock",
  AZURE_OPENAI: "Azure OpenAI",
  DEEPSEEK: "DeepSeek",
  GOOGLE_VERTEX_AI: "Google Vertex AI",
};

// Matrix types
export const MATRIX_STATUS = {
  MATCH: "match",
  PARTIAL: "partial",
  MISMATCH: "mismatch",
};

// Helper functions
export const createPromptRequest = (
  prompt_text,
  short_desc,
  long_desc,
  base_version = null
) => ({
  prompt_text,
  short_desc,
  long_desc,
  ...(base_version !== null && { base_version }),
});

export const generateMetadataRequest = (prompt_text, base_version) => ({
  prompt_text,
  base_version,
});

export const tunePromptRequest = (
  field_path,
  strategy = null,
  connector_id = null
) => {
  const req = { field_path };
  if (strategy !== null) req.strategy = strategy;
  if (connector_id !== null) req.connector_id = connector_id;
  return req;
};

export const createConnectorRequest = (
  type,
  provider,
  name,
  model,
  credentials,
  params = {}
) => ({
  type,
  provider,
  name,
  model,
  credentials,
  params,
});

export const createNoteRequest = (field_path, note_text) => ({
  field_path,
  note_text,
});
