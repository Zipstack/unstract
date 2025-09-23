# """AutoGen service for integration with Unstract LLM adapters."""

# import logging
# from typing import Any, Dict, List, Optional

# from unstract.autogen_client import (
#     SimpleAutoGenAgent,
#     create_simple_autogen_agent,
#     process_with_autogen,
#     run_autogen_poc,
# )

# logger = logging.getLogger(__name__)


# def test_autogen_integration(llm_adapter: Any) -> Dict[str, Any]:
#     """Test AutoGen integration with Unstract LLM adapter.
    
#     This is a POC function that demonstrates AutoGen working with
#     Unstract LLM adapters. It runs a simple test and logs the results.
    
#     Args:
#         llm_adapter: Unstract LLM adapter instance (e.g., LLM object from SDK1)
        
#     Returns:
#         Dictionary containing test results
#     """
#     logger.info("Starting AutoGen integration POC test")
    
#     try:
#         # Test 1: Basic prompt
#         basic_result = process_with_autogen(
#             llm_adapter=llm_adapter,
#             prompt="What is 2+2? Answer in one word.",
#             system_message="You are a helpful math assistant. Be concise."
#         )
        
#         logger.info("AutoGen POC Test 1 (Basic Math):")
#         logger.info("  Prompt: What is 2+2? Answer in one word.")
#         logger.info("  Response: %s", basic_result["response"])
#         logger.info("  Token Usage: %s", basic_result["usage"])
        
#         # Test 2: Context-based prompt
#         context_result = process_with_autogen(
#             llm_adapter=llm_adapter,
#             prompt="What is the main topic?",
#             system_message="You are a helpful assistant that analyzes context.",
#             context="The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France."
#         )
        
#         logger.info("AutoGen POC Test 2 (Context Analysis):")
#         logger.info("  Prompt: What is the main topic?")
#         logger.info("  Context: The Eiffel Tower is a wrought-iron lattice tower...")
#         logger.info("  Response: %s", context_result["response"])
#         logger.info("  Token Usage: %s", context_result["usage"])
        
#         # Test 3: Run the built-in POC
#         builtin_result = run_autogen_poc(llm_adapter)
        
#         logger.info("AutoGen POC Test 3 (Built-in POC):")
#         logger.info("  Result: %s", builtin_result)
        
#         # Compile results
#         poc_results = {
#             "success": True,
#             "message": "AutoGen integration POC completed successfully",
#             "tests": {
#                 "basic_math": {
#                     "prompt": "What is 2+2? Answer in one word.",
#                     "response": basic_result["response"],
#                     "usage": basic_result["usage"]
#                 },
#                 "context_analysis": {
#                     "prompt": "What is the main topic?",
#                     "response": context_result["response"],
#                     "usage": context_result["usage"]
#                 },
#                 "builtin_poc": builtin_result
#             },
#             "total_tokens": (
#                 basic_result["usage"]["total_tokens"] + 
#                 context_result["usage"]["total_tokens"]
#             )
#         }
        
#         logger.info("AutoGen POC completed successfully. Total tokens used: %s", 
#                    poc_results["total_tokens"])
        
#         return poc_results
        
#     except Exception as e:
#         logger.error("AutoGen POC failed with error: %s", str(e))
#         return {
#             "success": False,
#             "message": f"AutoGen integration POC failed: {str(e)}",
#             "error": str(e)
#         }


# def run_autogen_agent_test(
#     llm_settings: Optional[Dict[str, Any]] = None,
#     prompt: Optional[str] = None,
#     context: Optional[str] = None,
#     use_mock: bool = True  # Allow switching between mock and real adapter
# ) -> Dict[str, Any]:
#     """Run a simple AutoGen agent test with Unstract LLM adapter.
    
#     This function creates an LLM adapter using SDK1 and tests the AutoGen
#     integration by processing a prompt through the UnstractAutoGenClient.
    
#     Args:
#         llm_settings: Optional LLM configuration settings
#         prompt: Optional custom prompt to test (defaults to a simple math question)
#         context: Optional context to include with the prompt
#         use_mock: If True, use mock adapter; if False, use real SDK1 adapter
        
