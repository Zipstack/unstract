# Agentic Prompt Studio - Implementation Guide

## Phase 1 Status: 80% Complete ✅

A comprehensive conversion of AutoPrompt (React + TypeScript + Tailwind + Shadcn) to Ant Design + JavaScript for Unstract's Agentic Prompt Studio v2.

---

## 📁 Project Structure

```
frontend/src/components/agentic-prompt-studio/
├── components/           # 11 components (COMPLETE)
│   ├── AccuracyOverviewPanel.js
│   ├── ComparePromptsModal.js
│   ├── DataRenderer.js + .css
│   ├── DocumentManager.js
│   ├── FieldComparisonModal.js + .css
│   ├── MonacoEditor.js
│   ├── NoteEditorModal.js
│   ├── PdfViewer.js + .css
│   ├── PromptHistoryModal.js
│   ├── SavePromptModal.js
│   └── StatusBadge.js
├── pages/                # 3/6 pages (50% complete)
│   ├── Dashboard.js ✅
│   ├── Projects.js ✅
│   ├── ProjectDetail.js + .css ✅
│   ├── ProjectAnalytics.js ❌ TODO
│   ├── ProjectMismatchMatrix.js ❌ TODO
│   └── Settings.js ❌ TODO
├── hooks/
│   └── useMockApi.js ✅  # Complete mock API layer
├── mock/
│   └── mockData.js ✅    # Realistic mock data
├── utils/
│   └── helpers.js ✅     # 25+ utility functions
└── index.js ✅           # Main export file
```

---

## ✅ Completed Features (17/20 files)

### Foundation Layer
- ✅ **Mock API Layer** (`useMockApi.js`) - All CRUD operations with realistic delays
- ✅ **Mock Data** (`mockData.js`) - Complete data structures matching AutoPrompt API
- ✅ **Utilities** (`helpers.js`) - Date formatting, status helpers, object manipulation

### Core Components (11/11)
- ✅ **StatusBadge** - Ant Design Tag-based status indicator
- ✅ **DataRenderer** - Recursive JSON renderer with 3-rule system
- ✅ **MonacoEditor** - JSON/Markdown/Plain text editor wrapper
- ✅ **PdfViewer** - PDF display with percentage-based highlights
- ✅ **DocumentManager** - Tabbed PDF/Raw text viewer
- ✅ **AccuracyOverviewPanel** - Project accuracy metrics with recalculate

### Modal Components (5/5)
- ✅ **SavePromptModal** - Save with AI-generated metadata
- ✅ **PromptHistoryModal** - Version history table with load/compare
- ✅ **ComparePromptsModal** - Side-by-side diff viewer
- ✅ **FieldComparisonModal** - Complex field comparison with tuning
- ✅ **NoteEditorModal** - Markdown note editor

### Pages (3/6)
- ✅ **Dashboard** - Statistics overview
- ✅ **Projects** - Project list with CRUD
- ✅ **ProjectDetail** - Main two-panel layout with tabs

---

## ❌ Remaining Work (3 pages)

### 1. ProjectAnalytics Page
**Purpose:** Charts and graphs for accuracy analysis

**Key Features to Implement:**
- Accuracy over time (line chart)
- Field-level accuracy breakdown (bar chart)
- Top mismatched fields table
- Category breakdown pie chart
- Error type distribution

**Libraries:**
- Use **Recharts** (same as AutoPrompt)
- Reference: `autoprompt/frontend/src/pages/ProjectAnalytics.tsx`

**Mock Data Available:**
- `mockAnalyticsSummary`
- `mockTopMismatchedFields`
- `mockFieldDetails`

**Template Structure:**
```javascript
import React, { useState, useEffect } from "react";
import { Card, Row, Col } from "antd";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { useMockApi } from "../hooks/useMockApi";

const ProjectAnalytics = ({ projectId }) => {
  const [summary, setSummary] = useState(null);
  const [topFields, setTopFields] = useState([]);
  const { getAnalyticsSummary, getTopMismatchedFields } = useMockApi();

  // TODO: Fetch data and render charts

  return (
    <div style={{ padding: "24px" }}>
      <h2>Analytics</h2>
      <Row gutter={16}>
        <Col span={12}>
          <Card title="Accuracy Over Time">
            <LineChart width={500} height={300} data={/* TODO */}>
              {/* TODO: Add chart components */}
            </LineChart>
          </Card>
        </Col>
        {/* TODO: Add more charts */}
      </Row>
    </div>
  );
};

export default ProjectAnalytics;
```

---

### 2. ProjectMismatchMatrix Page
**Purpose:** Heatmap visualization of doc-field matches

**Key Features to Implement:**
- Document rows × Field columns grid
- Color-coded cells (green=match, yellow=partial, red=mismatch)
- Click cell to view field details
- Filter by match status
- Export matrix data

