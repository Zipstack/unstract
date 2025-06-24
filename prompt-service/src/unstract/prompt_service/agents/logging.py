"""
Enhanced logging for agents.
This module provides utilities for logging agent activities, conversations, and function calls.
It is designed to work with any type of agent and can be extended for different agent frameworks.
"""
import json
import logging
from typing import Any, Dict, Optional, List, Callable, Union
import os
from datetime import datetime

# Support for AutoGen if available
try:
    from autogen_agentchat.agents import Agent as AutoGenAgent
    from autogen_core import EVENT_LOGGER_NAME
    AUTOGEN_AVAILABLE = True
except ImportError:
    # Define placeholder for type hints if AutoGen not available
    AutoGenAgent = Any  # type: ignore
    EVENT_LOGGER_NAME = "autogen_core"
    AUTOGEN_AVAILABLE = False

# Configure agent logging
agent_logger = logging.getLogger("unstract.agents")


class AgentLoggerConfig:
    """Framework-agnostic logging configuration for agents"""
    
    @staticmethod
    def setup_logging(
        log_level: int = logging.INFO, 
        log_to_console: bool = True,
        log_to_file: bool = False,
        log_directory: Optional[str] = None,
        custom_loggers: Optional[List[logging.Logger]] = None,
        log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ) -> None:
        """
        Set up logging for agents across any framework.
        
        Args:
            log_level: Logging level (default: INFO)
            log_to_console: Whether to log to console
            log_to_file: Whether to log to file
            log_directory: Directory for log files
            custom_loggers: Optional additional loggers to configure
            log_format: Format string for log messages
        """
        # Prepare list of loggers to configure
        loggers_to_configure = [agent_logger]
        
        # Add AutoGen logger if available
        if AUTOGEN_AVAILABLE:
            autogen_logger = logging.getLogger(EVENT_LOGGER_NAME)
            loggers_to_configure.append(autogen_logger)
        
        # Add any custom loggers
        if custom_loggers:
            loggers_to_configure.extend(custom_loggers)
        
        # Create formatter
        formatter = logging.Formatter(log_format)
        
        # Configure each logger
        for logger in loggers_to_configure:
            # Clear existing handlers
            logger.handlers.clear()
            
            # Set log level
            logger.setLevel(log_level)
            
            # Console handler
            if log_to_console:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(log_level)
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)
            
            # File handler
            if log_to_file and log_directory:
                os.makedirs(log_directory, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                log_file = os.path.join(log_directory, f'agent_log_{timestamp}.log')
                
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(log_level)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)


