import { useState, useCallback } from "react";

import {
  mockProjects,
  mockDocuments,
  mockSchema,
  mockPrompts,
  mockVerifiedData,
  mockExtractedData,
  mockDocumentStatus,
  mockAnalyticsSummary,
  mockTopMismatchedFields,
  mockFieldDetails,
  mockMatrixData,
  mockConnectors,
  mockNotes,
  mockProcessingStatuses,
} from "../mock/mockData";

// Helper to simulate network delay
const delay = (ms) => {
  const randomPart = Math.random() * 1000;
  const randomDelay = 500 + randomPart;
  return new Promise((resolve) => setTimeout(resolve, ms || randomDelay));
};

export const useMockApi = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Projects API
  const getProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await delay(600);
      return mockProjects;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getProject = useCallback(async (projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      const project = mockProjects.find((p) => p.id === projectId);
      if (!project) throw new Error("Project not found");
      return project;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const createProject = useCallback(async (data) => {
    setLoading(true);
    setError(null);
    try {
      await delay(800);
      const newProject = {
        id: `proj_${Date.now()}`,
        name: data.name,
        description: data.description || null,
        created_at: new Date().toISOString(),
        extractor_llm_id: null,
        agent_llm_id: null,
        llmwhisperer_id: null,
        lightweight_llm_id: null,
      };
      return newProject;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteProject = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(600);
      return { message: "Project deleted successfully" };
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Documents API
  const getDocuments = useCallback(async (projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(500);
      // Fallback to proj_1 documents if projectId doesn't match
      return mockDocuments[projectId] || mockDocuments["proj_1"] || [];
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getDocument = useCallback(async (projectId, documentId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      const docs = mockDocuments[projectId] || [];
      const doc = docs.find((d) => d.id === documentId);
      if (!doc) throw new Error("Document not found");
      return doc;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const uploadDocument = useCallback(async (projectId, file) => {
    setLoading(true);
    setError(null);
    try {
      await delay(1500); // Longer delay for upload
      const newDoc = {
        id: `doc_${Date.now()}`,
        project_id: projectId,
        original_filename: file.name,
        stored_path: `/uploads/${file.name}`,
        size_bytes: file.size,
        pages: null,
        uploaded_at: new Date().toISOString(),
        raw_text: null,
      };
      return newDoc;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Schema API
  const getSchema = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(500);
      return mockSchema;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Prompts API
  const getPrompts = useCallback(async (projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(500);
      return mockPrompts.filter((p) => p.project_id === projectId);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getLatestPrompt = useCallback(async (projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      let prompts = mockPrompts.filter((p) => p.project_id === projectId);
      // Fallback to proj_1 prompts if projectId doesn't match
      if (prompts.length === 0) {
        prompts = mockPrompts.filter((p) => p.project_id === "proj_1");
      }
      return prompts[prompts.length - 1] || null;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const createPrompt = useCallback(async (projectId, data) => {
    setLoading(true);
    setError(null);
    try {
      await delay(800);
      const existingPrompts = mockPrompts.filter(
        (p) => p.project_id === projectId
      );
      const newVersion = existingPrompts.length + 1;
      const newPrompt = {
        id: `prompt_${Date.now()}`,
        project_id: projectId,
        version: newVersion,
        short_desc: data.short_desc,
        long_desc: data.long_desc,
        prompt_text: data.prompt_text,
        created_at: new Date().toISOString(),
        accuracy: null,
      };
      return newPrompt;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const generateMetadata = useCallback(async (_promptText) => {
    setLoading(true);
    setError(null);
    try {
      await delay(1200); // Longer delay for AI generation
      return {
        short_desc: "AI-generated summary",
        long_desc: "AI-generated detailed description of the changes made",
        generated: true,
      };
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Extraction API
  const getVerifiedData = useCallback(async (projectId, documentId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      // Fallback to doc_1 verified data if documentId doesn't match
      return mockVerifiedData[documentId] || mockVerifiedData["doc_1"] || null;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getExtractedData = useCallback(async (projectId, documentId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      // Fallback to doc_1 extracted data if documentId doesn't match
      return (
        mockExtractedData[documentId] || mockExtractedData["doc_1"] || null
      );
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const runExtraction = useCallback(
    async (_projectId, _documentId, _promptId) => {
      setLoading(true);
      setError(null);
      try {
        await delay(2000); // Longer delay for extraction
        return {
          job_id: `job_${Date.now()}`,
          status: "processing",
          message: "Extraction started",
        };
      } catch (err) {
        setError(err.message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Document Status API
  const getDocumentStatus = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(500);
      return mockDocumentStatus;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Analytics API
  const getAnalyticsSummary = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(600);
      return mockAnalyticsSummary;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getTopMismatchedFields = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(600);
      return mockTopMismatchedFields;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getFieldDetails = useCallback(async (projectId, fieldPath) => {
    setLoading(true);
    setError(null);
    try {
      await delay(500);
      return mockFieldDetails[fieldPath] || null;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const getMatrixData = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(700);
      return mockMatrixData;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Connectors API
  const getConnectors = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      return mockConnectors;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Notes API
  const getNotes = useCallback(async (projectId, documentId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(400);
      return mockNotes[documentId] || [];
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const createNote = useCallback(async (projectId, documentId, data) => {
    setLoading(true);
    setError(null);
    try {
      await delay(600);
      const newNote = {
        id: `note_${Date.now()}`,
        project_id: projectId,
        document_id: documentId,
        field_path: data.field_path,
        note_text: data.note_text,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      return newNote;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateNote = useCallback(async (noteId, data) => {
    setLoading(true);
    setError(null);
    try {
      await delay(600);
      return {
        ...data,
        id: noteId,
        updated_at: new Date().toISOString(),
      };
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteNote = useCallback(async (_noteId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(500);
      return { message: "Note deleted successfully" };
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Processing API
  const generatePromptWithDeps = useCallback(async (_projectId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(1000);
      return {
        status: "processing",
        job_id: `job_${Date.now()}`,
        message: "Prompt generation started",
      };
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const tunePrompt = useCallback(
    async (_projectId, fieldPath, _strategy = "multiagent") => {
      setLoading(true);
      setError(null);
      try {
        await delay(1000);
        return {
          status: "processing",
          job_id: `job_${Date.now()}`,
          message: `Tuning prompt for field: ${fieldPath}`,
        };
      } catch (err) {
        setError(err.message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const getProcessingStatus = useCallback(async (_jobId) => {
    setLoading(true);
    setError(null);
    try {
      await delay(300);
      // Simulate progressive status
      return mockProcessingStatuses.processing;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    loading,
    error,
    // Projects
    getProjects,
    getProject,
    createProject,
    deleteProject,
    // Documents
    getDocuments,
    getDocument,
    uploadDocument,
    // Schema
    getSchema,
    // Prompts
    getPrompts,
    getLatestPrompt,
    createPrompt,
    generateMetadata,
    // Extraction
    getVerifiedData,
    getExtractedData,
    runExtraction,
    // Status
    getDocumentStatus,
    // Analytics
    getAnalyticsSummary,
    getTopMismatchedFields,
    getFieldDetails,
    getMatrixData,
    // Connectors
    getConnectors,
    // Notes
    getNotes,
    createNote,
    updateNote,
    deleteNote,
    // Processing
    generatePromptWithDeps,
    tunePrompt,
    getProcessingStatus,
  };
};
