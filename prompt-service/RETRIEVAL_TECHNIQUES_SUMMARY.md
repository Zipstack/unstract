# New Retrieval Techniques Implementation Summary

## Overview
This document summarizes the implementation of 5 new retrieval techniques for the Unstract prompt service, in addition to the existing Simple and Subquestion retrievers.

## Implemented Retrieval Techniques

### 1. Fusion Retrieval (`fusion`)
- **File**: `src/unstract/prompt_service/core/retrievers/fusion.py`
- **Description**: Generates multiple query variations and combines results using reciprocal rank fusion
- **Key Features**:
  - Uses LLM to generate query variations
  - Applies reciprocal rank fusion scoring
  - Combines results from multiple queries for better coverage

### 2. Recursive Retrieval (`recursive`)
- **File**: `src/unstract/prompt_service/core/retrievers/recursive.py`
- **Description**: Performs initial retrieval then explores related content based on extracted key concepts
- **Key Features**:
  - Extracts key concepts from initial results
  - Performs additional retrievals based on concepts
  - Builds comprehensive context through exploration

### 3. Router Retrieval (`router`)
- **File**: `src/unstract/prompt_service/core/retrievers/router.py`
- **Description**: Analyzes queries and routes them to appropriate retrieval strategies
- **Key Features**:
  - Uses LLM to determine optimal retrieval strategy
  - Supports semantic, keyword, and hybrid approaches
  - Adapts retrieval method based on query type

### 4. Keyword Table Retrieval (`keyword_table`)
- **File**: `src/unstract/prompt_service/core/retrievers/keyword_table.py`
- **Description**: Extracts and matches keywords for efficient retrieval
- **Key Features**:
  - Extracts keywords from queries and documents
  - Calculates keyword match scores
  - Combines keyword matching with vector similarity

### 5. Automerging Retrieval (`automerging`)
- **File**: `src/unstract/prompt_service/core/retrievers/automerging.py`
- **Description**: Automatically merges adjacent or related chunks for better context
- **Key Features**:
  - Groups nodes by document position
  - Merges adjacent chunks based on metadata
  - Provides more comprehensive context

## Integration Points

### 1. Constants
- **File**: `src/unstract/prompt_service/constants.py`
- Added `RetrievalStrategy` enum with all retrieval types

### 2. Retrieval Service
- **File**: `src/unstract/prompt_service/services/retrieval.py`
- Updated to handle all new retrieval types
- Uses a mapping dictionary for dynamic retriever selection
- Maintains backward compatibility with legacy constants

### 3. Controller
- **File**: `src/unstract/prompt_service/controllers/answer_prompt.py`
- Updated validation to accept all new retrieval strategies
- Supports both enum values and legacy constants

### 4. Helper
- **File**: `src/unstract/prompt_service/helpers/retrieval.py`
- Updated to support all new retrieval types

## Usage
To use a new retrieval technique, specify the `retrieval-strategy` parameter in the API request with one of these values:
- `simple` (existing)
- `subquestion` (existing)
- `fusion` (new)
- `recursive` (new)
- `router` (new)
- `keyword_table` (new)
- `automerging` (new)

## Compatibility Notes
- All implementations are compatible with LlamaIndex 0.12.39
- Graceful fallbacks when LLM is not available
- Maintains the same interface as existing retrievers

## Frontend Implementation

### Retrieval Strategy Modal
- **File**: `frontend/src/components/custom-tools/retrieval-strategy-modal/RetrievalStrategyModal.jsx`
- **Features**:
  - Interactive modal showing all retrieval strategies
  - Detailed descriptions and use cases for each strategy
  - Resource impact indicators (token usage, cost)
  - Technical details for each approach
  - Submit button at the top for better UX

### Integration with LLM Profile Form
- **Updated**: `frontend/src/components/custom-tools/add-llm-profile/AddLlmProfile.jsx`
- **Changes**:
  - Added "Configure" button next to retrieval strategy dropdown
  - Opens detailed modal for strategy selection
  - Maintains existing dropdown functionality

### Backend Updates
- **Updated**: `backend/prompt_studio/prompt_studio_core_v2/static/select_choices.json`
- **Added**: All new retrieval strategies to dropdown options

## UI Features Implemented

✅ **Submit button at the top** - Modal includes submit button in header and footer
✅ **Interactive strategy selection** - Radio buttons with detailed descriptions
✅ **Resource impact indicators** - Shows token usage and cost impact
✅ **Technical details** - Provides implementation details for each strategy
✅ **Responsive design** - Works on different screen sizes
✅ **Integration with existing form** - Seamlessly works with current LLM profile setup

## Next Steps
1. Add comprehensive unit tests for each retriever
2. Update API documentation
3. Performance benchmarking and optimization
4. Add analytics/telemetry for strategy usage patterns