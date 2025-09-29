#!/usr/bin/env python3
"""Simple test to debug the basic functionality."""

from dotenv import load_dotenv
from unstract.task_abstraction import TASK_REGISTRY, get_backend

# Load environment
load_dotenv()


def test_simple_task():
    """Test a simple task execution."""
    print("🧪 Testing Simple Task Execution...")

    backend = get_backend()

    # Register tasks
    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)
        print(f"   Registered: {task_func.__name__}")

    # Test simple task
    print("\n📤 Submitting add_numbers task...")
    task_id = backend.submit("add_numbers", a=10, b=5)
    print(f"   Task ID: {task_id}")

    # Get result
    print("\n📥 Getting result...")
    result = backend.get_result(task_id)
    print(f"   Status: {result.status}")
    print(f"   Result: {result.result}")
    print(f"   Error: {result.error}")

    if result.is_completed and result.result == 15:
        print("✅ Simple task test PASSED!")
        return True
    else:
        print("❌ Simple task test FAILED!")
        return False


if __name__ == "__main__":
    test_simple_task()