class AgentConversationLogger:
    """Framework-agnostic logger for agent conversations and activities"""
    
    def __init__(self, 
                 conversation_id: str, 
                 log_level: int = logging.INFO,
                 include_message_content: bool = True,
                 agent_type: str = "generic",
                 max_content_length: int = 1000):
        """
        Initialize the conversation logger.
        
        Args:
            conversation_id: ID for the conversation
            log_level: Logging level
            include_message_content: Whether to include full message content
            agent_type: Type of agent being logged ("autogen", "langchain", etc.)
            max_content_length: Maximum length for content truncation
        """
        self.conversation_id = conversation_id
        self.log_level = log_level
        self.include_message_content = include_message_content
        self.agent_type = agent_type
        self.max_content_length = max_content_length
        self.conversation_log = []
        
    def log_message(self, sender: str, receiver: str, message: Any) -> None:
        """
        Log a message between agents.
        
        Args:
            sender: Sender agent name
            receiver: Receiver agent name
            message: Message content (can be dict, string, or any other format depending on agent framework)
        """
        log_entry = {
            "type": "message",
            "timestamp": datetime.now().isoformat(),
            "conversation_id": self.conversation_id,
            "sender": sender,
            "receiver": receiver
        }
        
        if self.include_message_content:
            # Clean the message for logging (avoid logging huge content)
            safe_message = self._clean_content_for_logging(message)
            log_entry["message"] = safe_message
            
        self.conversation_log.append(log_entry)
        
        # Log to the logger
        agent_logger.log(
            self.log_level, 
            f"[{sender} -> {receiver}] {self._format_content_summary(message)}"
        )
        
    def log_function_call(self, agent_name: str, function_name: str, 
                          arguments: Any, result: Any) -> None:
        """
        Log a function call by an agent.
        
        Args:
            agent_name: Name of the agent making the call
            function_name: Name of the function
            arguments: Function arguments (dict or any other format)
            result: Function result (any format)
        """
        log_entry = {
            "type": "function_call",
            "timestamp": datetime.now().isoformat(),
            "conversation_id": self.conversation_id,
            "agent": agent_name,
            "function_name": function_name
        }
        
        # Add arguments with appropriate cleaning
        log_entry["arguments"] = self._clean_content_for_logging(arguments)
        
        # Clean and add the result
        log_entry["result_summary"] = self._clean_content_for_logging(result)
            
        self.conversation_log.append(log_entry)
        
        # Format arguments for logging
        args_str = str(arguments)
        if isinstance(arguments, dict):
            try:
                args_str = json.dumps(arguments, default=str)
            except Exception:
                pass
        
        # Log to the logger
        agent_logger.log(
            self.log_level,
            f"[FUNCTION CALL] {agent_name} called {function_name}({args_str}) -> {self._format_content_summary(result)}"
        )
    
    def log_thinking(self, agent_name: str, thinking: str) -> None:
        """
        Log an agent's thinking process.
        
        Args:
            agent_name: Name of the agent
            thinking: Thinking content
        """
        # Truncate long thinking content
        truncated_thinking = thinking
        if len(thinking) > self.max_content_length:
            truncated_thinking = thinking[:self.max_content_length] + "..."
            
        log_entry = {
            "type": "thinking",
            "timestamp": datetime.now().isoformat(),
            "conversation_id": self.conversation_id,
            "agent": agent_name,
            "thinking": truncated_thinking
        }
        
        self.conversation_log.append(log_entry)
        
        # Log to the logger
        preview_len = min(100, self.max_content_length)
        agent_logger.log(
            self.log_level,
            f"[THINKING] {agent_name}: {thinking[:preview_len]}..." if len(thinking) > preview_len else thinking
        )
    
    def log_event(self, event_type: str, agent_name: str, data: Any) -> None:
        """
        Log a generic agent event.
        
        Args:
            event_type: Type of event
            agent_name: Name of the agent
            data: Event data
        """
        log_entry = {
            "type": "event",
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "conversation_id": self.conversation_id,
            "agent": agent_name,
            "data": self._clean_content_for_logging(data)
        }
        
        self.conversation_log.append(log_entry)
        
        # Log to the logger
        agent_logger.log(
            self.log_level,
            f"[EVENT:{event_type}] {agent_name}: {self._format_content_summary(data)}"
        )
    
    def export_conversation_log(self) -> List[Dict[str, Any]]:
        """
        Export the conversation log.
        
        Returns:
            The full conversation log
        """
        return self.conversation_log
    
    def _clean_content_for_logging(self, content: Any) -> Any:
        """
        Clean content for logging by truncating large strings, handling special cases.
        Works with any content type from any agent framework.
        
        Args:
            content: Original content of any type
            
        Returns:
            Cleaned content suitable for logging
        """
        # Handle different content types
        if isinstance(content, str):
            # Simple string truncation
            if len(content) > self.max_content_length:
                return content[:self.max_content_length] + "... [truncated]"
            return content
            
        elif isinstance(content, dict):
            # Process dictionary fields
            result = {}
            for key, value in content.items():
                # Truncate string values that are too long
                if isinstance(value, str) and len(value) > self.max_content_length:
                    result[key] = value[:self.max_content_length] + "... [truncated]"
                # Handle nested dictionaries recursively
                elif isinstance(value, dict):
                    result[key] = self._clean_content_for_logging(value)
                # Keep special fields like function calls intact
                elif key == "function_call":
                    result[key] = value
                # Handle common data fields generically
                elif key in ["content", "text", "extracted_text", "data", "result"]:
                    if isinstance(value, str) and len(value) > self.max_content_length:
                        result[key] = value[:self.max_content_length] + "... [truncated]"
                    else:
                        result[key] = value
                # Default handling
                else:
                    result[key] = value
            return result
            
        elif isinstance(content, list):
            # For lists, process each item separately but limit max items
            max_items = 20  # Reasonable limit for logging
            if len(content) > max_items:
                return [self._clean_content_for_logging(item) for item in content[:max_items]] + ["... (truncated)"]
            return [self._clean_content_for_logging(item) for item in content]
            
        # Default case - return as is
        return content
    
    def _format_content_summary(self, content: Any) -> str:
        """
        Format a content summary for logging.
        Creates a brief readable summary for any content type.
        
        Args:
            content: Content to summarize
            
        Returns:
            Summarized content as string
        """
        # Handle different content types
        if content is None:
            return "None"
            
        if isinstance(content, str):
            # Truncate and return string
            max_preview = 50
            if len(content) > max_preview:
                return f"{content[:max_preview]}..."
            return content
            
        elif isinstance(content, dict):
            # Handle special message formats first
            if "function_call" in content:
                function_name = content["function_call"].get("name", "unknown")
                return f"Function call: {function_name}"
                
            # Handle common content fields
            for field in ["content", "text", "extracted_text", "message", "summary"]:
                if field in content and isinstance(content[field], str):
                    text = content[field]
                    if len(text) > 50:
                        return f"{field}: '{text[:50]}...'"
                    return f"{field}: '{text}'"
                    
            # Default dict handling - show keys
            keys = list(content.keys())
            if len(keys) > 5:
                return f"Dict with keys: {', '.join(keys[:5])}... ({len(keys)} total)"
            return f"Dict with keys: {', '.join(keys)}"
            
        elif isinstance(content, list):
            # Handle lists - show length and sample
            if not content:
                return "Empty list"
            if len(content) == 1:
                return f"List with 1 item: {self._format_content_summary(content[0])}"
            return f"List with {len(content)} items"
            
        # Default handling
        return str(content)

