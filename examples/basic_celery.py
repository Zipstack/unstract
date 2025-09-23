#!/usr/bin/env python3
"""Basic Celery backend example.

This example demonstrates:
1. Setting up a Celery backend
2. Registering tasks
3. Submitting tasks for execution
4. Retrieving results

Prerequisites:
- Redis server running on localhost:6379
- Install: pip install celery[redis]

Usage:
    python examples/basic_celery.py
"""

import time
import sys
from pathlib import Path

# Add task-abstraction to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "unstract" / "task-abstraction" / "src"))

from task_abstraction import get_backend
from task_abstraction.models import BackendConfig


def main():
    """Basic Celery example."""
    print("🚀 Basic Celery Backend Example")
    print("=" * 40)

    # Create Celery backend configuration
    config = BackendConfig(
        backend_type="celery",
        connection_params={
            "broker_url": "redis://localhost:6379/0",
            "result_backend": "redis://localhost:6379/0",
        },
        worker_config={
            "concurrency": 4,
            "max_tasks_per_child": 100,
        }
    )

    try:
        # Get backend instance
        print("📡 Connecting to Celery backend...")
        backend = get_backend(config=config)
        print(f"✓ Connected to {backend.backend_type} backend")

        # Register tasks using decorator syntax
        print("\n📝 Registering tasks...")

        @backend.register_task
        def add_numbers(a, b):
            """Add two numbers."""
            print(f"Executing add_numbers({a}, {b})")
            return a + b

        @backend.register_task
        def multiply_numbers(a, b):
            """Multiply two numbers."""
            print(f"Executing multiply_numbers({a}, {b})")
            return a * b

        @backend.register_task
        def process_text(text):
            """Process text and return statistics."""
            print(f"Processing text: '{text[:50]}...'")
            return {
                "length": len(text),
                "words": len(text.split()),
                "uppercase": text.upper()
            }

        print(f"✓ Registered {len(backend._tasks)} tasks:")
        for task_name in backend._tasks.keys():
            print(f"  - {task_name}")

        # Submit tasks for execution
        print("\n🎯 Submitting tasks...")

        # Enable eager mode for immediate execution (development only)
        backend.app.conf.task_always_eager = True
        backend.app.conf.task_eager_propagates = True

        # Submit tasks
        task1_id = backend.submit("add_numbers", 5, 3)
        task2_id = backend.submit("multiply_numbers", 4, 7)
        task3_id = backend.submit("process_text", "Hello, world! This is a test message.")

        print(f"✓ Submitted 3 tasks:")
        print(f"  - Task 1: {task1_id}")
        print(f"  - Task 2: {task2_id}")
        print(f"  - Task 3: {task3_id}")

        # Retrieve results
        print("\n📊 Retrieving results...")

        result1 = backend.get_result(task1_id)
        result2 = backend.get_result(task2_id)
        result3 = backend.get_result(task3_id)

        print(f"✓ Task 1 result: {result1.result} (status: {result1.status})")
        print(f"✓ Task 2 result: {result2.result} (status: {result2.status})")
        print(f"✓ Task 3 result: {result3.result} (status: {result3.status})")

        # Test error handling
        print("\n❌ Testing error handling...")
        try:
            backend.submit("nonexistent_task", 1, 2)
        except ValueError as e:
            print(f"✓ Caught expected error: {e}")

        print("\n✅ Basic Celery example completed successfully!")
        print("\nNote: In production, remove task_always_eager=True and run a Celery worker:")
        print("  celery -A your_app worker --loglevel=info")

    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Install with: pip install celery[redis]")
        return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())