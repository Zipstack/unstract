**Project Context Guidance**
--------------------------------
Always reference these core documents before implementation:
1. 1. `phase1_graceful_shutdown_oss.md` - Foundational project concept for structure-tool SIGTERM handling

**Workflow Rules**
-------------------
1. Read relevant context documents before each task
2. Implement only specified checkpoints
3. Write and run tests after implementation
4. Update `phase2_graceful_shutdown_k8s.md` status upon completion. Add complete tick mark to checkpoint once done.
5. Proceed to next checkpoint only after verification

# Phase-2: Graceful Shutdown Implementation (Kubernetes)

## Core Objective
Adapt graceful shutdown for Kubernetes environments while maintaining consistent SIGTERM handling in the Structure Tool.

## Critical Implementation Note
The Structure Tool's core SIGTERM handling logic remains identical to the OSS implementation from Phase-1. Kubernetes only changes how signals are delivered and managed at the cluster level.

## Checkpoint Tasks
- [x] **2.1 Verify SIGTERM Handling (Same as Phase-1)**  
  Confirm Structure Tool includes:  
  - Global `shutdown_requested` flag ✅  
  - SIGTERM handler that sets the flag ✅  
  - Flag checks before all critical operations ✅  
  - Completion logic for current LLM processing ✅  

- [x] **2.2 PreStop Hook Configuration**  
  Implement `preStop` hook in deployment manifest: ✅  
  ```yaml
  lifecycle:
    preStop:
      exec:
        command: ["/bin/sh", "-c", "kill -TERM 1"]

- [x] **2.3 Kubernetes Integration Tests**  
  Verify graceful shutdown in K8s environment ✅

- [x] **2.4 Documentation Update**  
  Add Kubernetes-specific graceful shutdown documentation ✅


## Implementation Notes
- Structure Tool core SIGTERM handling logic remains identical between OSS and K8s. 
- Kubernetes only changes how signals are delivered at cluster level
- Tests must be written and run successfully before marking checkpoints as complete
- Each checkpoint must be verified before proceeding to the next. Add complete tick mark to checkpoint once done.

## Kubernetes Graceful Shutdown Implementation Details

### Architecture Overview
The Kubernetes graceful shutdown implementation builds upon the OSS Docker implementation from Phase-1, maintaining the same SIGTERM handling logic in the Structure Tool while adapting the signal delivery mechanism for Kubernetes environments.

### Key Components

#### 1. Structure Tool SIGTERM Handling (Unchanged from Phase-1)
- **Global shutdown flag**: `shutdown_requested = threading.Event()`
- **Signal handler**: `signal.signal(signal.SIGTERM, signal_handler)`
- **Shutdown checks**: Inserted before all critical operations:
  - Document text extraction
  - LLM API calls (prompt answering, summarization)
  - Vector indexing
  - Challenge mode validations

#### 2. Kubernetes PreStop Hook Configuration
Implemented in `/unstract-cloud/runner/src/unstract/runner/clients/k8s.py`:

```python
"lifecycle": {
    "preStop": {
        "exec": {
            "command": ["/bin/sh", "-c", "kill -TERM 1"]
        }
    }
}
```

#### 3. Pod Termination Grace Period
Configured in pod manifest:
- **Default**: 7200 seconds (2 hours)
- **Environment variable**: `TOOLS_K8S_TERMINATION_GRACE_PERIOD`
- **Range**: 30 seconds to 7200 seconds

### Signal Flow in Kubernetes

1. **Kubernetes Shutdown Initiation**:
   - Pod receives termination signal from Kubernetes API
   - `terminationGracePeriodSeconds` timer starts

2. **PreStop Hook Execution**:
   - Kubernetes executes preStop hook: `kill -TERM 1`
   - Sends SIGTERM to PID 1 (main process) in container

3. **Structure Tool Signal Handling**:
   - SIGTERM handler sets `shutdown_requested.set()`
   - All critical operations check `shutdown_requested.is_set()`
   - Current LLM processing completes gracefully
   - Tool exits with status 0

4. **Kubernetes Cleanup**:
   - If process exits within grace period: clean shutdown
   - If grace period expires: SIGKILL sent (force termination)
   - Pod transitions to "Succeeded" or "Failed" state

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_K8S_TERMINATION_GRACE_PERIOD` | `7200` | Pod termination grace period (seconds) |
| `GRACEFUL_SHUTDOWN_PERIOD` | `300` | Structure Tool internal timeout (seconds) |
| `CONTAINER_CLIENT_PATH` | `unstract.runner.clients.k8s` | Kubernetes client selection |

### Testing

#### Integration Tests
Located in `/unstract-cloud/runner/tests/test_k8s_graceful_shutdown.py`:
- PreStop hook configuration validation
- Termination grace period handling
- Pod manifest graceful shutdown config
- Signal forwarding sequence verification
- Environment variable propagation
- Kubernetes vs Docker consistency
- Pod cleanup after graceful shutdown

#### Test Coverage
- ✅ PreStop hook YAML configuration
- ✅ SIGTERM signal forwarding
- ✅ Grace period environment variable handling
- ✅ Pod lifecycle state transitions
- ✅ Cross-platform consistency (K8s vs Docker)

### Deployment Configuration

#### Runner Deployment
The runner deployment in `/unstract-cloud/charts/unstract-platform/templates/runner/deployment.yaml` already includes:
- `terminationGracePeriodSeconds: 7200`
- Service account with pod management permissions
- Environment variable `CONTAINER_CLIENT_PATH: "unstract.runner.clients.k8s"`

#### Tool Pod Configuration
Dynamically generated pods include:
- PreStop hook with SIGTERM forwarding
- Configurable termination grace period
- Process namespace sharing for signal delivery
- Resource limits and requests
- Volume mounts for log collection

### Monitoring and Observability

#### Graceful Shutdown Metrics
- Pod termination duration
- Signal delivery success rate
- Grace period utilization
- Force termination incidents

#### Logging
- Structure Tool logs shutdown initiation
- Kubernetes events track pod lifecycle
- Runner logs container creation/cleanup
- OpenTelemetry traces span graceful shutdown

### Troubleshooting

#### Common Issues
1. **Grace period too short**: Increase `TOOLS_K8S_TERMINATION_GRACE_PERIOD`
2. **PreStop hook failure**: Check container shell availability
3. **Signal not received**: Verify process namespace sharing
4. **Force termination**: Monitor grace period utilization

#### Debug Commands
```bash
# Check pod events
kubectl describe pod <pod-name>

# View pod logs
kubectl logs <pod-name> -c unstract-tool

# Monitor pod termination
kubectl get pods -w
```

### Differences from Docker Implementation

| Aspect | Docker | Kubernetes |
|--------|--------|------------|
| Signal delivery | Direct `docker kill -s SIGTERM` | PreStop hook `kill -TERM 1` |
| Grace period | `GRACEFUL_SHUTDOWN_PERIOD` (300s) | `terminationGracePeriodSeconds` (7200s) |
| Container lifecycle | Docker daemon manages | Kubernetes scheduler manages |
| Process isolation | Docker container | Kubernetes pod with shared namespace |
| Cleanup | `docker rm` | Pod deletion by Kubernetes |

### Security Considerations

- PreStop hook requires shell access in container
- Signal delivery requires appropriate process permissions
- Service account needs pod management RBAC permissions
- Grace period should balance resource usage vs. completion time

### Performance Impact

- PreStop hook adds minimal overhead (~1ms)
- Grace period reserves pod resources during shutdown
- Shared process namespace enables efficient signal delivery
- Graceful shutdown reduces data loss and improves reliability
