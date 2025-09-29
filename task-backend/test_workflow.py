#!/usr/bin/env python3
"""Test script to test workflow/task chaining."""

import time

from dotenv import load_dotenv
from unstract.task_abstraction import TASK_REGISTRY, get_backend
from unstract.task_abstraction.workflow import Parallel, Sequential, WorkflowDefinition

# Load environment
load_dotenv()


def test_task_chaining():
    """Test chaining add_numbers -> concat_with_number."""
    print("🔗 Testing task chaining workflow...")

    # Get backend instance
    backend = get_backend()

    # Register tasks from library
    print(f"📋 Registering {len(TASK_REGISTRY)} tasks from task-abstraction library...")

    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)
        print(f"   ✅ Registered: {task_func.__name__}")

    print("🎯 All tasks registered with client backend")

    # Step 1: Execute add_numbers task
    print("\n📝 Step 1: Submitting add_numbers task (10 + 5)...")

    if hasattr(backend, "app"):  # Celery backend
        celery_task = backend._tasks["add_numbers"]
        result1 = celery_task.apply_async(args=[10, 5], queue="file_processing")
        task_id_1 = result1.id
    else:
        task_id_1 = backend.submit("add_numbers", 10, 5)

    print(f"✅ Submitted add_numbers task: {task_id_1}")

    # Poll for first task completion
    print("⏳ Polling for add_numbers completion (5s intervals)...")
    while True:
        result_1 = backend.get_result(task_id_1)
        print(f"   Status: {result_1.status}")

        if result_1.status == "completed":
            print(f"🎉 Step 1 Result: {result_1}")
            break
        elif result_1.status == "failed":
            print(f"❌ First task failed: {result_1.error}")
            return

        time.sleep(5)

    # Extract the number result from first task
    number_result = result_1.result
    print(f"📊 Number from add_numbers: {number_result}")

    # Step 2: Execute concat_with_number using result from step 1
    print(
        f"\n📝 Step 2: Submitting concat_with_number task ('Result is ', {number_result})..."
    )

    if hasattr(backend, "app"):  # Celery backend
        celery_task = backend._tasks["concat_with_number"]
        result2 = celery_task.apply_async(
            args=["Result is ", number_result], queue="api_processing"
        )
        task_id_2 = result2.id
    else:
        task_id_2 = backend.submit("concat_with_number", "Result is ", number_result)

    print(f"✅ Submitted concat_with_number task: {task_id_2}")

    # Poll for second task completion
    print("⏳ Polling for concat_with_number completion (5s intervals)...")
    while True:
        result_2 = backend.get_result(task_id_2)
        print(f"   Status: {result_2.status}")

        if result_2.status == "completed":
            print(f"🎉 Step 2 Result: {result_2}")
            print(f"\n🏆 Final Chained Result: '{result_2.result}'")
            print("✅ Task chaining workflow completed successfully!")
            break
        elif result_2.status == "failed":
            print(f"❌ Second task failed: {result_2.error}")
            return

        time.sleep(5)


def test_celery_chain():
    """Test using Celery's built-in chain functionality."""
    print("\n🔗 Testing Celery native chain functionality...")

    backend = get_backend()

    # Register tasks from library
    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)

    if hasattr(backend, "app"):
        try:
            from celery import chain

            # Create chain: add_numbers(10, 5) | format_result_message()
            add_task = backend._tasks["add_numbers"]
            format_task = backend._tasks["format_result_message"]

            # Build the chain with proper queue routing for each task
            # format_result_message is designed for chains - takes number as first arg
            workflow_chain = chain(
                add_task.s(10, 5).set(queue="file_processing"),
                format_task.s().set(
                    queue="api_processing"
                ),  # Result (15) becomes first arg
            )

            print("📝 Submitting Celery chain workflow...")
            chain_result = workflow_chain.apply_async()
            print(f"✅ Submitted chain workflow: {chain_result.id}")

            # Poll for chain completion
            print("⏳ Polling for chain completion (5s intervals)...")
            while True:
                if chain_result.ready():
                    final_result = chain_result.result
                    print(f"🏆 Celery Chain Final Result: '{final_result}'")
                    print("✅ Celery chain workflow completed successfully!")
                    break
                elif chain_result.failed():
                    print(f"❌ Chain failed: {chain_result.result}")
                    break
                else:
                    print(f"   Chain status: {chain_result.status}")
                    time.sleep(5)

        except ImportError:
            print("❌ Celery chain not available")
        except Exception as e:
            print(f"❌ Chain execution failed: {e}")
    else:
        print("❌ Not using Celery backend, skipping chain test")


