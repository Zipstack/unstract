import os
import tempfile
from typing import List, Dict, Any, Optional
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
from tools.append_page import append_page_to_output, clear_output_file
from tools.line_no_prefixer import prefix_lines_with_numbers
import logging
logger = logging.getLogger(__name__)

class RentRollLocatorAgent:
    def __init__(self, llm_client: OpenAIChatCompletionClient):
        self.llm_client = llm_client
        self.agent = self._create_agent()
    
    def _create_agent(self) -> AssistantAgent:
        # Read the system prompt
        system_prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/rentroll_locator_system.md")
        with open(system_prompt_path, 'r') as f:
            system_prompt = f.read()
        
        # Create tools for the agent
        tools = self._create_tools()
        
        # Create the agent
        agent = AssistantAgent(
            name="RentRollLocator",
            model_client=self.llm_client,
            system_message=system_prompt,
            tools=tools
        )
        
        return agent
    
    def _create_tools(self) -> List[Any]:
        """Create tools for the RentRollLocator agent."""
        
        # The LLM only needs to make decisions, no tools required for content extraction
        # Content extraction will be handled programmatically based on LLM decisions
        return []
    
    async def process_file(self, text_file_name: str, output_file_name: str) -> str:
        """
        Process a text file by analyzing each page individually for rent roll data.
        
        Args:
            text_file_name: Path to the input text file
            output_file_name: Path where extracted rent roll pages will be saved
        
        Returns:
            Path to the extracted text file
        """
        # Step 1: Add line numbers to the input file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='_numbered.txt', delete=False) as temp_file:
            numbered_file = temp_file.name
        
        logger.info(f"Adding line numbers to input file...")
        line_prefix_result = prefix_lines_with_numbers(text_file_name, numbered_file)
        logger.info(f"Line numbering result: {line_prefix_result}")
        
        # Read the numbered file and split into pages
        try:
            with open(numbered_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading numbered file: {e}")
            # Clean up temp file
            if os.path.exists(numbered_file):
                os.unlink(numbered_file)
            return output_file_name
        
        pages = content.split('\f')
        total_pages = len(pages)
        logger.info(f"Processing {total_pages} pages...")
        
        # Read the user prompt
        user_prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/rentroll_locator_user.md")
        with open(user_prompt_path, 'r') as f:
            user_prompt_template = f.read()
        
        # Clear the output file first
        clear_result = clear_output_file(output_file_name)
        logger.info(f"Cleared output file: {clear_result}")
        
        pages_with_rentroll = 0
        
        # Process each page individually
        for page_num, page_content in enumerate(pages, 1):
            if not page_content.strip():  # Skip empty pages
                continue
                
            logger.info(f"\n--- Analyzing Page {page_num} ---")
            
            # Create a message for this specific page
            page_message_content = f"""{user_prompt_template}

## Current Task
Analyze PAGE {page_num} of {total_pages} from file: {text_file_name}

## Page Content:
{page_content}

## Your Task:
Analyze this page content and determine if it contains rent roll data. Respond ONLY with the required JSON format."""
            
            page_message = TextMessage(content=page_message_content, source="user")
            
            # Analyze this page with the agent
            try:
                response = await self.agent.on_messages([page_message], cancellation_token=None)
                
                if response.chat_message and hasattr(response.chat_message, 'content'):
                    analysis_content = response.chat_message.content
                    logger.info(f"LLM Decision: {analysis_content}")
                    
                    # Parse the LLM response to extract the decision
                    decision = self._parse_llm_decision(analysis_content)
                    
                    if decision == "YES":
                        # Programmatically append the original page content (preserving formatting)
                        append_result = append_page_to_output(output_file_name, page_content, page_num)
                        pages_with_rentroll += 1
                        logger.info(f"✅ Page {page_num} contains rent roll data - EXTRACTED PROGRAMMATICALLY")
                        logger.info(f"   {append_result}")
                    else:
                        logger.info(f"❌ Page {page_num} does not contain rent roll data - SKIPPED")
                
            except Exception as e:
                logger.error(f"Error analyzing page {page_num}: {e}")
                continue
        
        logger.info(f"\n=== EXTRACTION SUMMARY ===")
        logger.info(f"Total pages processed: {total_pages}")
        logger.info(f"Pages with rent roll data: {pages_with_rentroll}")
        logger.info(f"Output saved to: {output_file_name}")
        
        # Clean up temporary numbered file
        if os.path.exists(numbered_file):
            os.unlink(numbered_file)
            logger.info(f"Cleaned up temporary file: {numbered_file}")
        
        return output_file_name
    
    def _parse_llm_decision(self, llm_response: str) -> str:
        """
        Parse the LLM response to extract YES/NO decision.
        
        Args:
            llm_response: The full response from the LLM
            
        Returns:
            "YES" or "NO" based on the LLM's decision
        """
        try:
            # Look for JSON in the response
            import json
            import re
            
            # Try to find JSON block in the response
            json_match = re.search(r'```json\s*({.*?})\s*```', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                parsed = json.loads(json_str)
                return parsed.get('detection_result', 'NO').upper()
            
            # Fallback: look for direct JSON
            json_match = re.search(r'{.*?"detection_result".*?}', llm_response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return parsed.get('detection_result', 'NO').upper()
            
            # Fallback: look for YES/NO in the text
            if '"detection_result": "YES"' in llm_response or '"detection_result":"YES"' in llm_response:
                return "YES"
            elif '"detection_result": "NO"' in llm_response or '"detection_result":"NO"' in llm_response:
                return "NO"
            
            # Default to NO if can't parse
            return "NO"
            
        except Exception:
            # If parsing fails, default to NO
            return "NO"