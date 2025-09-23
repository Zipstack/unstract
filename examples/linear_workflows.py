#!/usr/bin/env python3
"""Linear workflow example.

This example demonstrates:
1. Creating linear workflows with @workflow decorator
2. Sequential task execution across different backends
3. Workflow result tracking and progress monitoring
4. Backend-specific workflow implementations

Usage:
    python examples/linear_workflows.py
"""

import sys
from pathlib import Path

# Add task-abstraction to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "unstract" / "task-abstraction" / "src"))

from task_abstraction import get_backend, workflow, WorkflowDefinition
from task_abstraction.models import BackendConfig


def create_data_processing_tasks(backend):
    """Register tasks for data processing workflow."""
    print("📝 Registering data processing tasks...")

    @backend.register_task
    def extract_data(input_data, source="default"):
        """Extract data from source."""
        print(f"  🔍 Extracting data from {source}")
        return {
            "extracted": input_data,
            "source": source,
            "record_count": len(str(input_data))
        }

    @backend.register_task
    def validate_data(input_data, strict=False):
        """Validate extracted data."""
        print(f"  ✅ Validating data (strict={strict})")
        if not input_data.get("extracted"):
            raise ValueError("No data to validate")

        return {
            **input_data,
            "validated": True,
            "validation_mode": "strict" if strict else "normal"
        }

    @backend.register_task
    def transform_data(input_data, format="json"):
        """Transform data to specified format."""
        print(f"  🔄 Transforming data to {format}")
        return {
            **input_data,
            "transformed": True,
            "format": format,
            "size": input_data.get("record_count", 0) * 2  # Simulated processing
        }

    @backend.register_task
    def load_data(input_data, target="warehouse"):
        """Load data to target destination."""
        print(f"  💾 Loading data to {target}")
        return {
            **input_data,
            "loaded": True,
            "target": target,
            "final_status": "success"
        }

    print(f"✓ Registered {len(backend._tasks)} tasks")
    return ["extract_data", "validate_data", "transform_data", "load_data"]


def demonstrate_workflow_decorator(backend):
    """Demonstrate @workflow decorator usage."""
    print("\n🔀 Demonstrating @workflow decorator")
    print("-" * 40)

    # Create workflow using decorator
    @workflow(backend, description="Complete data processing pipeline")
    def data_processing_pipeline():
        """Define a linear data processing workflow."""
        return [
            ("extract_data", {"source": "database"}),
            ("validate_data", {"strict": True}),
            ("transform_data", {"format": "parquet"}),
            ("load_data", {"target": "data_lake"})
        ]

    print(f"✓ Workflow 'data_processing_pipeline' registered")
    print(f"✓ Workflow steps: {len(backend._workflows['data_processing_pipeline'].steps)}")

    return "data_processing_pipeline"


def demonstrate_programmatic_workflow(backend):
    """Demonstrate programmatic workflow creation."""
    print("\n🛠 Demonstrating programmatic workflow creation")
    print("-" * 40)

    # Create workflow programmatically
    workflow_def = WorkflowDefinition.from_step_list(
        name="quick_analysis",
        steps=[
            "extract_data",
            ("validate_data", {"strict": False}),
            "transform_data"
        ],
        description="Quick data analysis workflow"
    )

    backend.register_workflow(workflow_def)

    print(f"✓ Workflow 'quick_analysis' registered")
    print(f"✓ Workflow steps: {len(workflow_def.steps)}")

    return "quick_analysis"


def simulate_workflow_execution(backend, workflow_name, input_data):
    """Simulate workflow execution and result tracking."""
    print(f"\n🚀 Executing workflow: {workflow_name}")
    print("-" * 40)

    try:
        # Submit workflow
        workflow_id = backend.submit_workflow(workflow_name, input_data)
        print(f"✓ Workflow submitted: {workflow_id}")

        # Get workflow result
        result = backend.get_workflow_result(workflow_id)
        print(f"📊 Workflow status: {result.status}")
        print(f"📈 Progress: {result.steps_completed}/{result.total_steps} steps")

        if result.progress_percentage > 0:
            print(f"📊 Progress: {result.progress_percentage:.1f}%")

        if result.is_completed:
            print(f"✅ Final result: {result.final_result}")
        elif result.is_failed:
            print(f"❌ Error: {result.error}")
        else:
            print(f"⏳ Status: {result.status}")

        return result

    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
        return None