def test_workflow_patterns():
    """Test new workflow patterns: Sequential, Parallel, and Mixed."""
    print("\n🎨 Testing new Workflow API patterns...")

    backend = get_backend()

    # Register tasks from library
    for task_func in TASK_REGISTRY:
        backend.register_task(task_func)

    print("✅ Tasks registered for workflow pattern tests")

    # Test 1: Sequential workflow
    print("\n🔄 Test 1: Sequential Workflow Pattern")
    sequential_workflow = WorkflowDefinition.sequential(
        [("add_numbers", {"a": 10, "b": 5}), "format_result_message"],
        name="sequential_test",
        description="Sequential add->format workflow",
    )

    backend.register_workflow(sequential_workflow)

    try:
        print("📝 Submitting sequential workflow...")
        workflow_id = backend.submit_workflow("sequential_test", None)
        print(f"✅ Sequential workflow submitted: {workflow_id}")

        # Poll for completion
        print("⏳ Polling for sequential workflow completion...")
        while True:
            result = backend.get_workflow_result(workflow_id)
            print(
                f"   Status: {result.status}, Progress: {result.progress_percentage:.1f}%"
            )

            if result.is_completed:
                print(f"🎉 Sequential workflow completed: {result.final_result}")
                break
            elif result.is_failed:
                print(f"❌ Sequential workflow failed: {result.error}")
                break

            time.sleep(2)

    except Exception as e:
        print(f"❌ Sequential workflow error: {e}")

    # Test 2: Parallel workflow
    print("\n⚡ Test 2: Parallel Workflow Pattern")
    parallel_workflow = WorkflowDefinition.parallel(
        [
            ("add_numbers", {"a": 5, "b": 3}),
            ("add_numbers", {"a": 10, "b": 7}),
            ("add_numbers", {"a": 2, "b": 8}),
        ],
        name="parallel_test",
        description="Parallel add operations",
    )

    backend.register_workflow(parallel_workflow)

    try:
        print("📝 Submitting parallel workflow...")
        workflow_id = backend.submit_workflow("parallel_test", None)
        print(f"✅ Parallel workflow submitted: {workflow_id}")

        # Poll for completion
        print("⏳ Polling for parallel workflow completion...")
        while True:
            result = backend.get_workflow_result(workflow_id)
            print(
                f"   Status: {result.status}, Progress: {result.progress_percentage:.1f}%"
            )

            if result.is_completed:
                print(f"🎉 Parallel workflow completed: {result.final_result}")
                break
            elif result.is_failed:
                print(f"❌ Parallel workflow failed: {result.error}")
                break

            time.sleep(2)

    except Exception as e:
        print(f"❌ Parallel workflow error: {e}")

    # Test 3: Mixed workflow
    print("\n🎭 Test 3: Mixed Workflow Pattern")
    mixed_workflow = WorkflowDefinition.mixed(
        [
            Sequential([("add_numbers", {"a": 10, "b": 5})]),  # Step 1: Calculate 15
            Parallel(
                [  # Step 2: Multiple operations with result
                    ("echo", {"message": "First parallel task"}),
                    ("echo", {"message": "Second parallel task"}),
                ]
            ),
            Sequential(["format_result_message"]),  # Step 3: Format final result
        ],
        name="mixed_test",
        description="Mixed sequential->parallel->sequential workflow",
    )

    backend.register_workflow(mixed_workflow)

    try:
        print("📝 Submitting mixed workflow...")
        workflow_id = backend.submit_workflow("mixed_test", None)
        print(f"✅ Mixed workflow submitted: {workflow_id}")

        # Poll for completion
        print("⏳ Polling for mixed workflow completion...")
        while True:
            result = backend.get_workflow_result(workflow_id)
            print(
                f"   Status: {result.status}, Progress: {result.progress_percentage:.1f}%"
            )

            if result.is_completed:
                print(f"🎉 Mixed workflow completed: {result.final_result}")
                break
            elif result.is_failed:
                print(f"❌ Mixed workflow failed: {result.error}")
                break

            time.sleep(2)

    except Exception as e:
        print(f"❌ Mixed workflow error: {e}")


if __name__ == "__main__":
    test_task_chaining()
    test_celery_chain()
    test_workflow_patterns()
