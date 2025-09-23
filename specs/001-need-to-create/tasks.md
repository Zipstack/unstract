# Tasks: Generic Task Queue Abstraction Library Implementation

**Input**: Design documents from `/home/ghost/Documents/zipstack/unstract-copy/specs/001-need-to-create/`
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, quickstart.md ✓

## Implementation Tasks

### Phase 1: Core Interface
- [ ] **T001** Clean existing over-engineered implementation in `unstract/task-abstraction/src/`
- [ ] **T002** Implement `TaskBackend` abstract interface in `src/task_abstraction/base.py`
- [ ] **T003** Implement `TaskResult` model in `src/task_abstraction/models.py`
- [ ] **T004** Implement backend configuration in `src/task_abstraction/config.py`

### Phase 2: Backend Adapters
- [ ] **T005** Implement `CeleryBackend` in `src/task_abstraction/backends/celery.py`
- [ ] **T006** Implement `HatchetBackend` in `src/task_abstraction/backends/hatchet.py`
- [ ] **T007** Implement `TemporalBackend` in `src/task_abstraction/backends/temporal.py`

### Phase 3: Factory and Loader
- [ ] **T008** Implement backend factory in `src/task_abstraction/factory.py`
- [ ] **T009** Implement `get_backend()` loader function

### Phase 4: Worker Service
- [ ] **T010** Clean task-backend service implementation
- [ ] **T011** Implement simple worker startup in `task-backend/src/task_backend/worker.py`
- [ ] **T012** Add configuration management in `task-backend/src/task_backend/config.py`

### Phase 5: Linear Workflows (v2)
- [ ] **T013** Implement `@workflow` decorator for linear task chaining
- [ ] **T014** Add workflow support to each backend adapter
- [ ] **T015** Implement `backend.submit_workflow()` method

### Phase 6: Testing
- [ ] **T016** Basic unit tests for TaskBackend interface
- [ ] **T017** Integration tests for each backend adapter
- [ ] **T018** End-to-end workflow execution tests

## Task Dependencies
```
T001 → T002-T004 → T005-T007 → T008-T009 → T010-T012 → T013-T015 → T016-T018
```

## Success Criteria
- Simple, clean "SQLAlchemy for task queues" interface
- All three backends (Celery, Hatchet, Temporal) working
- Configuration-based backend switching
- Worker service starts appropriate backend workers
- Linear workflow support (v2)
- No over-engineering or complex orchestration features