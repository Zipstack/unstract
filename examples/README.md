# Task Abstraction Examples

This directory contains examples demonstrating how to use the task abstraction library across different backends and use cases.

## Quick Start Examples

### Basic Usage
- [`basic_celery.py`](basic_celery.py) - Simple Celery backend usage
- [`basic_hatchet.py`](basic_hatchet.py) - Simple Hatchet backend usage
- [`basic_temporal.py`](basic_temporal.py) - Simple Temporal backend usage

### Configuration Examples
- [`config_examples/`](config_examples/) - Various configuration approaches
- [`environment_config.py`](environment_config.py) - Environment-based configuration
- [`file_config.py`](file_config.py) - YAML file configuration

### Integration Examples
- [`django_integration.py`](django_integration.py) - Django integration
- [`fastapi_integration.py`](fastapi_integration.py) - FastAPI integration
- [`platform_migration.py`](platform_migration.py) - Unstract platform migration example

### Advanced Usage
- [`backend_switching.py`](backend_switching.py) - Runtime backend switching
- [`error_handling.py`](error_handling.py) - Comprehensive error handling
- [`monitoring.py`](monitoring.py) - Task monitoring and observability

## Running Examples

Each example is self-contained and includes setup instructions:

```bash
# Basic Celery example (requires Redis)
python examples/basic_celery.py

# Configuration examples
python examples/environment_config.py

# Platform integration
python examples/django_integration.py
```

## Directory Structure

```
examples/
├── README.md                    # This file
├── basic_celery.py             # Simple Celery usage
├── basic_hatchet.py            # Simple Hatchet usage
├── basic_temporal.py           # Simple Temporal usage
├── backend_switching.py        # Backend switching demo
├── environment_config.py       # Environment configuration
├── file_config.py             # File configuration
├── error_handling.py          # Error handling patterns
├── monitoring.py              # Monitoring and observability
├── config_examples/           # Configuration examples
│   ├── celery.yaml
│   ├── hatchet.yaml
│   └── temporal.yaml
├── integrations/              # Platform integrations
│   ├── django_integration.py
│   ├── fastapi_integration.py
│   └── platform_migration.py
└── docker/                    # Docker examples
    ├── docker-compose.dev.yml
    └── docker-compose.prod.yml
```

## Prerequisites

Different examples require different backend services:

### Celery Examples
- Redis server running on localhost:6379
- Install: `pip install celery[redis]`

### Hatchet Examples
- Hatchet account and API token
- Install: `pip install hatchet-sdk`

### Temporal Examples
- Temporal server running on localhost:7233
- Install: `pip install temporalio`

## Backend Setup

### Redis (for Celery)
```bash
docker run -d -p 6379:6379 redis:alpine
```

### Temporal (for Temporal)
```bash
docker run -d -p 7233:7233 temporalio/auto-setup:latest
```

### Hatchet
Sign up at https://app.hatchet.run and get your API token.

## Integration Patterns

The examples demonstrate several key integration patterns:

1. **Direct Usage** - Using the library directly in Python code
2. **Framework Integration** - Integrating with Django, FastAPI, etc.
3. **Configuration Management** - Environment, file, and programmatic config
4. **Error Handling** - Robust error handling across backends
5. **Monitoring** - Health checks, metrics, and observability
6. **Testing** - Unit and integration testing patterns

Each pattern is documented with code examples and best practices.