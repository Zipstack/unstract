# Unstract Tool Sidecar

A companion container that runs alongside main tool containers in Unstract for log processing, monitoring, and real-time streaming.

## Key Features
- Log processing and real-time streaming to Redis
- Monitors tool container output and completion signals
- Runs in same pod as tool container (For K8s)
- Handles organization and execution-specific logging
- Part of containerized tool execution infrastructure

## Architecture
The sidecar container operates as part of Unstract's containerized infrastructure, working in tandem with the main tool containers to provide real-time monitoring and log management capabilities. It uses Redis for efficient log publishing and streaming.