#     Returns:
#         Dictionary containing the test results
#     """
#     from unstract.flags.feature_flag import check_feature_flag_status
    
#     logger.info(f"Starting AutoGen agent test with {'mock' if use_mock else 'SDK1'} LLM adapter")
    
#     try:
#         if use_mock:
#             # Create a mock LLM adapter for testing
#             class MockLLMAdapter:
#                 """Mock LLM adapter that simulates SDK1 LLM behavior."""
                
#                 def completion(self, messages, **kwargs):
#                     """Mock completion method that simulates LLM responses."""
#                     # Extract the last user message
#                     user_message = next((m for m in reversed(messages) if m.get("role") == "user"), {})
#                     content = user_message.get("content", "")
                    
#                     # Generate mock responses based on prompt content
#                     if "capital" in content.lower() and "france" in content.lower():
#                         response_text = "The capital of France is Paris."
#                     elif "2+2" in content:
#                         response_text = "Four"
#                     elif "hello" in content.lower():
#                         response_text = "Hello! How can I help you today?"
#                     else:
#                         response_text = f"I understand your request: '{content[:50]}...'. Here's my response."
                    
#                     # Create a mock response object that matches the expected structure
#                     class MockChoice:
#                         def __init__(self, content, finish_reason):
#                             self.message = type('obj', (object,), {'content': content})()
#                             self.finish_reason = finish_reason
                    
#                     class MockUsage:
#                         def __init__(self, prompt_tokens, completion_tokens):
#                             self.prompt_tokens = prompt_tokens
#                             self.completion_tokens = completion_tokens
#                             self.total_tokens = prompt_tokens + completion_tokens
                    
#                     class MockResponse:
#                         def __init__(self, content, finish_reason, usage):
#                             self.choices = [MockChoice(content, finish_reason)]
#                             self.usage = usage
#                             self.cached = False
                    
#                     usage = MockUsage(
#                         prompt_tokens=len(str(messages)) // 4,
#                         completion_tokens=len(response_text) // 4
#                     )
                    
#                     return MockResponse(response_text, "stop", usage)
            
#             # Create mock adapter
#             llm_adapter = MockLLMAdapter()
#             logger.info("Created mock LLM adapter for testing")
            
#         else:
#             # Use real SDK1 LLM adapter
#             if check_feature_flag_status("sdk1"):
#                 from unstract.sdk1.llm import LLM
#                 from unstract.sdk1.tool.base import BaseTool
                
#                 # Create a minimal tool implementation for SDK1
#                 class MinimalTool(BaseTool):
#                     """Minimal tool implementation for testing."""
                    
#                     def __init__(self):
#                         self._env = {}
                    
#                     def run(self, **kwargs: Any) -> Any:
#                         """Implement abstract run method."""
#                         logger.info("MinimalTool.run() called for testing")
#                         return {"status": "success", "message": "Tool executed"}
                    
#                     def get_env(self, key: str, default: Any = None) -> Any:
#                         """Get environment variable."""
#                         import os
#                         return os.environ.get(key, default)
                    
#                     def get_env_or_die(self, key: str) -> str:
#                         """Get environment variable or raise error."""
#                         import os
#                         value = os.environ.get(key)
#                         if not value:
#                             # Return a mock value for testing
#                             return "mock-api-key"
#                         return value
                    
#                     def stream_log(self, log_message: str, level: str = "INFO") -> None:
#                         """Stream log message."""
#                         logger.info(f"[Tool] {log_message}")
                
#                 # Create tool instance
#                 tool = MinimalTool()
                
#                 # Default adapter metadata for SDK1
#                 if llm_settings is None:
#                     adapter_metadata = {
#                         "model": "mock-model",
#                         "temperature": 0.7,
#                         "max_tokens": 500
#                     }
#                 else:
#                     adapter_metadata = llm_settings
                
