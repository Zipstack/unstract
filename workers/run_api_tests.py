#!/usr/bin/env python3
"""Test Runner for InternalAPIClient Test Suite

This script provides an easy way to run all API client tests with different
configurations and report generation.

Usage:
    python workers/run_api_tests.py --all
    python workers/run_api_tests.py --comprehensive
    python workers/run_api_tests.py --errors-only
    python workers/run_api_tests.py --integration
    python workers/run_api_tests.py --performance
    python workers/run_api_tests.py --quick
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return the result."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )

        end_time = time.time()
        duration = end_time - start_time

        print(f"\nExecution time: {duration:.2f} seconds")

        if result.returncode == 0:
            print(f"✅ SUCCESS: {description}")
            if result.stdout:
                print(f"\nOutput:\n{result.stdout}")
        else:
            print(f"❌ FAILED: {description}")
            if result.stderr:
                print(f"\nError output:\n{result.stderr}")
            if result.stdout:
                print(f"\nStandard output:\n{result.stdout}")

        return result.returncode == 0, duration, result

    except Exception as e:
        print(f"❌ ERROR running {description}: {str(e)}")
        return False, 0, None


def install_dependencies():
    """Install test dependencies."""
    print("Installing test dependencies...")

    dependencies = [
        "pytest>=7.0.0",
        "responses>=0.20.0",
        "psutil>=5.8.0",
        "requests>=2.25.0",
    ]

    for dep in dependencies:
        cmd = [sys.executable, "-m", "pip", "install", dep]
        success, _, _ = run_command(cmd, f"Installing {dep}")
        if not success:
            print(f"Warning: Failed to install {dep}")


def run_comprehensive_tests():
    """Run comprehensive API client tests."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_comprehensive.py",
        "-v",
        "--tb=short",
        "--durations=10",
        "--strict-markers",
    ]

    return run_command(cmd, "Comprehensive API Client Tests")


def run_error_handling_tests():
    """Run error handling tests."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_error_handling.py",
        "-v",
        "--tb=short",
        "--durations=5",
    ]

    return run_command(cmd, "Error Handling Tests")


def run_integration_tests():
    """Run integration tests."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_integration.py",
        "-v",
        "--tb=short",
        "--durations=10",
    ]

    return run_command(cmd, "Integration Tests")


def run_performance_tests():
    """Run performance tests."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_performance.py",
        "-v",
        "--tb=short",
        "--durations=10",
        "-s",  # Don't capture output for performance metrics
        "-m",
        "performance",
    ]

    return run_command(cmd, "Performance Tests")


def run_quick_tests():
    """Run a quick subset of tests."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_comprehensive.py::TestCoreHTTPMethods",
        "workers/test_api_client_comprehensive.py::TestHealthAndConfiguration",
        "workers/test_api_client_error_handling.py::TestNetworkErrors",
        "-v",
        "--tb=line",
    ]

    return run_command(cmd, "Quick Tests")


def run_all_tests():
    """Run all test suites."""
    test_files = [
        "workers/test_api_client_comprehensive.py",
        "workers/test_api_client_error_handling.py",
        "workers/test_api_client_integration.py",
        "workers/test_api_client_performance.py",
    ]

    cmd = (
        ["python", "-m", "pytest"]
        + test_files
        + ["-v", "--tb=short", "--durations=15", "--strict-markers"]
    )

    return run_command(cmd, "All API Client Tests")


def generate_test_report():
    """Generate a comprehensive test report."""
    report_file = "workers/api_test_report.html"

    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_comprehensive.py",
        "workers/test_api_client_error_handling.py",
        "workers/test_api_client_integration.py",
        "--html=" + report_file,
        "--self-contained-html",
        "--tb=short",
    ]

    success, duration, result = run_command(cmd, "Generating Test Report")

    if success:
        print(f"\n📊 Test report generated: {report_file}")

    return success, duration, result


