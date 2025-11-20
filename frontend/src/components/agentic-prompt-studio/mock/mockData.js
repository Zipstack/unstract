/**
 * Mock data for Agentic Prompt Studio
 * This file contains realistic mock data structures that mimic the AutoPrompt backend API
 * TODO: Replace with actual API calls in Phase 2
 */

// Mock Projects
export const mockProjects = [
  {
    id: "proj_1",
    name: "Invoice Extraction",
    description: "Extract structured data from invoices",
    created_at: "2025-01-10T10:00:00Z",
    extractor_llm_id: "llm_openai_gpt4",
    agent_llm_id: "llm_anthropic_claude",
    llmwhisperer_id: "llmw_1",
    lightweight_llm_id: "llm_openai_gpt35",
  },
  {
    id: "proj_2",
    name: "Medical Records Processing",
    description: "Extract patient information from medical documents",
    created_at: "2025-01-12T14:30:00Z",
    extractor_llm_id: "llm_anthropic_claude",
    agent_llm_id: "llm_anthropic_claude",
    llmwhisperer_id: null,
    lightweight_llm_id: "llm_openai_gpt35",
  },
  {
    id: "proj_3",
    name: "Contract Analysis",
    description: "Parse legal contracts and extract key terms",
    created_at: "2025-01-15T09:15:00Z",
    extractor_llm_id: "llm_openai_gpt4",
    agent_llm_id: "llm_openai_gpt4",
    llmwhisperer_id: "llmw_1",
    lightweight_llm_id: null,
  },
];

// Mock Documents
export const mockDocuments = {
  proj_1: [
    {
      id: "doc_1",
      project_id: "proj_1",
      original_filename: "invoice_001.pdf",
      stored_path: "/uploads/invoice_001.pdf",
      size_bytes: 245678,
      pages: 2,
      uploaded_at: "2025-01-10T11:00:00Z",
      raw_text:
        "INVOICE\n\nInvoice Number: INV-2025-001\nDate: January 10, 2025\n\nBill To:\nAcme Corporation\n123 Business St\nSan Francisco, CA 94105\n\nAmount Due: $1,500.00",
    },
    {
      id: "doc_2",
      project_id: "proj_1",
      original_filename: "invoice_002.pdf",
      stored_path: "/uploads/invoice_002.pdf",
      size_bytes: 312456,
      pages: 3,
      uploaded_at: "2025-01-10T11:15:00Z",
      raw_text:
        "INVOICE\n\nInvoice Number: INV-2025-002\nDate: January 11, 2025\n\nBill To:\nTech Innovations Inc\n456 Tech Ave\nAustin, TX 78701\n\nAmount Due: $2,750.00",
    },
  ],
};

// Mock Schema
export const mockSchema = {
  id: "schema_1",
  project_id: "proj_1",
  json_schema: JSON.stringify({
    type: "object",
    properties: {
      invoice_number: { type: "string" },
      invoice_date: { type: "string", format: "date" },
      bill_to: {
        type: "object",
        properties: {
          company_name: { type: "string" },
          address: { type: "string" },
          city: { type: "string" },
          state: { type: "string" },
          zip_code: { type: "string" },
        },
      },
      amount_due: { type: "number" },
      line_items: {
        type: "array",
        items: {
          type: "object",
          properties: {
            description: { type: "string" },
            quantity: { type: "number" },
            unit_price: { type: "number" },
            total: { type: "number" },
          },
        },
      },
    },
  }),
  created_at: "2025-01-10T12:00:00Z",
  updated_at: "2025-01-10T12:00:00Z",
};

