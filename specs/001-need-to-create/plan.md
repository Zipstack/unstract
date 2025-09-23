# Implementation Plan: Generic Task Queue Abstraction Library

**Branch**: `001-task-abstraction-layer` | **Date**: 2025-09-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/home/ghost/Documents/zipstack/unstract-copy/specs/001-need-to-create/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → Loaded successfully from spec.md
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type: single (library package in unstract/task-abstraction)
   → Set Structure Decision: Library-only approach (existing package)
3. Evaluate Constitution Check section below
   → Constitution template found but not configured for project
   → Using standard constitutional principles for library development
   → Update Progress Tracking: Initial Constitution Check
4. Execute Phase 0 → research.md
   → Research backend integration patterns, migration strategies
5. Execute Phase 1 → contracts, data-model.md, quickstart.md, CLAUDE.md
6. Re-evaluate Constitution Check section
   → Update Progress Tracking: Post-Design Constitution Check
7. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
8. STOP - Ready for /tasks command
```

## Summary
Implement a generic task queue abstraction library that provides a unified interface for task execution across multiple backends (Celery, Hatchet, Temporal), enabling backend switching through configuration without code changes. Think: "SQLAlchemy for task queues".

## Technical Context
**Language/Version**: Python 3.12+
**Primary Dependencies**: Celery, hatchet-sdk, temporalio, pydantic
**Storage**: Backend-specific (Redis for Celery, etc.)
**Testing**: pytest, integration tests with real backends
**Target Platform**: Any Python environment
**Project Type**: Generic library package (task-abstraction) + worker service (task-backend)
**Performance Goals**: Minimal overhead over native backend performance
**Constraints**: Simple, clean interface similar to SQLAlchemy's database abstraction
**Scale/Scope**: Generic abstraction usable by any Python project needing task queue portability

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Simplicity**:
- Projects: 1 (task-abstraction library in unstract/ directory)
- Using framework directly? Yes (Celery, Hatchet, Temporal APIs directly)
- Single data model? Yes (unified workflow/task definitions with backend adapters)
- Avoiding patterns? Yes (no unnecessary Repository pattern, direct backend integration)

**Architecture**:
- EVERY feature as library? Yes (generic task abstraction library)
- Libraries listed: unstract.task_abstraction (unified workflow interface)
- CLI per library: Worker startup CLI, workflow registration CLI, status CLI
- Library docs: llms.txt format planned for API documentation

**Testing (NON-NEGOTIABLE)**:
- RED-GREEN-Refactor cycle enforced? Yes (tests written first for each backend)
- Git commits show tests before implementation? Required in development
- Order: Contract→Integration→E2E→Unit strictly followed? Yes
- Real dependencies used? Yes (actual Celery/Hatchet/Temporal backends)
- Integration tests for: Backend adapters, workflow registration, migration scenarios
- FORBIDDEN: Implementation before test, skipping RED phase

**Observability**:
- Structured logging included? Yes (consistent across all backends)
- Frontend logs → backend? N/A (backend library only)
- Error context sufficient? Yes (backend-specific error handling with unified interface)

**Versioning**:
- Version number assigned? Yes (0.1.0 → 0.2.0 for this feature)
- BUILD increments on every change? Yes
- Breaking changes handled? Yes (feature flag migration, backward compatibility)

## Project Structure

### Documentation (this feature)
```
specs/001-need-to-create/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Library structure (existing package being extended)
unstract/task-abstraction/
├── src/unstract/task_abstraction/
│   ├── base/            # Base classes (existing)
│   ├── backends/        # Backend adapters (extend existing)
│   ├── models.py        # Data models (extend existing)
│   ├── config.py        # Configuration (extend existing)
│   ├── factory.py       # Client factory (extend existing)
│   └── registry.py      # Task registry (extend existing)
├── tests/
│   ├── contract/        # Backend contract tests
│   ├── integration/     # Multi-backend integration tests
│   └── unit/            # Unit tests
└── examples/            # Migration examples
    ├── backend_django_integration.py
    └── prompt_service_integration.py
```

**Structure Decision**: Library extension approach (existing unstract/task-abstraction package)

## Phase 0: Outline & Research

1. **Extract unknowns from Technical Context**:
   - Backend integration patterns for Celery/Hatchet/Temporal
   - Feature flag implementation strategy for gradual migration
   - Static task registration mechanisms across backends
   - Worker resource profile management with abstraction layer
   - Service replacement strategies (Runner/Structure Tool/Prompt Service)

2. **Generate and dispatch research agents**:
   ```
   Task: "Research Hatchet SDK integration patterns for workflow definitions"
   Task: "Research Temporal workflow patterns compatible with existing task structure"
   Task: "Research feature flag strategies for service migration without downtime"
   Task: "Research static task registration patterns for multi-backend support"
   Task: "Research backward compatibility patterns for existing Celery workflows"
   ```

3. **Consolidate findings** in `research.md`:
   - Backend adapter pattern decisions
   - Migration strategy rationale
   - Task registry implementation approach
   - Feature flag integration method

**Output**: research.md with all technical approaches resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - TaskAbstractionLayer, WorkflowDefinition, TaskDefinition
   - BackendAdapter interface and implementations
   - TaskRegistry, WorkerClient, FeatureFlag models
   - ExecutionContext with backend-agnostic state management

2. **Generate API contracts** from functional requirements:
   - Workflow registration API (static at startup)
   - Task execution API (unified across backends)
   - Status monitoring API (consistent interface)
   - Migration control API (feature flag management)
   - Output contracts to `/contracts/`

3. **Generate contract tests** from contracts:
   - Backend adapter contract tests (must fail initially)
   - Workflow registration tests across backends
   - Feature flag migration scenario tests
   - Cross-backend compatibility tests

4. **Extract test scenarios** from user stories:
   - Document workflow execution through abstraction layer
   - Service migration with feature flags enabled
   - Worker startup with task registration
   - Error handling consistency across backends

5. **Update CLAUDE.md incrementally**:
   - Add task abstraction library context
   - Include backend-specific patterns and constraints
   - Document migration approach and feature flag usage
   - Keep existing platform context, add new abstractions

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, CLAUDE.md

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `/templates/tasks-template.md` as base
- Generate tasks from backend adapters (Celery, Hatchet, Temporal)
- Each backend → adapter implementation task [P]
- Each contract → contract test task [P]
- Migration scenarios → integration test tasks
- Feature flag implementation → configuration tasks
- Documentation tasks for each backend

**Ordering Strategy**:
- TDD order: Contract tests → Backend adapters → Integration tests
- Backend independence: Celery, Hatchet adapters in parallel [P]
- Migration order: Feature flags → Legacy service replacement
- Registry implementation before worker client integration

**Estimated Output**: 30-35 numbered, ordered tasks in tasks.md focusing on backend adapters, migration strategy, and testing

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (backend adapters, feature flags, migration tools)  
**Phase 5**: Validation (multi-backend tests, migration scenarios, performance validation)

## Complexity Tracking
*No constitutional violations identified - library-first approach with direct framework usage*

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)  
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

**Artifacts Generated**:
- [x] research.md - Backend integration patterns and migration strategies
- [x] data-model.md - Enhanced entities with multi-backend support
- [x] contracts/backend_adapter_contract.py - Backend compatibility contract tests
- [x] contracts/migration_api_contract.py - Migration scenario contract tests
- [x] quickstart.md - Complete migration guide with examples
- [x] CLAUDE.md - Updated with task abstraction context

---
*Based on Constitutional Principles - Library-first, Test-driven, Backend-agnostic*