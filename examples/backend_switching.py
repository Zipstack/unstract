#!/usr/bin/env python3
"""Backend switching example.

This example demonstrates:
1. How to switch between different backends using configuration
2. How the same task code works across all backends
3. Configuration-driven backend selection
4. Runtime backend switching

Usage:
    python examples/backend_switching.py
"""

import sys
from pathlib import Path

# Add task-abstraction to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "unstract" / "task-abstraction" / "src"))

from task_abstraction import get_backend
from task_abstraction.models import BackendConfig


def create_backend_configs():
    """Create configurations for different backends."""
    return {
        "celery": BackendConfig(
            backend_type="celery",
            connection_params={
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0",
            }
        ),
        "hatchet": BackendConfig(
            backend_type="hatchet",
            connection_params={
                "token": "your-hatchet-token",  # Replace with real token
                "server_url": "https://app.hatchet.run",
            }
        ),
        "temporal": BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "example-queue",
            }
        )
    }


def register_common_tasks(backend):
    """Register the same tasks on any backend."""
    print(f"📝 Registering tasks on {backend.backend_type} backend...")

    @backend.register_task
    def calculate_fibonacci(n):
        """Calculate Fibonacci number."""
        if n <= 1:
            return n
        return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

    @backend.register_task
    def process_order(order_id, customer_id, items):
        """Process an order."""
        total = sum(item.get("price", 0) * item.get("quantity", 1) for item in items)
        return {
            "order_id": order_id,
            "customer_id": customer_id,
            "total_items": len(items),
            "total_price": total,
            "status": "processed"
        }

    @backend.register_task
    def validate_email(email):
        """Validate email format."""
        return "@" in email and "." in email.split("@")[1]

    print(f"✓ Registered {len(backend._tasks)} tasks")
    return list(backend._tasks.keys())


def test_backend(backend_name, config):
    """Test a specific backend."""
    print(f"\n🔧 Testing {backend_name.upper()} backend")
    print("-" * 40)

    try:
        # Create backend
        backend = get_backend(config=config)
        print(f"✓ Created {backend.backend_type} backend")

        # Register tasks
        task_names = register_common_tasks(backend)

        # Test task submission (simulation)
        print(f"🎯 Testing task submission...")

        # For demonstration, we'll just show that tasks are registered
        # In a real scenario, you'd submit and get results
        for task_name in task_names:
            print(f"  - Task '{task_name}' ready for submission")

        print(f"✓ {backend_name} backend test completed")
        return True

    except ImportError as e:
        print(f"⚠️  {backend_name} backend unavailable: {e}")
        return False
    except Exception as e:
        print(f"❌ {backend_name} backend error: {e}")
        return False


def demonstrate_configuration_switching():
    """Demonstrate switching backends via configuration."""
    print("🔄 Configuration-based Backend Switching")
    print("=" * 50)

    configs = create_backend_configs()
    results = {}

    # Test each backend configuration
    for backend_name, config in configs.items():
        success = test_backend(backend_name, config)
        results[backend_name] = success

    # Summary
    print(f"\n📊 Backend Availability Summary:")
    for backend_name, available in results.items():
        status = "✅ Available" if available else "❌ Unavailable"
        print(f"  - {backend_name.capitalize()}: {status}")

    return results


def demonstrate_environment_switching():
    """Demonstrate switching backends via environment variables."""
    print(f"\n🌍 Environment-based Backend Switching")
    print("-" * 50)

    import os

    # Simulate different environment configurations
    environments = {
        "development": "celery",
        "staging": "hatchet",
        "production": "temporal"
    }

    for env_name, backend_type in environments.items():
        print(f"\n🏷️  Environment: {env_name}")

        # Simulate setting environment variable
        os.environ["TASK_BACKEND_TYPE"] = backend_type

        try:
            # In real usage, get_backend would read from environment
            backend = get_backend(backend_type, use_env=False)  # Simplified for demo
            print(f"✓ Would use {backend.backend_type} backend in {env_name}")
        except:
            print(f"⚠️  {backend_type} backend not available for {env_name}")

    # Clean up environment
    os.environ.pop("TASK_BACKEND_TYPE", None)


def demonstrate_runtime_switching():
    """Demonstrate runtime backend switching."""
    print(f"\n⚡ Runtime Backend Switching")
    print("-" * 50)

    configs = create_backend_configs()

    # Simulate a scenario where we need to switch backends at runtime
    scenarios = [
        ("High load processing", "celery"),
        ("Workflow orchestration", "hatchet"),
        ("Mission critical tasks", "temporal"),
    ]

    for scenario, preferred_backend in scenarios:
        print(f"\n🎭 Scenario: {scenario}")
        print(f"   Preferred backend: {preferred_backend}")

        try:
            config = configs[preferred_backend]
            backend = get_backend(config=config)
            print(f"   ✓ Using {backend.backend_type} backend")

            # Register tasks for this scenario
            register_common_tasks(backend)
            print(f"   ✓ Tasks ready for {scenario}")

        except Exception as e:
            print(f"   ❌ Fallback needed: {e}")

            # Fallback logic
            for fallback_name, fallback_config in configs.items():
                if fallback_name != preferred_backend:
                    try:
                        backend = get_backend(config=fallback_config)
                        print(f"   ⚡ Falling back to {backend.backend_type}")
                        break
                    except:
                        continue


def main():
    """Run backend switching demonstrations."""
    print("🔀 Task Abstraction - Backend Switching Examples")
    print("=" * 60)

    try:
        # Demonstrate different switching approaches
        demonstrate_configuration_switching()
        demonstrate_environment_switching()
        demonstrate_runtime_switching()

        print(f"\n✅ Backend switching examples completed!")
        print(f"\nKey Takeaways:")
        print(f"  • Same task code works across all backends")
        print(f"  • Backend selection via configuration")
        print(f"  • Runtime switching for different scenarios")
        print(f"  • Graceful fallback when backends unavailable")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())