// Mock Prompts
export const mockPrompts = [
  {
    id: "prompt_1",
    project_id: "proj_1",
    version: 1,
    short_desc: "Initial prompt",
    long_desc: "First version of the extraction prompt with basic fields",
    prompt_text:
      "Extract the following information from the invoice:\n- Invoice Number\n- Date\n- Bill To\n- Amount Due",
    created_at: "2025-01-10T12:30:00Z",
    accuracy: null,
  },
  {
    id: "prompt_2",
    project_id: "proj_1",
    version: 2,
    short_desc: "Added line items extraction",
    long_desc:
      "Enhanced version that includes line item details and improves address parsing",
    prompt_text:
      "Extract the following information from the invoice:\n- Invoice Number\n- Date\n- Bill To (including full address breakdown)\n- Amount Due\n- Line Items (description, quantity, unit price, total)",
    created_at: "2025-01-10T14:00:00Z",
    accuracy: 78.5,
  },
  {
    id: "prompt_3",
    project_id: "proj_1",
    version: 3,
    short_desc: "Improved date parsing",
    long_desc: "Fixed date format inconsistencies and added validation rules",
    prompt_text:
      "Extract the following information from the invoice:\n- Invoice Number\n- Date (format as YYYY-MM-DD)\n- Bill To (including full address breakdown)\n- Amount Due\n- Line Items (description, quantity, unit price, total)\n\nEnsure all dates follow ISO 8601 format.",
    created_at: "2025-01-10T16:00:00Z",
    accuracy: 92.3,
  },
];

// Mock Verified Data
export const mockVerifiedData = {
  doc_1: {
    id: "verified_1",
    project_id: "proj_1",
    document_id: "doc_1",
    data: {
      invoice_number: "INV-2025-001",
      invoice_date: "2025-01-10",
      bill_to: {
        company_name: "Acme Corporation",
        address: "123 Business St",
        city: "San Francisco",
        state: "CA",
        zip_code: "94105",
      },
      amount_due: 1500.0,
      line_items: [
        {
          description: "Professional Services",
          quantity: 10,
          unit_price: 150.0,
          total: 1500.0,
        },
      ],
    },
  },
};

// Mock Extracted Data
export const mockExtractedData = {
  doc_1: {
    id: "extracted_1",
    project_id: "proj_1",
    document_id: "doc_1",
    prompt_id: "prompt_3",
    data: {
      invoice_number: "INV-2025-001",
      invoice_date: "2025-01-10",
      bill_to: {
        company_name: "Acme Corporation",
        address: "123 Business St",
        city: "San Francisco",
        state: "CA",
        zip_code: "94105",
      },
      amount_due: 1500.0,
      line_items: [
        {
          description: "Professional Services",
          quantity: 10,
          unit_price: 150.0,
          total: 1500.0,
        },
      ],
    },
    created_at: "2025-01-10T16:30:00Z",
    highlights: [
      {
        field_path: "invoice_number",
        page: 0,
        rects: [{ x: 100, y: 50, width: 150, height: 20 }],
      },
      {
        field_path: "amount_due",
        page: 0,
        rects: [{ x: 100, y: 400, width: 100, height: 20 }],
      },
    ],
  },
};

// Mock Document Status
export const mockDocumentStatus = [
  {
    id: "doc_1",
    filename: "invoice_001.pdf",
    uploaded_at: "2025-01-10T11:00:00Z",
    raw_text_status: "complete",
    summary_status: "complete",
    verified_data_status: "complete",
    extraction_status: "complete",
    processing_error: null,
    accuracy: 95.5,
    accuracy_matches: 21,
    accuracy_total_fields: 22,
  },
  {
    id: "doc_2",
    filename: "invoice_002.pdf",
    uploaded_at: "2025-01-10T11:15:00Z",
    raw_text_status: "complete",
    summary_status: "complete",
    verified_data_status: "complete",
    extraction_status: "processing",
    processing_error: null,
    accuracy: null,
  },
];

// Mock Analytics Summary
export const mockAnalyticsSummary = {
  total_docs: 15,
  total_fields: 180,
  matched_fields: 165,
  failed_fields: 15,
  overall_accuracy: 91.67,
};

