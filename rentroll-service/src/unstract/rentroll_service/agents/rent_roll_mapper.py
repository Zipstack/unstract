"""RentRollMapper Agent

This agent maps user-defined JSON field names to actual field names found in rent roll documents.
It analyzes the document structure and creates a mapping between standardized user fields
and the document's specific terminology.
"""

import json
import os
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient


class RentRollMapper:
    """Agent that maps user JSON schema fields to rent roll document fields."""

    def __init__(self, llm_client: ChatCompletionClient):
        """Initialize the RentRollMapper agent.

        Args:
            llm_client: The LLM client for the agent to use
        """
        self.llm_client = llm_client
        self.agent = self._create_agent()

    def _create_agent(self) -> AssistantAgent:
        """Create and configure the RentRollMapper agent."""
        # Load system prompt
        system_prompt_path = os.path.join(
            os.path.dirname(__file__), "../prompts/rentroll_mapper_system.md"
        )
        with open(system_prompt_path, encoding="utf-8") as f:
            system_prompt = f.read()

        # Create agent with tools
        agent = AssistantAgent(
            name="RentRollMapper",
            model_client=self.llm_client,
            system_message=system_prompt,
            tools=self._create_tools(),
        )

        return agent

    def _create_tools(self) -> list[Any]:
        """Create tools for the RentRollMapper agent."""
        # This agent doesn't need tools - it just analyzes and maps
        return []

    async def map_fields(
        self, extracted_text_file: str, user_json_file: str
    ) -> dict[str, Any]:
        """Map user JSON fields to rent roll document fields.

        Args:
            extracted_text_file: Path to the extracted rent roll text file
            user_json_file: Path to the user's JSON schema file

        Returns:
            Dictionary mapping user fields to document fields
        """
        # Read the extracted rent roll content (first 2 pages only)
        rent_roll_content = self._read_first_two_pages(extracted_text_file)

        # Read the user's JSON schema
        with open(user_json_file, encoding="utf-8") as f:
            user_json = json.load(f)

        # Get just the keys from the user's JSON for mapping
        user_fields = self._extract_field_keys(user_json)
        user_json_schema = {field: "" for field in user_fields}

        # Load user prompt template
        user_prompt_path = os.path.join(
            os.path.dirname(__file__), "../prompts/rentroll_mapper_user.md"
        )
        with open(user_prompt_path, encoding="utf-8") as f:
            user_prompt_template = f.read()

        # Format the user prompt with actual data
        user_prompt = user_prompt_template.format(
            rent_roll_content=rent_roll_content,
            user_json_schema=json.dumps(user_json_schema, indent=2),
        )

        # Send task to agent
        task = TextMessage(content=user_prompt, source="user")

        # Get response from agent
        result = None
        response = await self.agent.on_messages([task], None)

        if response and isinstance(response.chat_message, TextMessage):
            # Try to extract JSON from the response
            result = self._extract_mapping_from_response(response.chat_message.content)

        if not result:
            raise ValueError("Failed to extract mapping from agent response")

        return result

    def _read_first_two_pages(self, file_path: str) -> str:
        """Read only the first two pages from the extracted rent roll file."""
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Split by form feed character (page separator)
        pages = content.split("\f")

        # Get first two pages (or all if less than 2)
        first_two_pages = pages[:2]

        # Join them back with form feed for clarity
        return "\f".join(first_two_pages)

    def _extract_field_keys(self, json_obj: Any, prefix: str = "") -> list[str]:
        """Recursively extract all field keys from a JSON structure.

        Args:
            json_obj: The JSON object to extract keys from
            prefix: Prefix for nested keys (e.g., "property.address")

        Returns:
            List of all field keys in dot notation
        """
        keys = []

        if isinstance(json_obj, dict):
            for key, value in json_obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                keys.append(full_key)
                # Recursively extract from nested objects
                if isinstance(value, dict):
                    keys.extend(self._extract_field_keys(value, full_key))
                elif isinstance(value, list) and value and isinstance(value[0], dict):
                    # For arrays of objects, get keys from the first object
                    keys.extend(self._extract_field_keys(value[0], full_key + "[0]"))

        return keys

    def _extract_mapping_from_response(self, response: str) -> dict[str, Any] | None:
        """Extract the JSON mapping from the agent's response."""
        try:
            # Look for JSON in the response
            import re

            # Try to find JSON block in the response
            json_match = re.search(r"```json\s*({.*?})\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                mapping = json.loads(json_str)
                return self._process_mapping_structure(mapping)

            # Try to parse the entire response as JSON
            # First, find where JSON might start
            json_start = response.find("{")
            if json_start != -1:
                json_end = response.rfind("}") + 1
                if json_end > json_start:
                    potential_json = response[json_start:json_end]
                    mapping = json.loads(potential_json)
                    return self._process_mapping_structure(mapping)

            return None
        except json.JSONDecodeError:
            return None

    def _process_mapping_structure(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Process mapping structure to handle both simple and array-based mappings.

        Args:
            mapping: Raw mapping from LLM response

        Returns:
            Processed mapping with proper structure
        """
        processed = {}

        for key, value in mapping.items():
            if isinstance(value, list) and len(value) > 0:
                # Handle array mappings like charge_codes
                if all(isinstance(item, dict) for item in value):
                    # This is an array of objects mapping
                    processed[key] = value
                else:
                    # This might be a simple array, treat as regular mapping
                    processed[key] = value
            else:
                # Regular field mapping
                processed[key] = value

        return processed
