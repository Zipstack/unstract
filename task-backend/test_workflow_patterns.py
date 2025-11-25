#!/usr/bin/env python3
"""Test script focused on testing the new workflow patterns."""

import time

from dotenv import load_dotenv
from unstract.task_abstraction import TASK_REGISTRY, get_backend
from unstract.task_abstraction.workflow import Parallel, Sequential, WorkflowDefinition

# Load environment
load_dotenv()


def test_sequential_pattern():
    """Test the sequential workflow pattern."""
    print("🔄 Testing Sequential Workflow Pattern...")

    backend = get_backend()

    # Register tasks from library
    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)

    # Create a simple sequential workflow: add_numbers -> format_result_message
    workflow = WorkflowDefinition.sequential(
        [
            ("add_numbers", {"a": 10, "b": 5}),  # First task with kwargs
            "format_result_message",  # Second task uses result from first
        ],
        name="sequential_test",
    )

    backend.register_workflow(workflow)

    try:
        # Submit workflow
        workflow_id = backend.submit_workflow("sequential_test", None)
        print(f"✅ Sequential workflow submitted: {workflow_id}")

        # Poll for completion
        while True:
            result = backend.get_workflow_result(workflow_id)
            print(
                f"   Status: {result.status}, Progress: {result.progress_percentage:.1f}%"
            )

            if result.is_completed:
                print(f"🎉 Sequential workflow result: '{result.final_result}'")
                print("✅ Sequential pattern test passed!")
                return True
            elif result.is_failed:
                print(f"❌ Sequential workflow failed: {result.error}")
                return False

            time.sleep(1)

    except Exception as e:
        print(f"❌ Sequential pattern error: {e}")
        return False


def test_parallel_pattern():
    """Test the parallel workflow pattern."""
    print("\n⚡ Testing Parallel Workflow Pattern...")

    backend = get_backend()

    # Register tasks from library
    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)

    # Create a parallel workflow with multiple add operations
    workflow = WorkflowDefinition.parallel(
        [
            ("add_numbers", {"a": 5, "b": 3}),  # = 8
            ("add_numbers", {"a": 10, "b": 7}),  # = 17
            ("add_numbers", {"a": 2, "b": 8}),  # = 10
        ],
        name="parallel_test",
    )

    backend.register_workflow(workflow)

    try:
        # Submit workflow
        workflow_id = backend.submit_workflow("parallel_test", None)
        print(f"✅ Parallel workflow submitted: {workflow_id}")

        # Poll for completion
        while True:
            result = backend.get_workflow_result(workflow_id)
            print(
                f"   Status: {result.status}, Progress: {result.progress_percentage:.1f}%"
            )

            if result.is_completed:
                print(f"🎉 Parallel workflow results: {result.final_result}")
                print("✅ Parallel pattern test passed!")
                return True
            elif result.is_failed:
                print(f"❌ Parallel workflow failed: {result.error}")
                return False

            time.sleep(1)

    except Exception as e:
        print(f"❌ Parallel pattern error: {e}")
        return False


def test_mixed_pattern():
    """Test the mixed workflow pattern."""
    print("\n🎭 Testing Mixed Workflow Pattern...")

    backend = get_backend()

    # Register tasks from library
    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)

    # Create a mixed workflow: Sequential -> Parallel -> Sequential
    workflow = WorkflowDefinition.mixed(
        [
            # Phase 1: Sequential calculation
            Sequential([("add_numbers", {"a": 10, "b": 5})]),  # = 15
            # Phase 2: Parallel echo operations (ignores previous result)
            Parallel(
                [
                    ("echo", {"message": "First parallel echo"}),
                    ("echo", {"message": "Second parallel echo"}),
                ]
            ),
            # Phase 3: Sequential format (uses parallel results)
            Sequential([("add_numbers", {"a": 1, "b": 1})]),  # Simple operation
        ],
        name="mixed_test",
    )

    backend.register_workflow(workflow)

    try:
        # Submit workflow
        workflow_id = backend.submit_workflow("mixed_test", None)
        print(f"✅ Mixed workflow submitted: {workflow_id}")

        # Poll for completion
        while True:
            result = backend.get_workflow_result(workflow_id)
            print(
                f"   Status: {result.status}, Progress: {result.progress_percentage:.1f}%"
            )

            if result.is_completed:
                print(f"🎉 Mixed workflow result: {result.final_result}")
                print("✅ Mixed pattern test passed!")
                return True
            elif result.is_failed:
                print(f"❌ Mixed workflow failed: {result.error}")
                return False

            time.sleep(1)

    except Exception as e:
        print(f"❌ Mixed pattern error: {e}")
        return False


if __name__ == "__main__":
    print("🎨 Testing new Workflow API patterns...\n")

    # Test each pattern
    sequential_passed = test_sequential_pattern()
    parallel_passed = test_parallel_pattern()
    mixed_passed = test_mixed_pattern()

    # Summary
    print("\n📊 Test Results Summary:")
    print(f"   Sequential Pattern: {'✅ PASSED' if sequential_passed else '❌ FAILED'}")
    print(f"   Parallel Pattern:   {'✅ PASSED' if parallel_passed else '❌ FAILED'}")
    print(f"   Mixed Pattern:      {'✅ PASSED' if mixed_passed else '❌ FAILED'}")

    if all([sequential_passed, parallel_passed, mixed_passed]):
        print(
            "\n🏆 All workflow pattern tests passed! The new Workflow API is working correctly."
        )
    else:
        print("\n⚠️  Some workflow pattern tests failed. Check the errors above.")