#                 # Create LLM adapter using SDK1 with mock adapter
#                 # SDK1 LLM expects: adapter_id, adapter_metadata, tool, etc.
#                 llm_adapter = LLM(
#                     adapter_id="mock",  # Use mock adapter ID
#                     adapter_metadata=adapter_metadata,
#                     tool=tool,
#                     system_prompt="You are a helpful assistant."
#                 )
                
#                 logger.info(f"Created SDK1 LLM adapter with metadata: {adapter_metadata}")
#             else:
#                 # Fallback to mock if SDK1 is not available
#                 logger.warning("SDK1 feature flag is disabled, using mock adapter")
#                 return run_autogen_agent_test(llm_settings, prompt, context, use_mock=True)
        
#         logger.info(f"Created LLM adapter for testing")
        
#         # Use default prompt if none provided
#         if prompt is None:
#             prompt = "What is the capital of France? Answer in one sentence."
        
#         # Create AutoGen agent
#         agent = create_simple_autogen_agent(
#             llm_adapter=llm_adapter,
#             system_message="You are a helpful assistant. Be concise and accurate.",
#             name="test_agent"
#         )
        
#         logger.info("Created SimpleAutoGenAgent")
        
#         # Process the prompt
#         result = agent.process_message(
#             message=prompt,
#             context=context,
#             include_history=False
#         )
        
#         logger.info(f"AutoGen agent response: {result['response']}")
#         logger.info(f"Token usage: {result['usage']}")
        
#         # Clean up
#         agent.clear_history()
        
#         return {
#             "success": True,
#             "prompt": prompt,
#             "context": context,
#             "response": result["response"],
#             "usage": result["usage"],
#             "message": "AutoGen agent test completed successfully"
#         }
        
#     except Exception as e:
#         logger.error(f"AutoGen agent test failed: {str(e)}")
#         return {
#             "success": False,
#             "error": str(e),
#             "message": f"AutoGen agent test failed: {str(e)}"
#         }


# class AutoGenTestTool:
#     """Minimal tool implementation for AutoGen testing with real SDK1 adapter."""
    
#     def __init__(self):
#         self._env = {}
    
#     def run(self, **kwargs: Any) -> Any:
#         """Tool run method - not used for AutoGen testing."""
#         return {"status": "success", "message": "AutoGen test tool"}
    
#     def get_env(self, key: str, default: Any = None) -> Any:
#         """Get environment variable."""
#         import os
#         return os.environ.get(key, default)
    
#     def get_env_or_die(self, key: str) -> str:
#         """Get environment variable or raise error."""
#         import os
#         value = os.environ.get(key)
#         if not value:
#             raise Exception(f"Missing required environment variable: {key}")
#         return value
    
#     def stream_log(self, log_message: str, level: str = "INFO") -> None:
#         """Stream log message."""
#         logger.info(f"[AutoGenTestTool] {log_message}")


# async def run_real_sdk1_autogen_test(
#     adapter_instance_id: str = "c99c5b5c-4b4f-465b-bf41-ede9d8de691d",
#     prompt: Optional[str] = None,
#     context: Optional[str] = None,
#     streaming: bool = False,
#     test_scenarios: List[str] = None
# ) -> Dict[str, Any]:
#     """Test AutoGen integration with real SDK1 LLM adapter.
    
#     Uses a real adapter instance ID to test the integration between
#     AutoGen client and SDK1 LLM adapters with actual platform configuration.
    
#     Args:
#         adapter_instance_id: The real adapter instance ID to use
#         prompt: Optional custom prompt to test (defaults to a simple question)
#         context: Optional context to include with the prompt
#         streaming: If True, test streaming completion
#         test_scenarios: List of test scenarios to run
        
#     Returns:
#         Dictionary containing the test results
#     """
#     from unstract.flags.feature_flag import check_feature_flag_status
    
#     logger.info(f"Starting real SDK1 AutoGen test with adapter: {adapter_instance_id}")
    
#     if test_scenarios is None:
#         test_scenarios = ["completion"]
    
#     try:
#         # Ensure SDK1 is available
#         if not check_feature_flag_status("sdk1"):
#             raise Exception("SDK1 feature flag is not enabled")
        
