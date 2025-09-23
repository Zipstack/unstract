# """AutoGen test controller - No authentication required."""

# from typing import Any

# from flask import Blueprint, jsonify, request
# from flask import current_app as app

# from unstract.prompt_service.services.autogen_poc import run_autogen_agent_test

# autogen_bp = Blueprint("autogen", __name__)


# @autogen_bp.route("/test-autogen", methods=["POST", "GET"])
# def test_autogen() -> Any:
#     """Test AutoGen integration endpoint.
    
#     This endpoint doesn't require authentication and is used to test
#     the AutoGen integration with Unstract LLM adapters.
    
#     For POST requests, accepts JSON payload with:
#     - prompt: Optional custom prompt to test
#     - context: Optional context to include
#     - llm_settings: Optional LLM configuration
#     - use_mock: Optional boolean to use mock adapter (default: True)
    
#     For GET requests, runs with default settings.
#     """
#     app.logger.info("Received AutoGen test request")
    
#     if request.method == "POST":
#         payload = request.json or {}
#         prompt = payload.get("prompt")
#         context = payload.get("context")
#         llm_settings = payload.get("llm_settings")
#         use_mock = payload.get("use_mock", True)
#     else:
#         # GET request - use defaults
#         prompt = None
#         context = None
#         llm_settings = None
#         use_mock = request.args.get("use_mock", "true").lower() == "true"
    
#     # Run the AutoGen agent test
#     result = run_autogen_agent_test(
#         llm_settings=llm_settings,
#         prompt=prompt,
#         context=context,
#         use_mock=use_mock
#     )
    
#     app.logger.info(f"AutoGen test result: {result}")
    
#     return jsonify(result)


# @autogen_bp.route("/test-real-autogen", methods=["POST", "GET"])
# def test_real_autogen() -> Any:
#     """Test AutoGen integration with real SDK1 LLM adapter - No authentication required.
    
#     Uses real adapter instance ID: c99c5b5c-4b4f-465b-bf41-ede9d8de691d
    
#     For POST requests, accepts JSON payload with:
#     - prompt: Optional custom prompt to test
#     - context: Optional context to include
#     - streaming: Optional boolean to test streaming (default: False)
#     - test_scenarios: Optional list of scenarios to test
    
#     For GET requests, runs with default settings.
#     """
#     from unstract.prompt_service.services.autogen_poc import run_real_sdk1_autogen_test
    
#     app.logger.info("Received real AutoGen test request")
    
#     if request.method == "POST":
#         payload = request.json or {}
#         prompt = payload.get("prompt")
#         context = payload.get("context")
#         streaming = payload.get("streaming", False)
#         test_scenarios = payload.get("test_scenarios", ["completion"])
#     else:
#         # GET request - use defaults
#         prompt = request.args.get("prompt")
#         context = request.args.get("context")
#         streaming = request.args.get("streaming", "false").lower() == "true"
#         test_scenarios = ["completion"]
    
#     # Run the real SDK1 AutoGen integration test
#     import asyncio
    
#     try:
#         # Run the async function
#         result = asyncio.run(run_real_sdk1_autogen_test(
#             adapter_instance_id="c99c5b5c-4b4f-465b-bf41-ede9d8de691d",
#             prompt=prompt,
#             context=context,
#             streaming=streaming,
#             test_scenarios=test_scenarios
#         ))
#     except Exception as e:
#         app.logger.error(f"Failed to run real AutoGen test: {str(e)}")
#         result = {
#             "success": False,
#             "error": str(e),
#             "message": f"Failed to execute real AutoGen test: {str(e)}",
#             "adapter_instance_id": "c99c5b5c-4b4f-465b-bf41-ede9d8de691d"
#         }
    
#     app.logger.info(f"Real AutoGen test result: {result}")
    
#     return jsonify(result)


# @autogen_bp.route("/test-model-autogen", methods=["POST"])
# def test_model_autogen() -> Any:
#     """Test AutoGen with specific adapter to check model identity.
    
#     This endpoint fetches adapter c99c5b5c-4b4f-465b-bf41-ede9d8de691d,
#     instantiates it like prompt studio does, and uses autogen to ask
#     'Which model are you?' to verify the integration works without deps issues.
    
#     Expects platform_key in request headers or JSON payload.
#     """
#     from unstract.flags.feature_flag import check_feature_flag_status
#     from unstract.prompt_service.helpers.prompt_ide_base_tool import PromptServiceBaseTool
    
