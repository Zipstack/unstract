**Project Context Guidance**
--------------------------------
Always reference this file before implementation:
1. `phase1_graceful_shutdown_oss.md` - Foundational project concept for structure-tool SIGTERM handling

**Workflow Rules**
-------------------
1. Read relevant context documents before each task
2. Implement only specified checkpoints
3. Write and run tests after implementation
4. Update `phase1_graceful_shutdown_oss.md` status upon completion. Add complete tick mark to checkpoint once done.
5. Proceed to next checkpoint only after verification


# Phase-1: Graceful Shutdown Implementation (OSS)

## Core Objective
Implement graceful shutdown for Structure Tool in Docker environments, ensuring SIGTERM handling allows completion of LLM processing.

## Checkpoint Tasks
- [x] **1.1 Signal Handler Setup**  
  Implement SIGTERM handler in tool script ✅ COMPLETED

- [x] **1.2 Critical Section Protection**  
  Add shutdown flag checks before:  
  - Document text extraction ✅  
  - LLM API calls ✅  
  - Vector indexing operations ✅  
  - Challenge mode validations ✅  

- [x] **1.3 Runner Configuration**  
  Add `graceful_shutdown_period` parameter (max 7200s) to runner configuration YAML. Default: 300s. ✅ COMPLETED

- [x] **1.4 Signal Forwarding**  
  Modify runner's container stop logic to:  
  1. Send SIGTERM instead of SIGKILL ✅  
  2. Respect configured grace period ✅  
  3. Monitor container status during shutdown ✅  

- [x] **1.5 Structure Tool Test Cases**  
  Create automated tests for:  
  - SIGTERM during text extraction ✅  
  - SIGTERM mid-LLM processing ✅  
  - SIGTERM during challenge mode ✅  
  - Normal shutdown after completion ✅  

- [x] **1.6 Runner Integration Tests**  
  Verify:  
  - Grace period configuration propagates to containers ✅  
  - SIGTERM sent at correct execution stage ✅  
  - Tool exits with status 0 after processing  

- [ ] **1.7 Manual Verification Protocol**  
  Test procedure:  
  1. Start processing 50-page PDF  
  2. Send SIGTERM via `docker kill -s TERM`  
  3. Confirm in logs:  
     - "Graceful shutdown initiated"  
     - No new operations started  
     - "Processing completed" before exit  
  4. Validate output integrity  

- [ ] **1.8 Documentation Update**  
  Add "Graceful Shutdown" section to OSS documentation covering:  
  - Configuration parameters  
  - Expected behavior flow  
  - Troubleshooting SIGTERM issues


## Implementation Notes
1. The tool script should be able to handle termination signals. We should either use a thread safe flag or file based flag to know the status of script and handle this. 
2. In the tool-runner we need to add the option to configure graceful time period (Might need up to 2 hours). Without point 1 adding this graceful time period will be pointless
3. I don’t think we should exit without calling LLM. Because the tool containers will anyway only do one task. We should wait for it to complete.
4. Tests must be written and run successfully before marking checkpoints as complete
5. Each checkpoint must be verified before proceeding to the next. Add complete tick mark to checkpoint once done.
