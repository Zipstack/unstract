"""
Context Extraction Agent.
An AutoGen agent specialized in extracting context from documents using X2Text.
"""
from typing import Any, Dict, Optional, Callable
import json
import logging
import uuid

from autogen_agentchat.agents import ConversableAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from unstract.prompt_service.agents.context_extraction.tools.x2text_tool import X2TextTool
from unstract.prompt_service.agents.logging import AgentConversationLogger, AgentCallbacks

logger = logging.getLogger(__name__)

class ContextExtractionAgent(ConversableAgent):
    """AutoGen agent specialized for context extraction."""

    def __init__(
        self,
        x2text_tool: X2TextTool,
        model_client: Any,
        name: str = "context_extraction_agent",
        system_message: str = "You are a specialized agent for extracting text context from documents.",
        llm_config: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        enable_logging: bool = True,
        log_level: int = logging.INFO,
        **kwargs,
    ):
        """
        Initialize the context extraction agent.
        
        Args:
            x2text_tool: Tool to use for document processing.
            model_client: LLM client to use for agent reasoning.
            name: Name of the agent.
            system_message: System message to use for the agent.
            llm_config: Configuration for the LLM.
            conversation_id: ID for the conversation, will auto-generate if not provided.
            enable_logging: Whether to enable enhanced logging.
            log_level: Log level for agent activities.
            **kwargs: Additional arguments to pass to the ConversableAgent.
        """
        self.x2text_tool = x2text_tool
        self.enable_logging = enable_logging
        self.conversation_id = conversation_id or f"context-extraction-{uuid.uuid4()}"
        
        # Set up conversation logger for this agent
        if self.enable_logging:
            self.conversation_logger = AgentConversationLogger(
                conversation_id=self.conversation_id,
                log_level=log_level,
                agent_type="autogen",  # Specify the agent framework type
                max_content_length=2000  # Increase content length for document extraction
            )
            
            # Prepare callbacks for logging
            self._setup_logging_callbacks()
        
        # Create custom function for X2Text processing
        def process_document(input_file_path: str, output_file_path: Optional[str] = None, 
                            enable_highlight: bool = False, tags: Optional[list[str]] = None) -> Dict[str, Any]:
            """Process document with X2Text extraction."""
            logger.info(f"Processing document: {input_file_path}")
            result = self.x2text_tool.process_document(
                input_file_path=input_file_path,
                output_file_path=output_file_path,
                enable_highlight=enable_highlight,
                tags=tags
            )
            
            # Log function call if logging is enabled
            if self.enable_logging:
                self.conversation_logger.log_function_call(
                    agent_name=name,
                    function_name="process_document",
                    arguments={
                        "input_file_path": input_file_path,
                        "output_file_path": output_file_path,
                        "enable_highlight": enable_highlight,
                        "tags": tags
                    },
                    result=result
                )
                
            return result
        
        # Configure agent with the X2Text processing tool
        function_map = {
            "process_document": process_document
        }

        # Complete system message
        complete_system_message = f"""
{system_message}

You have access to a document processing tool through the process_document function.
When given a file path, you should:
1. Process the document to extract its text content
2. Analyze the extracted text to identify key information
3. Return the extracted text

Always use the process_document function to extract text from documents.
"""
        
        # Initialize the base ConversableAgent
        super().__init__(
            name=name,
            system_message=complete_system_message,
            function_map=function_map,
            model=model_client,
            **kwargs
        )
        
        if self.enable_logging:
            logger.info(f"Initialized {name} agent with conversation ID: {self.conversation_id}")
    
    def _setup_logging_callbacks(self) -> None:
        """Set up callbacks for logging agent activities."""
        # Create callbacks for messages
        on_message = AgentCallbacks.create_message_callback(
            conversation_logger=self.conversation_logger,
            agent_name=self.name
        )
        
        # Create callback for thinking
        on_thinking = AgentCallbacks.create_thinking_callback(
            conversation_logger=self.conversation_logger,
            agent_name=self.name
        )
        
        # Create callback for function calls
        on_function_call = AgentCallbacks.create_function_call_callback(
            conversation_logger=self.conversation_logger,
            agent_name=self.name
        )
        
        # Register callbacks with the agent
        self.register_on_message_callback(on_message)
        
        # Check if the agent supports thinking callbacks (not all agents do)
        if hasattr(self, "register_thinking_callback"):
            self.register_thinking_callback(on_thinking)
            
        # Register function call callback if supported
        if hasattr(self, "register_function_call_callback"):
            self.register_function_call_callback(on_function_call)
    
    def get_conversation_log(self) -> Dict[str, Any]:
        """Get the conversation log for this agent.
        
        Returns:
            Dict with conversation ID and log entries
        """
        if not self.enable_logging:
            return {"conversation_id": self.conversation_id, "log": []}
            
        return {
            "conversation_id": self.conversation_id,
            "log": self.conversation_logger.export_conversation_log()
        }