#     app.logger.info("Received test-model-autogen request")
    
#     # Hardcode platform_key for testing
#     platform_key = "5b615549-9d2e-4c4c-9b4e-60a0eb82a41b"
    
#     # Fixed adapter instance ID as requested
#     adapter_instance_id = "57f55cd2-e5ee-411e-86e6-d309485bab74"
    
#     try:
#         # Check if SDK1 is available
#         if not check_feature_flag_status("sdk1"):
#             return jsonify({
#                 "success": False,
#                 "error": "SDK1 feature flag is not enabled",
#                 "message": "SDK1 is required for this integration test",
#                 "adapter_instance_id": adapter_instance_id
#             }), 503
        
#         from unstract.sdk1.llm import LLM
#         from unstract.autogen_client import UnstractAutoGenClient
#         from autogen_core.models import UserMessage
        
#         # Create tool instance for SDK1 context (like prompt studio does)
#         tool = PromptServiceBaseTool(platform_key=platform_key)
        
#         app.logger.info(f"Created PromptServiceBaseTool with platform_key")
        
#         # Create LLM adapter using real adapter instance ID (like prompt studio)
#         llm_adapter = LLM(
#             adapter_instance_id=adapter_instance_id,
#             tool=tool,
#             system_prompt="You are a helpful assistant."
#         )
        
#         app.logger.info(f"Created SDK1 LLM adapter with instance ID: {adapter_instance_id}")
        
#         # Create AutoGen client with real adapter
#         autogen_client = UnstractAutoGenClient(
#             llm_adapter=llm_adapter,
#             timeout=30.0,
#             enable_retries=True,
#             max_retries=2
#         )
        
#         app.logger.info("Created UnstractAutoGenClient")
        
#         # Test with the requested prompt
#         prompt = "Which model are you?"
#         messages = [UserMessage(content=prompt, source="user")]
        
#         # Run async completion
#         import asyncio
        
#         async def run_completion():
#             return await autogen_client.create(messages)
        
#         completion_result = asyncio.run(run_completion())
        
#         app.logger.info(f"AutoGen completion successful: {completion_result.content}")
        
#         # Close the client
#         async def close_client():
#             await autogen_client.close()
        
#         asyncio.run(close_client())
        
#         # Return structured response
#         result = {
#             "success": True,
#             "adapter_instance_id": adapter_instance_id,
#             "prompt": prompt,
#             "response": completion_result.content,
#             "usage": {
#                 "prompt_tokens": completion_result.usage.prompt_tokens,
#                 "completion_tokens": completion_result.usage.completion_tokens,
#                 "total_tokens": completion_result.usage.prompt_tokens + completion_result.usage.completion_tokens
#             },
#             "finish_reason": completion_result.finish_reason,
#             "cached": completion_result.cached,
#             "message": "AutoGen model identity test completed successfully"
#         }
        
#         app.logger.info(f"Test completed successfully. Response: {completion_result.content}")
#         return jsonify(result)
        
#     except Exception as e:
#         error_message = str(e)
#         app.logger.error(f"AutoGen model test failed: {error_message}")
        
#         # Provide specific troubleshooting based on error type
#         troubleshooting = {
#             "check_adapter_exists": f"Verify adapter instance {adapter_instance_id} exists in platform",
#             "check_credentials": "Ensure adapter has valid LLM provider credentials",
#             "check_platform_key": "Verify platform_key is valid",
#             "check_platform_connection": "Ensure prompt service can reach platform service"
#         }
        
#         if "adapter" in error_message.lower():
#             troubleshooting["primary_issue"] = "Adapter configuration or credentials"
#         elif "platform" in error_message.lower():
#             troubleshooting["primary_issue"] = "Platform API key or connectivity"
#         elif "timeout" in error_message.lower():
#             troubleshooting["primary_issue"] = "Request timeout - check model response time"
#         else:
#             troubleshooting["primary_issue"] = "Unknown - check logs for details"
        
#         return jsonify({
#             "success": False,
#             "error": error_message,
#             "message": f"AutoGen model identity test failed: {error_message}",
#             "adapter_instance_id": adapter_instance_id,
#             "troubleshooting": troubleshooting
#         }), 500


# @autogen_bp.route("/autogen-health", methods=["GET"])
# def autogen_health() -> Any:
#     """Health check endpoint for AutoGen integration."""
#     return jsonify({
#         "status": "healthy",
#         "service": "autogen-integration",
#         "message": "AutoGen integration is available"
#     })