#         from unstract.sdk1.llm import LLM
#         from unstract.autogen_client import UnstractAutoGenClient
#         from autogen_core.models import UserMessage
        
#         # Create tool instance for SDK1 context
#         tool = AutoGenTestTool()
        
#         logger.info(f"Created AutoGenTestTool for SDK1 context")
        
#         # Create LLM adapter using real adapter instance ID
#         llm_adapter = LLM(
#             adapter_instance_id=adapter_instance_id,
#             tool=tool,
#             system_prompt="You are a helpful assistant. Be concise and accurate."
#         )
        
#         logger.info(f"Created SDK1 LLM adapter with instance ID: {adapter_instance_id}")
        
#         # Create AutoGen client with real adapter
#         autogen_client = UnstractAutoGenClient(
#             llm_adapter=llm_adapter,
#             timeout=60.0,
#             enable_retries=True,
#             max_retries=3
#         )
        
#         logger.info("Created UnstractAutoGenClient with real SDK1 adapter")
        
#         # Use default prompt if none provided
#         if prompt is None:
#             prompt = "What is the capital of France? Answer in one sentence."
        
#         results = {
#             "success": True,
#             "adapter_instance_id": adapter_instance_id,
#             "adapter_type": "real_sdk1",
#             "tests": {},
#             "total_tokens_used": 0
#         }
        
#         # Test 1: Basic completion
#         if "completion" in test_scenarios:
#             logger.info("Running basic completion test...")
            
#             messages = [UserMessage(content=prompt, source="user")]
#             if context:
#                 messages.insert(0, UserMessage(content=f"Context: {context}", source="system"))
            
#             completion_result = await autogen_client.create(messages)
            
#             test_result = {
#                 "prompt": prompt,
#                 "context": context,
#                 "response": completion_result.content,
#                 "usage": {
#                     "prompt_tokens": completion_result.usage.prompt_tokens,
#                     "completion_tokens": completion_result.usage.completion_tokens,
#                     "total_tokens": completion_result.usage.total_tokens
#                 },
#                 "finish_reason": completion_result.finish_reason,
#                 "cached": completion_result.cached
#             }
            
#             results["tests"]["basic_completion"] = test_result
#             results["total_tokens_used"] += completion_result.usage.total_tokens
            
#             logger.info(f"Basic completion test completed. Response: {completion_result.content}")
#             logger.info(f"Token usage: {completion_result.usage.total_tokens}")
        
#         # Test 2: Streaming completion
#         if streaming and "streaming" in test_scenarios:
#             logger.info("Running streaming completion test...")
            
#             messages = [UserMessage(content=f"Tell me a short story about {prompt}", source="user")]
            
#             chunks_received = 0
#             collected_content = []
#             final_result = None
            
#             async for chunk in autogen_client.create_stream(messages):
#                 if isinstance(chunk, str):
#                     collected_content.append(chunk)
#                     chunks_received += 1
#                 else:
#                     # Final CreateResult
#                     final_result = chunk
            
#             streaming_test_result = {
#                 "prompt": f"Tell me a short story about {prompt}",
#                 "chunks_received": chunks_received,
#                 "total_response": "".join(collected_content),
#                 "usage": {
#                     "prompt_tokens": final_result.usage.prompt_tokens,
#                     "completion_tokens": final_result.usage.completion_tokens,
#                     "total_tokens": final_result.usage.total_tokens
#                 } if final_result else {"total_tokens": 0},
#                 "finish_reason": final_result.finish_reason if final_result else None
#             }
            
#             results["tests"]["streaming_completion"] = streaming_test_result
#             if final_result:
#                 results["total_tokens_used"] += final_result.usage.total_tokens
            
#             logger.info(f"Streaming test completed. Chunks received: {chunks_received}")
        
#         # Test 3: Multi-turn conversation
#         if "conversation" in test_scenarios:
#             logger.info("Running multi-turn conversation test...")
            
#             conversation_messages = [
#                 UserMessage(content="What is 2+2?", source="user")
#             ]
            
