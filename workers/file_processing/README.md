# File Processing Worker

Lightweight Celery worker for file processing tasks.

## Overview

This worker handles:
- `process_file_batch` - File batch processing
- `process_file_batch_api` - API file batch processing

## Running

```bash
uv sync

# Run the worker
 celery -A worker worker --loglevel=info -Q file_processing
