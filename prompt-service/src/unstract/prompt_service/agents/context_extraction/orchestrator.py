"""
Context Extraction Orchestrator.
Provides the main interface for using the context extraction agent.
"""
from typing import Any, Dict, List, Optional
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from autogen_agentchat.agents import UserProxyAgent
from autogen_core import EVENT_LOGGER_NAME
from autogen_ext.models.openai import OpenAIChatCompletionClient

from unstract.prompt_service.agents.context_extraction.agent import ContextExtractionAgent
from unstract.prompt_service.agents.context_extraction.tools.x2text_tool import X2TextTool
from unstract.prompt_service.agents.logging import AgentLoggerConfig, AgentConversationLogger, AgentCallbacks
from unstract.prompt_service.constants import ExecutionSource
from unstract.prompt_service.constants import IndexingConstants as IKeys
from unstract.prompt_service.exceptions import ExtractionError
from unstract.prompt_service.helpers.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.prompt_service.utils.file_utils import FileUtils
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.utils import ToolUtils
from unstract.sdk.utils.common_utils import log_elapsed
from unstract.sdk.x2txt import X2Text
logger = logging.getLogger(__name__)
autogen_logger = logging.getLogger(EVENT_LOGGER_NAME)

class AgentyContextExtractorV2:
    """Agentic Context Extractor v2 implementation using AutoGen."""
    
    def __init__(self, platform_key: str, model_config: Optional[Dict[str, Any]] = None, 
                log_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the extractor with configuration.
        
        Args:
            platform_key: Platform key for authentication.
            model_config: Optional model configuration.
            log_config: Optional logging configuration.
        """
        self.platform_key = platform_key
        self.model_config = model_config or {
            "model": "gpt-4o",  # Default model
            "temperature": 0.1
        }
        
        # Set up logging configuration
        self.log_config = log_config or {}
        self.enable_logging = self.log_config.get("enable_logging", True)
        self.log_to_file = self.log_config.get("log_to_file", False)
        self.log_level = self.log_config.get("log_level", logging.INFO)
        self.log_directory = self.log_config.get("log_directory", "./logs/agent_logs")
        
        # Configure agent logging
        if self.enable_logging:
            AgentLoggerConfig.setup_logging(
                log_level=self.log_level,
                log_to_console=True,
                log_to_file=self.log_to_file,
                log_directory=self.log_directory if self.log_to_file else None
            )
            
            logger.info("Initialized AgentyContextExtractorV2 with enhanced logging")
            autogen_logger.setLevel(self.log_level)
        
    @log_elapsed(operation="AGENTIC_EXTRACTION_V2")
    def extract_context(
        self,
        x2text_instance_id: str,
        file_path: str,
        run_id: str,
        output_file_path: Optional[str] = None,
        enable_highlight: bool = False,
        usage_kwargs: Dict[Any, Any] = {},
        tags: Optional[List[str]] = None,
        execution_source: Optional[str] = None,
        tool_exec_metadata: Optional[Dict[str, Any]] = None,
        execution_run_data_folder: Optional[str] = None,
    ) -> str:
        """
        Extract context from a document using an agent-based approach.
        
        Args:
            x2text_instance_id: ID of the X2Text instance to use.
            file_path: Path to the input document.
            run_id: ID of the current run.
            output_file_path: Optional path to save the output.
            enable_highlight: Whether to enable highlighting.
            usage_kwargs: Usage information for tracking.
            tags: Optional tags for the document.
            execution_source: Source of execution.
            tool_exec_metadata: Metadata for tool execution.
            execution_run_data_folder: Folder for execution data.
            
        Returns:
            The extracted text from the document.
            
        Raises:
            ExtractionError: If extraction fails.
        """
        try:
            # Initialize X2Text
            util = PromptServiceBaseTool(platform_key=self.platform_key)
            x2text = X2Text(
                tool=util, 
                adapter_instance_id=x2text_instance_id, 
                usage_kwargs=usage_kwargs
            )
            
            # Get filesystem instance
            fs = FileUtils.get_fs_instance(execution_source=execution_source)
            
            # Initialize the X2Text tool
            x2text_tool = X2TextTool(x2text_instance=x2text, fs=fs)
            
            # Initialize OpenAI model client
            model_client = OpenAIChatCompletionClient(**self.model_config)
            
            # Generate a conversation ID for this extraction run
            conversation_id = f"extract-{run_id}-{uuid.uuid4()}"
            extract_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Log extraction run start
            logger.info(f"Starting extraction run {conversation_id} for file: {file_path}")
            
            # Create the context extraction agent with logging enabled
            extraction_agent = ContextExtractionAgent(
                x2text_tool=x2text_tool,
                model_client=model_client,
                name="context_extractor",
                conversation_id=conversation_id,
                enable_logging=self.enable_logging,
                log_level=self.log_level
            )
            
            # Create user proxy agent to initiate the conversation
            user_proxy = UserProxyAgent(
                name="user_proxy",
                human_input_mode="NEVER"  # No human input needed for this process
            )
            
            # Register proxied user agent with logging if enabled
            if self.enable_logging:
                # Set up conversation logger for user proxy
                user_logger = AgentConversationLogger(
                    conversation_id=conversation_id,
                    log_level=self.log_level
                )
                
                # Create and register message callback
                on_message = AgentCallbacks.create_message_callback(
                    conversation_logger=user_logger,
                    agent_name=user_proxy.name
                )
                
                user_proxy.register_on_message_callback(on_message)
            
            # Start the conversation with a task
            initial_message = f"Extract the text content from the document at path: {file_path}"
            if output_file_path:
                initial_message += f" and save to: {output_file_path}"
            
            # Track start time for performance monitoring
            start_time = datetime.now()
            
            try:
                # Start the conversation between agents
                result = user_proxy.initiate_chat(
                    extraction_agent,
                    message=initial_message,
                    clear_history=True
                )
                
                # Calculate duration for performance tracking
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"Extraction completed in {duration:.2f} seconds")
            except Exception as e:
                # Log the error with enhanced details
                error_msg = f"Error during extraction: {str(e)}"
                logger.error(error_msg)
                
                # Log conversation details if available
                if self.enable_logging and hasattr(extraction_agent, "get_conversation_log"):
                    try:
                        # Get the conversation log up to the error point
                        conversation_logs = extraction_agent.get_conversation_log()
                        logger.error(f"Conversation state at failure: {json.dumps(conversation_logs, indent=2)}")
                    except Exception as log_error:
                        logger.error(f"Failed to retrieve conversation logs: {str(log_error)}")
                
                # Re-raise with more context
                raise ExtractionError(
                    f"Agent-based extraction failed: {error_msg}", 
                    code=500
                ) from e
                
            # Collect logs if enabled
            if self.enable_logging and self.log_to_file and execution_run_data_folder:
                # Create logs directory if it doesn't exist
                logs_path = Path(execution_run_data_folder) / "agent_logs"
                os.makedirs(logs_path, exist_ok=True)
                
                # Export conversation logs
                conversation_logs = extraction_agent.get_conversation_log()
                log_file = logs_path / f"conversation_{extract_timestamp}.json"
                
                with open(log_file, "w") as f:
                    json.dump(conversation_logs, f, indent=2)
                
                logger.info(f"Saved conversation logs to {log_file}")
            
            # Get the extracted text from the function call result
            for msg in reversed(extraction_agent.chat_messages[user_proxy]):
                if "function_call" in msg and msg["function_call"].get("name") == "process_document":
                    # Function was called, get the result
                    function_result = json.loads(msg.get("content", "{}"))
                    extracted_text = function_result.get("extracted_text", "")
                    
                    # Update execution metadata if necessary
                    if (execution_source == ExecutionSource.TOOL.value and 
                        tool_exec_metadata is not None and 
                        execution_run_data_folder is not None and 
                        "metadata" in function_result):
                        
                        metadata = function_result["metadata"]
                        if "whisper_hash" in metadata:
                            metadata_to_save = {IKeys.WHISPER_HASH: metadata["whisper_hash"]}
                            for key, value in metadata_to_save.items():
                                tool_exec_metadata[key] = value
                                
                            # Add agent metadata to track agent performance
                            if self.enable_logging:
                                metadata_to_save["agent_conversation_id"] = conversation_id
                                metadata_to_save["agent_duration_seconds"] = duration
                                
                            metadata_path = str(Path(execution_run_data_folder) / IKeys.METADATA_FILE)
                            ToolUtils.dump_json(
                                file_to_dump=metadata_path,
                                json_to_dump=metadata_to_save,
                                fs=fs,
                            )
                    
                    return extracted_text
        
            # If we get here, something went wrong
            raise ExtractionError("Failed to extract text: no result from extraction agent", code=500)
            
        except AdapterError as e:
            msg = f"Error from text extractor '{x2text.x2text_instance.get_name()}'. "
            msg += str(e)
            code = e.status_code if hasattr(e, 'status_code') and e.status_code != -1 else 500
            raise ExtractionError(msg, code=code) from e
        except Exception as e:
            msg = f"Error during agentic context extraction: {str(e)}"
            logger.error(msg)
            raise ExtractionError(msg, code=500) from e