def run_coverage_analysis():
    """Run tests with coverage analysis."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "workers/test_api_client_comprehensive.py",
        "--cov=workers/shared/api_client",
        "--cov-report=html:workers/coverage_html",
        "--cov-report=term-missing",
        "-v",
    ]

    return run_command(cmd, "Coverage Analysis")


def validate_test_environment():
    """Validate the test environment setup."""
    print("Validating test environment...")

    # Check Python version
    python_version = sys.version_info
    if python_version < (3, 8):
        print(
            f"❌ Python {python_version.major}.{python_version.minor} is too old. Need Python 3.8+"
        )
        return False
    else:
        print(
            f"✅ Python {python_version.major}.{python_version.minor}.{python_version.micro}"
        )

    # Check required modules
    required_modules = ["pytest", "responses", "requests"]
    missing_modules = []

    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} available")
        except ImportError:
            missing_modules.append(module)
            print(f"❌ {module} not available")

    if missing_modules:
        print(f"\nMissing modules: {', '.join(missing_modules)}")
        print("Run with --install-deps to install them")
        return False

    # Check test files exist
    test_files = [
        "workers/test_api_client_comprehensive.py",
        "workers/test_api_client_error_handling.py",
        "workers/test_api_client_integration.py",
        "workers/test_api_client_performance.py",
    ]

    missing_files = []
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"✅ {test_file}")
        else:
            missing_files.append(test_file)
            print(f"❌ {test_file}")

    if missing_files:
        print(f"\nMissing test files: {', '.join(missing_files)}")
        return False

    print("\n✅ Test environment validation successful")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run InternalAPIClient test suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python workers/run_api_tests.py --all                 # Run all tests
  python workers/run_api_tests.py --comprehensive       # Core functionality tests
  python workers/run_api_tests.py --errors-only         # Error handling tests
  python workers/run_api_tests.py --performance         # Performance benchmarks
  python workers/run_api_tests.py --quick               # Quick smoke tests
  python workers/run_api_tests.py --validate            # Check environment
  python workers/run_api_tests.py --install-deps        # Install dependencies
        """,
    )

    parser.add_argument("--all", action="store_true", help="Run all test suites")
    parser.add_argument(
        "--comprehensive", action="store_true", help="Run comprehensive API tests"
    )
    parser.add_argument(
        "--errors-only", action="store_true", help="Run error handling tests only"
    )
    parser.add_argument(
        "--integration", action="store_true", help="Run integration tests"
    )
    parser.add_argument(
        "--performance", action="store_true", help="Run performance tests"
    )
    parser.add_argument("--quick", action="store_true", help="Run quick smoke tests")
    parser.add_argument("--report", action="store_true", help="Generate HTML test report")
    parser.add_argument(
        "--coverage", action="store_true", help="Run with coverage analysis"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate test environment"
    )
    parser.add_argument(
        "--install-deps", action="store_true", help="Install test dependencies"
    )

    args = parser.parse_args()

    # If no specific test type is specified, show help
    if not any(
        [
            args.all,
            args.comprehensive,
            args.errors_only,
            args.integration,
            args.performance,
            args.quick,
            args.report,
            args.coverage,
            args.validate,
            args.install_deps,
        ]
    ):
        parser.print_help()
        return 1

    start_time = time.time()
    total_success = True
    test_results = []

    try:
        if args.install_deps:
            install_dependencies()
            return 0

        if args.validate:
            if not validate_test_environment():
                return 1
            return 0

        # Validate environment before running tests
        if not validate_test_environment():
            print(
                "\n❌ Environment validation failed. Use --install-deps to install dependencies."
            )
            return 1

        # Run selected test suites
        if args.quick:
            success, duration, _ = run_quick_tests()
            test_results.append(("Quick Tests", success, duration))
            total_success = total_success and success

        if args.comprehensive:
            success, duration, _ = run_comprehensive_tests()
            test_results.append(("Comprehensive Tests", success, duration))
            total_success = total_success and success

        if args.errors_only:
            success, duration, _ = run_error_handling_tests()
            test_results.append(("Error Handling Tests", success, duration))
            total_success = total_success and success

        if args.integration:
            success, duration, _ = run_integration_tests()
            test_results.append(("Integration Tests", success, duration))
            total_success = total_success and success

        if args.performance:
            success, duration, _ = run_performance_tests()
            test_results.append(("Performance Tests", success, duration))
            total_success = total_success and success

        if args.coverage:
            success, duration, _ = run_coverage_analysis()
            test_results.append(("Coverage Analysis", success, duration))
            total_success = total_success and success

        if args.report:
            success, duration, _ = generate_test_report()
            test_results.append(("Test Report Generation", success, duration))
            total_success = total_success and success

        if args.all:
            success, duration, _ = run_all_tests()
            test_results.append(("All Tests", success, duration))
            total_success = total_success and success

        # Print summary
        end_time = time.time()
        total_duration = end_time - start_time

        print(f"\n{'='*80}")
        print("TEST EXECUTION SUMMARY")
        print(f"{'='*80}")

        for test_name, success, duration in test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name:<30} ({duration:.2f}s)")

        print(f"\nTotal execution time: {total_duration:.2f} seconds")

        if total_success:
            print("\n🎉 ALL TESTS SUCCESSFUL!")
            return 0
        else:
            print("\n💥 SOME TESTS FAILED!")
            return 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Test execution interrupted by user")
        return 130

    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
