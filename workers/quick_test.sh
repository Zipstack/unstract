#!/bin/bash
# Quick test runner for API client tests

# Set up environment
cd "$(dirname "$0")"
export PYTHONPATH="../unstract/core/src:$PYTHONPATH"

# Temporarily disable imports to avoid circular import during testing
if grep -q "from \. import" __init__.py; then
    echo "📝 Temporarily disabling imports in __init__.py for testing..."
    sed -i 's/^from \. import/#from . import/g' __init__.py
    RESTORE_INIT=true
fi

echo "🚀 Running API Client Tests..."
echo "==============================="

# Quick smoke tests
echo -e "\n✨ Running Quick Smoke Tests..."
uv run pytest test_api_client_comprehensive.py::TestCoreHTTPMethods::test_get_request_success \
              test_api_client_comprehensive.py::TestHealthAndConfiguration::test_health_check_success \
              test_api_client_error_handling.py::TestNetworkErrors::test_timeout_error_single_request \
              -v --no-cov --tb=short

if [ $? -eq 0 ]; then
    echo -e "\n✅ Quick tests PASSED!"

    echo -e "\n📋 Running Core HTTP Tests..."
    uv run pytest test_api_client_comprehensive.py::TestCoreHTTPMethods -v --no-cov --tb=short

    echo -e "\n🔧 Running File Execution Tests..."
    uv run pytest test_api_client_comprehensive.py::TestFileExecutionAPIs::test_create_file_batch \
                  test_api_client_comprehensive.py::TestFileExecutionAPIs::test_update_file_execution_status \
                  -v --no-cov --tb=short

    echo -e "\n🌐 Running Webhook Tests..."
    uv run pytest test_api_client_comprehensive.py::TestWebhookAPIs::test_send_webhook \
                  -v --no-cov --tb=short

    echo -e "\n⚠️  Running Error Handling Tests..."
    uv run pytest test_api_client_error_handling.py::TestAuthenticationErrors::test_invalid_api_key_401 \
                  test_api_client_error_handling.py::TestServerErrors::test_internal_server_error_500 \
                  -v --no-cov --tb=short

    echo -e "\n🔗 Running Integration Test..."
    uv run pytest test_api_client_integration.py::TestWorkflowIntegration::test_api_workflow_with_endpoints \
                  -v --no-cov --tb=short

    echo -e "\n🎉 All selected tests completed! ✨"
    echo -e "\nTo run more comprehensive tests:"
    echo "  • All core tests: PYTHONPATH=\"../unstract/core/src:\$PYTHONPATH\" uv run pytest test_api_client_comprehensive.py -v --no-cov"
    echo "  • All error tests: PYTHONPATH=\"../unstract/core/src:\$PYTHONPATH\" uv run pytest test_api_client_error_handling.py -v --no-cov"
    echo "  • All integration tests: PYTHONPATH=\"../unstract/core/src:\$PYTHONPATH\" uv run pytest test_api_client_integration.py -v --no-cov"
    echo "  • Performance tests: PYTHONPATH=\"../unstract/core/src:\$PYTHONPATH\" uv run pytest test_api_client_performance.py -v --no-cov"

else
    echo -e "\n❌ Quick tests FAILED. Check the output above for details."
    exit 1
fi

# Restore __init__.py if we modified it
if [ "$RESTORE_INIT" = true ]; then
    echo "🔄 Restoring __init__.py..."
    sed -i 's/^#from \. import/from . import/g' __init__.py
fi