def test_backend_workflow_support(backend_name, config):
    """Test workflow support for a specific backend."""
    print(f"\n🔧 Testing {backend_name.upper()} workflow support")
    print("=" * 50)

    try:
        # Create backend
        backend = get_backend(config=config)
        print(f"✓ Created {backend.backend_type} backend")

        # Register tasks
        task_names = create_data_processing_tasks(backend)

        # Test workflow decorator
        workflow1 = demonstrate_workflow_decorator(backend)

        # Test programmatic workflow creation
        workflow2 = demonstrate_programmatic_workflow(backend)

        # Test workflow execution (simulation)
        print(f"\n🎯 Testing workflow execution simulation...")

        input_data = {"raw_data": "customer_records_2024.csv", "timestamp": "2024-01-01"}

        # Test both workflows
        for workflow_name in [workflow1, workflow2]:
            simulate_workflow_execution(backend, workflow_name, input_data)

        print(f"✅ {backend_name} workflow testing completed")
        return True

    except ImportError as e:
        print(f"⚠️  {backend_name} backend unavailable: {e}")
        return False
    except Exception as e:
        print(f"❌ {backend_name} workflow error: {e}")
        return False


def demonstrate_workflow_features():
    """Demonstrate workflow features across backends."""
    print("🔄 Linear Workflows - Task Abstraction Examples")
    print("=" * 60)

    # Backend configurations
    configs = {
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
                "token": "your-hatchet-token",
                "server_url": "https://app.hatchet.run",
            }
        ),
        "temporal": BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "workflow-queue",
            }
        )
    }

    results = {}

    # Test each backend
    for backend_name, config in configs.items():
        success = test_backend_workflow_support(backend_name, config)
        results[backend_name] = success

    # Summary
    print(f"\n📊 Workflow Support Summary:")
    for backend_name, available in results.items():
        status = "✅ Supported" if available else "❌ Unavailable"
        print(f"  - {backend_name.capitalize()}: {status}")

    return results


def demonstrate_workflow_patterns():
    """Demonstrate different workflow patterns."""
    print(f"\n🎨 Workflow Pattern Examples")
    print("-" * 40)

    patterns = {
        "ETL Pipeline": [
            ("extract", {"source": "postgres"}),
            ("transform", {"rules": "business_logic"}),
            ("load", {"target": "warehouse"})
        ],
        "Data Validation": [
            "check_format",
            ("validate_schema", {"strict": True}),
            ("check_quality", {"threshold": 0.95}),
            "generate_report"
        ],
        "ML Pipeline": [
            "load_data",
            ("preprocess", {"normalize": True}),
            ("train_model", {"algorithm": "random_forest"}),
            ("evaluate", {"metrics": ["accuracy", "f1"]}),
            "save_model"
        ]
    }

    for pattern_name, steps in patterns.items():
        print(f"\n📋 {pattern_name}:")
        for i, step in enumerate(steps, 1):
            if isinstance(step, tuple):
                task_name, kwargs = step
                print(f"  {i}. {task_name} {kwargs}")
            else:
                print(f"  {i}. {step}")

    print(f"\n💡 All patterns use the same workflow interface!")


def main():
    """Run linear workflow demonstrations."""
    try:
        # Demonstrate workflow concepts
        demonstrate_workflow_patterns()

        # Test workflow implementation
        demonstrate_workflow_features()

        print(f"\n✅ Linear workflow examples completed!")
        print(f"\nKey Features Demonstrated:")
        print(f"  • @workflow decorator for defining linear workflows")
        print(f"  • Sequential task execution with data flow")
        print(f"  • Backend-specific workflow implementations")
        print(f"  • Workflow progress tracking and monitoring")
        print(f"  • Unified interface across Celery, Hatchet, Temporal")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())