// Mock Top Mismatched Fields
export const mockTopMismatchedFields = [
  {
    field_path: "bill_to.zip_code",
    accuracy: 73.3,
    incorrect: 4,
    common_error: "OCR misreading of similar characters (0 vs O)",
  },
  {
    field_path: "invoice_date",
    accuracy: 80.0,
    incorrect: 3,
    common_error: "Date format inconsistency",
  },
  {
    field_path: "line_items[0].quantity",
    accuracy: 86.7,
    incorrect: 2,
    common_error: "Number extraction from table cells",
  },
];

// Mock Field Details
export const mockFieldDetails = {
  "bill_to.zip_code": {
    field_path: "bill_to.zip_code",
    accuracy: 73.3,
    mismatches: [
      {
        doc_name: "invoice_001.pdf",
        verified: "94105",
        extracted: "9410S",
        error_type: "OCR error",
      },
      {
        doc_name: "invoice_005.pdf",
        verified: "78701",
        extracted: "78701",
        error_type: null,
      },
    ],
  },
};

// Mock Matrix Data
export const mockMatrixData = {
  docs: [
    { id: "doc_1", name: "invoice_001.pdf" },
    { id: "doc_2", name: "invoice_002.pdf" },
    { id: "doc_3", name: "invoice_003.pdf" },
  ],
  fields: [
    { path: "invoice_number" },
    { path: "invoice_date" },
    { path: "bill_to.company_name" },
    { path: "bill_to.zip_code" },
    { path: "amount_due" },
  ],
  data: [
    { doc_id: "doc_1", field_path: "invoice_number", status: "match" },
    { doc_id: "doc_1", field_path: "invoice_date", status: "match" },
    { doc_id: "doc_1", field_path: "bill_to.company_name", status: "match" },
    { doc_id: "doc_1", field_path: "bill_to.zip_code", status: "mismatch" },
    { doc_id: "doc_1", field_path: "amount_due", status: "match" },
    { doc_id: "doc_2", field_path: "invoice_number", status: "match" },
    { doc_id: "doc_2", field_path: "invoice_date", status: "partial" },
    { doc_id: "doc_2", field_path: "bill_to.company_name", status: "match" },
    { doc_id: "doc_2", field_path: "bill_to.zip_code", status: "match" },
    { doc_id: "doc_2", field_path: "amount_due", status: "match" },
  ],
};

// Mock LLM Connectors
export const mockConnectors = [
  {
    id: "llm_openai_gpt4",
    type: "LLM",
    provider: "OpenAI",
    name: "GPT-4 Turbo",
    model: "gpt-4-turbo-preview",
    params: { temperature: 0.7, max_tokens: 4096 },
    created_at: "2025-01-05T10:00:00Z",
  },
  {
    id: "llm_anthropic_claude",
    type: "LLM",
    provider: "Anthropic",
    name: "Claude 3 Sonnet",
    model: "claude-3-sonnet-20240229",
    params: { temperature: 0.7, max_tokens: 4096 },
    created_at: "2025-01-05T10:30:00Z",
  },
  {
    id: "llm_openai_gpt35",
    type: "LLM",
    provider: "OpenAI",
    name: "GPT-3.5 Turbo",
    model: "gpt-3.5-turbo",
    params: { temperature: 0.5, max_tokens: 2048 },
    created_at: "2025-01-05T11:00:00Z",
  },
];

// Mock Notes
export const mockNotes = {
  doc_1: [
    {
      id: "note_1",
      project_id: "proj_1",
      document_id: "doc_1",
      field_path: "bill_to.zip_code",
      note_text: "OCR had trouble with the '5' character, looks like an 'S'",
      created_at: "2025-01-10T17:00:00Z",
      updated_at: "2025-01-10T17:00:00Z",
    },
  ],
};

// Processing status states
export const mockProcessingStatuses = {
  idle: { status: "pending" },
  processing: {
    status: "processing",
    progress: 45,
    message: "Extracting data from documents...",
    current_agent: "Extractor Agent",
  },
  complete: {
    status: "complete",
    progress: 100,
    message: "Processing completed successfully",
  },
  error: {
    status: "error",
    error: "Failed to connect to LLM service",
  },
};