#             # First turn
#             first_response = await autogen_client.create(conversation_messages)
            
#             # Second turn - follow up
#             conversation_messages.extend([
#                 UserMessage(content=first_response.content, source="assistant"),
#                 UserMessage(content="Now multiply that result by 3.", source="user")
#             ])
            
#             second_response = await autogen_client.create(conversation_messages)
            
#             conversation_test_result = {
#                 "turns": [
#                     {
#                         "prompt": "What is 2+2?",
#                         "response": first_response.content,
#                         "usage": {
#                             "total_tokens": first_response.usage.total_tokens
#                         }
#                     },
#                     {
#                         "prompt": "Now multiply that result by 3.",
#                         "response": second_response.content,
#                         "usage": {
#                             "total_tokens": second_response.usage.total_tokens
#                         }
#                     }
#                 ],
#                 "total_conversation_tokens": first_response.usage.total_tokens + second_response.usage.total_tokens
#             }
            
#             results["tests"]["multi_turn_conversation"] = conversation_test_result
#             results["total_tokens_used"] += conversation_test_result["total_conversation_tokens"]
            
#             logger.info("Multi-turn conversation test completed")
        
#         # Close the client
#         await autogen_client.close()
        
#         results["message"] = f"Real SDK1 AutoGen integration test completed successfully. Ran {len(test_scenarios)} scenarios."
#         results["integration_status"] = "real_sdk1_autogen_success"
        
#         logger.info(f"Real SDK1 AutoGen test completed successfully. Total tokens used: {results['total_tokens_used']}")
        
#         return results
        
#     except Exception as e:
#         error_message = str(e)
#         logger.error(f"Real SDK1 AutoGen test failed: {error_message}")
        
#         # Provide specific troubleshooting based on error type
#         troubleshooting = {
#             "check_adapter_exists": f"Verify adapter instance {adapter_instance_id} exists in platform",
#             "check_credentials": "Ensure adapter has valid LLM provider credentials",
#             "check_platform_key": "Verify PLATFORM_API_KEY environment variable is set",
#             "check_sdk1_flag": "Ensure SDK1 feature flag is enabled"
#         }
        
#         if "adapter" in error_message.lower():
#             troubleshooting["primary_issue"] = "Adapter configuration or credentials"
#         elif "platform" in error_message.lower():
#             troubleshooting["primary_issue"] = "Platform API key or connectivity"
#         elif "sdk1" in error_message.lower():
#             troubleshooting["primary_issue"] = "SDK1 feature flag or module loading"
#         else:
#             troubleshooting["primary_issue"] = "Unknown - check logs for details"
        
#         return {
#             "success": False,
#             "error": error_message,
#             "message": f"Real SDK1 AutoGen integration test failed: {error_message}",
#             "adapter_instance_id": adapter_instance_id,
#             "adapter_type": "real_sdk1",
#             "troubleshooting": troubleshooting
#         }


# def log_autogen_poc_results() -> None:
#     """Log AutoGen POC results to demonstrate integration.
    
#     This function can be called from anywhere in the prompt service
#     to test AutoGen integration without modifying existing flows.
#     """
#     logger.info("=" * 50)
#     logger.info("AUTOGEN INTEGRATION POC - PROOF OF CONCEPT")
#     logger.info("=" * 50)
#     logger.info("This demonstrates that AutoGen can be integrated with Unstract")
#     logger.info("The autogen-client package provides helper functions that work")
#     logger.info("with Unstract LLM adapters without requiring AutoGen dependencies")
#     logger.info("in the prompt service.")
#     logger.info("")
#     logger.info("Integration points:")
#     logger.info("1. autogen-client package provides SimpleAutoGenAgent class")
#     logger.info("2. Helper functions like process_with_autogen() for easy usage")
#     logger.info("3. Works with any Unstract LLM adapter that has completion method")
#     logger.info("4. No AutoGen dependencies needed in prompt-service")
#     logger.info("")
#     logger.info("Future: This can be extended to create Celery chains with AutoGen")
#     logger.info("=" * 50)