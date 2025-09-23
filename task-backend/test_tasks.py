#!/usr/bin/env python3
"""Test script to submit tasks to the running worker."""

import os
import time
from dotenv import load_dotenv
from unstract.task_abstraction import get_backend, TASK_REGISTRY

# Load environment
load_dotenv()

def test_task_execution():
    """Test task submission and execution."""
    print("🚀 Testing task execution...")

    # Get backend instance
    backend = get_backend()

    # Register tasks from library
    print(f"📋 Registering {len(TASK_REGISTRY)} tasks from task-abstraction library...")

    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)
        print(f"   ✅ Registered: {task_func.__name__}")

    print("🎯 All tasks registered with client backend")

    # Test 1: Simple add_numbers task
    print("\n📝 Test 1: Submitting add_numbers task to file_processing queue...")

    # For Celery, we need to submit with queue routing
    if hasattr(backend, 'app'):  # Celery backend
        celery_task = backend._tasks["add_numbers"]
        result = celery_task.apply_async(args=[15, 25], queue='file_processing')
        task_id = result.id
    else:
        task_id = backend.submit("add_numbers", 15, 25)

    print(f"✅ Submitted add_numbers task: {task_id}")

    # Wait a moment for execution
    print("⏳ Waiting for execution...")
    time.sleep(3)

    result = backend.get_result(task_id)
    print(f"🎉 Result: {result}")

    # Test 2: Echo task
    print("\n📝 Test 2: Submitting echo task to api_processing queue...")

    if hasattr(backend, 'app'):  # Celery backend
        celery_task = backend._tasks["echo"]
        result = celery_task.apply_async(args=["Hello from task-backend!"], queue='api_processing')
        task_id = result.id
    else:
        task_id = backend.submit("echo", "Hello from task-backend!")

    print(f"✅ Submitted echo task: {task_id}")

    time.sleep(3)
    result = backend.get_result(task_id)
    print(f"🎉 Result: {result}")

    # Test 3: Health check
    print("\n📝 Test 3: Submitting health_check task to callback_processing queue...")

    if hasattr(backend, 'app'):  # Celery backend
        celery_task = backend._tasks["health_check"]
        result = celery_task.apply_async(queue='callback_processing')
        task_id = result.id
    else:
        task_id = backend.submit("health_check")

    print(f"✅ Submitted health_check task: {task_id}")

    time.sleep(3)
    result = backend.get_result(task_id)
    print(f"🎉 Result: {result}")

    print("\n✅ All tests completed successfully!")

if __name__ == "__main__":
    test_task_execution()