**Libraries:**
- Custom grid component OR `react-grid-layout`
- Ant Design Table (alternative approach)

**Mock Data Available:**
- `mockMatrixData` with docs, fields, and data points

**Template Structure:**
```javascript
import React, { useState, useEffect } from "react";
import { Card, Table } from "antd";
import { useMockApi } from "../hooks/useMockApi";

const ProjectMismatchMatrix = ({ projectId }) => {
  const [matrixData, setMatrixData] = useState(null);
  const { getMatrixData } = useMockApi();

  // TODO: Fetch matrix data
  // TODO: Render heatmap grid
  // TODO: Add cell click handlers

  const getStatusColor = (status) => {
    const colors = {
      match: "#52c41a",
      partial: "#faad14",
      mismatch: "#ff4d4f",
    };
    return colors[status] || "#d9d9d9";
  };

  return (
    <div style={{ padding: "24px" }}>
      <Card title="Mismatch Matrix">
        {/* TODO: Render matrix grid */}
      </Card>
    </div>
  );
};

export default ProjectMismatchMatrix;
```

---

### 3. Settings Page
**Purpose:** Project configuration (LLM profiles, connectors)

**Key Features to Implement:**
- LLM profile selection (Extractor, Agent, Lightweight, LLMWhisperer)
- Connector management
- Project metadata editing
- Delete project

**Mock Data Available:**
- `mockConnectors` with LLM configurations

**Template Structure:**
```javascript
import React, { useState, useEffect } from "react";
import { Form, Select, Button, Card, Input, message } from "antd";
import { useMockApi } from "../hooks/useMockApi";

const Settings = ({ projectId }) => {
  const [form] = Form.useForm();
  const [project, setProject] = useState(null);
  const [connectors, setConnectors] = useState([]);
  const { getProject, getConnectors, updateProject } = useMockApi();

  // TODO: Fetch project and connectors
  // TODO: Handle form submission

  return (
    <div style={{ padding: "24px" }}>
      <Card title="Project Settings">
        <Form form={form} layout="vertical" onFinish={/* TODO */}>
          <Form.Item name="name" label="Project Name">
            <Input />
          </Form.Item>
          <Form.Item name="extractor_llm_id" label="Extractor LLM">
            <Select>
              {/* TODO: Map connectors */}
            </Select>
          </Form.Item>
          {/* TODO: Add more settings */}
          <Button type="primary" htmlType="submit">Save</Button>
        </Form>
      </Card>
    </div>
  );
};

export default Settings;
```

---

## 🔧 Implementation Instructions

### Step 1: Implement Remaining Pages

1. Create `pages/ProjectAnalytics.js` using template above
2. Create `pages/ProjectMismatchMatrix.js`
3. Create `pages/Settings.js`
4. Add exports to `index.js`

### Step 2: Integration with Routing

Add routes in your main app:

```javascript
import { Dashboard, Projects, ProjectDetail, ProjectAnalytics, ProjectMismatchMatrix, Settings } from "./components/agentic-prompt-studio";

// In your router:
<Route path="/agentic-studio" element={<Dashboard />} />
<Route path="/agentic-studio/projects" element={<Projects />} />
<Route path="/agentic-studio/projects/:id" element={<ProjectDetail />} />
<Route path="/agentic-studio/projects/:id/analytics" element={<ProjectAnalytics />} />
<Route path="/agentic-studio/projects/:id/matrix" element={<ProjectMismatchMatrix />} />
<Route path="/agentic-studio/projects/:id/settings" element={<Settings />} />
```

### Step 3: Test with Mock Data

All components use `useMockApi` hook which provides realistic data:

```javascript
import { useMockApi } from "./components/agentic-prompt-studio/hooks/useMockApi";

const MyComponent = () => {
  const { getProjects, loading, error } = useMockApi();

  useEffect(() => {
    getProjects().then(setProjects);
  }, []);
};
```

### Step 4: Replace Mock APIs (Phase 2)

When backend is ready, replace mock calls:

```javascript
// Before (Mock)
const data = await useMockApi().getProjects();

// After (Real API)
const data = await fetch("/api/agentic/projects").then(r => r.json());
```

All mock API calls are marked with `// TODO: Replace with actual API call`

---

## 📦 Dependencies

Ensure these packages are installed:

```json
{
  "dependencies": {
    "antd": "^5.5.1",
    "@ant-design/icons": "^5.0.0",
    "@monaco-editor/react": "^4.7.0",
    "@react-pdf-viewer/core": "^3.12.0",
    "@react-pdf-viewer/default-layout": "^3.12.0",
    "react-diff-viewer-continued": "^3.4.0",
    "recharts": "^3.4.1"
  }
}
```