class AgentCallbacks:
    """
    Callback handlers for agents to monitor conversations and events
    """
    
    @staticmethod
    def create_message_callback(conversation_logger: AgentConversationLogger, agent_name: str) -> Callable:
        """Create an message callback"""
        if not AUTOGEN_AVAILABLE:
            # Return a no-op function if AutoGen isn't available
            return lambda *args, **kwargs: None
            
        def on_autogen_message(recipient: AutoGenAgent, message: Dict[str, Any]) -> None:
            conversation_logger.log_message(
                sender=agent_name,
                receiver=recipient.name if hasattr(recipient, 'name') else "unknown",
                message=message
            )
        return on_autogen_message

    @staticmethod
    def create_function_call_callback(conversation_logger: AgentConversationLogger, agent_name: str) -> Callable:
        """Create a function call callback"""
        if not AUTOGEN_AVAILABLE:
            return lambda *args, **kwargs: None
            
        def on_autogen_function_call(function_name: str, arguments: Dict[str, Any], result: Any) -> None:
            conversation_logger.log_function_call(
                agent_name=agent_name,
                function_name=function_name,
                arguments=arguments,
                result=result
            )
        return on_autogen_function_call
        
    @staticmethod
    def create_thinking_callback(conversation_logger: AgentConversationLogger, agent_name: str) -> Callable:
        """Create a thinking callback"""
        if not AUTOGEN_AVAILABLE:
            return lambda *args, **kwargs: None
            
        def on_autogen_thinking(thinking: str) -> None:
            conversation_logger.log_thinking(
                agent_name=agent_name,
                thinking=thinking
            )
        return on_autogen_thinking


# Initialize logging with default configuration
AgentLoggerConfig.setup_logging()