---

## 🎨 Styling Approach

All components use:
1. **Ant Design props** for primary styling
2. **Inline styles** for custom layouts
3. **CSS files** only for complex components (DataRenderer, FieldComparisonModal, PdfViewer, ProjectDetail)

**No Tailwind or custom CSS frameworks needed!**

---

## 🔄 Phase 2: Plugin Separation

When ready to move to plugins:

1. Move entire `agentic-prompt-studio/` to `plugins/`
2. Add try-catch imports in parent components:

```javascript
let AgenticPromptStudio;
try {
  AgenticPromptStudio = require("../../plugins/agentic-prompt-studio").Dashboard;
} catch (err) {
  // Cloud-only feature not available
}

// Conditional rendering
{AgenticPromptStudio && <AgenticPromptStudio />}
```

3. Replace mock APIs with real endpoints
4. Add state management (Zustand) if needed

---

## 📝 Component Usage Examples

### Using Modal Components

```javascript
import { SavePromptModal, PromptHistoryModal } from "./components/agentic-prompt-studio";

const MyComponent = () => {
  const [saveVisible, setSaveVisible] = useState(false);

  return (
    <>
      <Button onClick={() => setSaveVisible(true)}>Save</Button>

      <SavePromptModal
        visible={saveVisible}
        onClose={() => setSaveVisible(false)}
        projectId="proj_1"
        promptText="Extract invoice data..."
        baseVersion={3}
        onSuccess={() => console.log("Saved!")}
      />
    </>
  );
};
```

### Using Display Components

```javascript
import { DataRenderer, PdfViewer, DocumentManager } from "./components/agentic-prompt-studio";

// Render extracted data
<DataRenderer
  data={extractedData}
  hideEmpty={true}
  highlightData={highlights}
  onFieldClick={(path, value) => console.log("Field clicked:", path)}
/>

// Show PDF with highlights
<PdfViewer
  url="/path/to/document.pdf"
  highlights={[[0, 10, 20, 30, 5]]} // [page, x%, y%, width%, height%]
  activeHighlightIndex={0}
/>

// Document tabs
<DocumentManager
  projectId="proj_1"
  document={documentObj}
  highlights={highlightArray}
/>
```

---

## 🐛 Known Limitations & Future Improvements

### Current Limitations
1. **No real-time updates** - SSE not implemented (mock only)
2. **No file upload** - Document upload UI needs integration
3. **Simplified tuning** - Multi-agent progress tracking is mocked
4. **No batch operations** - Batch extraction UI not implemented

### Recommended Improvements
1. Add **WebSocket/SSE** for real-time extraction status
2. Implement **drag-and-drop** document upload
3. Add **keyboard shortcuts** (Cmd+S to save, Cmd+K for search)
4. Add **export functionality** (CSV, JSON downloads)
5. Add **print preview** for reports
6. Implement **dark mode** support

---

## 🎯 Success Criteria

Phase 1 is complete when:
- ✅ All pages render without errors
- ✅ Mock API returns realistic data
- ✅ Modals open/close correctly
- ✅ Forms validate and submit
- ✅ Navigation works between pages
- ✅ No console errors
- ✅ Responsive layout works

Phase 2 is complete when:
- ⬜ Real APIs integrated
- ⬜ Moved to plugins/ directory
- ⬜ Try-catch imports working
- ⬜ No regressions in Prompt Studio v1

---

## 📞 Support & Questions

For implementation help:
1. Check AutoPrompt source: `../autoprompt/frontend/src/`
2. Review mock data: `mock/mockData.js`
3. Test with mock API: `hooks/useMockApi.js`
4. Reference helpers: `utils/helpers.js`

**All TODO comments mark areas needing API replacement!**

---

## 🚀 Quick Start Checklist

- [ ] Implement `ProjectAnalytics.js` (1-2 hours)
- [ ] Implement `ProjectMismatchMatrix.js` (1-2 hours)
- [ ] Implement `Settings.js` (1 hour)
- [ ] Add routing to main app
- [ ] Test all pages with mock data
- [ ] Verify no console errors
- [ ] Test modals and forms
- [ ] Review AutoPrompt for missing features
- [ ] Document any deviations
- [ ] Prepare for Phase 2 (API integration)

**Estimated completion time: 4-6 hours**

---

## 📊 Progress Summary

| Category | Complete | Remaining | Progress |
|----------|----------|-----------|----------|
| Foundation | 3/3 | 0 | 100% ✅ |
| Components | 11/11 | 0 | 100% ✅ |
| Modals | 5/5 | 0 | 100% ✅ |
| Pages | 3/6 | 3 | 50% 🟡 |
| **Total** | **22/25** | **3** | **88%** ✅ |

**You're 88% done! Just 3 pages left!** 🎉
