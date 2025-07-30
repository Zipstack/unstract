"""RentRollExtractor Agent

This agent extracts complete tabular rent roll data from documents and outputs it in
Tab-Separated Values (TSV) format using provided field mappings.
"""

import json
import os
import re

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient


class RentRollExtractorAgent:
    """Agent that extracts rent roll data to TSV format using field mappings."""

    def __init__(self, llm_client: ChatCompletionClient):
        """Initialize the RentRollExtractor agent.

        Args:
            llm_client: The LLM client for the agent to use
        """
        self.llm_client = llm_client
        self.agent = self._create_agent()

    def _create_agent(self) -> AssistantAgent:
        """Create and configure the RentRollExtractor agent."""
        # Load system prompt
        system_prompt_path = os.path.join(
            os.path.dirname(__file__), "../prompts/rentroll_extractor_system.md"
        )
        with open(system_prompt_path, encoding="utf-8") as f:
            system_prompt = f.read()

        # Create agent without tools (uses only LLM)
        agent = AssistantAgent(
            name="RentRollExtractor",
            model_client=self.llm_client,
            system_message=system_prompt,
        )

        return agent

    async def extract_data(
        self, extracted_text_file: str, field_mapping_file: str, output_tsv_file: str
    ) -> str:
        """Extract rent roll data from text file using field mapping and save as TSV.

        Args:
            extracted_text_file: Path to the extracted rent roll text file
            field_mapping_file: Path to the JSON field mapping file
            output_tsv_file: Path where TSV output will be saved

        Returns:
            Path to the generated TSV file
        """
        print("Starting data extraction...")
        print(f"Input file: {extracted_text_file}")
        print(f"Field mapping: {field_mapping_file}")
        print(f"Output TSV: {output_tsv_file}")

        # Read the extracted text file
        try:
            with open(extracted_text_file, encoding="utf-8") as f:
                rent_roll_text = f.read()
        except Exception as e:
            raise ValueError(f"Error reading extracted text file: {e}")

        # Read the field mapping
        try:
            with open(field_mapping_file, encoding="utf-8") as f:
                field_mapping = json.load(f)
        except Exception as e:
            raise ValueError(f"Error reading field mapping file: {e}")

        # Filter out null mappings (fields not present in document)
        filtered_mapping = {k: v for k, v in field_mapping.items() if v is not None}

        # Filter out parent array fields when array element fields exist
        filtered_mapping = self._filter_array_parent_fields(filtered_mapping)

        if not filtered_mapping:
            raise ValueError(
                "No valid field mappings found. All fields are mapped to null."
            )

        print(f"Processing {len(filtered_mapping)} mapped fields...")

        # Check if content needs to be chunked
        max_chunk_size = 15000  # Conservative limit for context

        if len(rent_roll_text) <= max_chunk_size:
            # Process in single chunk
            tsv_content = await self._extract_single_chunk(
                rent_roll_text, filtered_mapping
            )
        else:
            # Process in multiple chunks
            tsv_content = await self._extract_multiple_chunks(
                rent_roll_text, filtered_mapping, max_chunk_size
            )

        # Save TSV output
        try:
            with open(output_tsv_file, "w", encoding="utf-8") as f:
                f.write(tsv_content)
            print(f"TSV data saved to: {output_tsv_file}")
        except Exception as e:
            raise ValueError(f"Error writing TSV file: {e}")

        # Normalize tab alignment in array field rows
        # print("Running simplified TSV normalizer...")
        # self.tsv_array_tab_normalizer(output_tsv_file)

        # Count extracted rows (after normalization)
        with open(output_tsv_file, encoding="utf-8") as f:
            normalized_content = f.read()
        row_count = len(normalized_content.strip().split("\n")) - 1  # Subtract header row
        print(f"Extracted {row_count} data rows")

        return output_tsv_file

    def _filter_array_parent_fields(
        self, field_mapping: dict[str, str]
    ) -> dict[str, str]:
        """Filter out parent array fields when array element fields exist.

        For example, if we have:
        - "charge_codes": "Charge Schedules"
        - "charge_codes[0].charge_code": "Type"
        - "charge_codes[0].value": "Monthly Amt"

        Then remove "charge_codes" from the mapping since the array element fields exist.

        Args:
            field_mapping: Original field mapping

        Returns:
            Filtered field mapping without parent array fields
        """
        # Identify array element fields (contain bracket notation)
        array_element_fields = {}
        for field_name in field_mapping.keys():
            if "[" in field_name and "]" in field_name:
                # Extract parent array name (e.g., "charge_codes" from "charge_codes[0].charge_code")
                parent_name = field_name.split("[")[0]
                if parent_name not in array_element_fields:
                    array_element_fields[parent_name] = []
                array_element_fields[parent_name].append(field_name)

        # Filter out parent array fields that have element fields
        filtered_mapping = {}
        for field_name, field_value in field_mapping.items():
            # If this is a parent array field that has element fields, skip it
            if field_name in array_element_fields:
                print(
                    f"Filtering out parent array field '{field_name}' (has element fields: {array_element_fields[field_name]})"
                )
                continue
            else:
                filtered_mapping[field_name] = field_value

        return filtered_mapping

    def _get_array_fields_from_mapping(self, field_mapping: dict[str, str]) -> list[str]:
        """Extract array field names from field mapping.

        Args:
            field_mapping: The field mapping dictionary

        Returns:
            List of array field names (e.g., ['charge_codes[0].charge_code', 'charge_codes[0].value'])
        """
        array_fields = []
        for field_name in field_mapping.keys():
            if "[" in field_name and "]" in field_name:
                array_fields.append(field_name)
        return sorted(array_fields)

    def _generate_array_row_note(
        self, array_fields: list[str], field_mapping: dict[str, str]
    ) -> str:
        """Generate dynamic array row instructions based on actual field mapping.

        Args:
            array_fields: List of array field names from mapping
            field_mapping: The complete field mapping dictionary

        Returns:
            Formatted instruction text for array rows
        """
        if not array_fields:
            return "**IMPORTANT**: No array fields detected in the field mapping. Do not create any array rows."

        # Build the instruction text
        note_lines = [
            "**IMPORTANT**: For array rows containing array data, ONLY include these columns:",
            "- Column 1: `line_nos` (always)",
        ]

        # Add each array field as a column with document column name
        for i, field_name in enumerate(array_fields, start=2):
            document_column = field_mapping.get(field_name, field_name)
            note_lines.append(
                f"- Column {i}: The value from document column `{document_column}` (mapped to `{field_name}`)"
            )

        note_lines.extend(
            [
                "",
                "**IMPORTANT CASES:**",
                "- **Parent row with first array element**: If the first array element appears on the same line as the parent unit data, include BOTH the parent data AND the first array element values in the same TSV row.",
                "- **Separate array rows**: For additional array elements (2nd, 3rd, etc.) that appear on separate lines, create separate array rows with ONLY line_nos + array field values.",
                "",
                "No other columns should appear in separate array rows. Do not include unit_ref_id, tenant_name, or any other non-array fields in the separate array rows.",
            ]
        )

        return "\n".join(note_lines)

    async def _extract_single_chunk(
        self, rent_roll_text: str, field_mapping: dict[str, str]
    ) -> str:
        """Extract data from a single text chunk."""
        # Load user prompt template
        user_prompt_path = os.path.join(
            os.path.dirname(__file__), "../prompts/rentroll_extractor_user.md"
        )
        with open(user_prompt_path, encoding="utf-8") as f:
            user_prompt_template = f.read()

        # Generate dynamic array row instructions
        array_fields = self._get_array_fields_from_mapping(field_mapping)
        note_on_array_rows = self._generate_array_row_note(array_fields, field_mapping)

        # Format the user prompt with actual data
        user_prompt = user_prompt_template.format(
            rent_roll_text=rent_roll_text,
            field_mapping=json.dumps(field_mapping, indent=2),
            note_on_sub_rows=note_on_array_rows,
        )

        # Send task to agent
        task = TextMessage(content=user_prompt, source="user")

        # Get response from agent
        response = await self.agent.on_messages([task], None)

        if not response or not hasattr(response.chat_message, "content"):
            raise ValueError("Failed to get response from extraction agent")

        # Extract TSV content from response
        tsv_content = self._extract_tsv_from_response(response.chat_message.content)

        if not tsv_content:
            raise ValueError("Failed to extract TSV content from agent response")

        return tsv_content

    async def _extract_multiple_chunks(
        self, rent_roll_text: str, field_mapping: dict[str, str], max_chunk_size: int
    ) -> str:
        """Extract data from multiple text chunks and merge results."""
        # Split text into pages using form feed character
        pages = rent_roll_text.split("\f")

        # Group pages into chunks that don't exceed size limit
        chunks = []
        current_chunk = ""

        for page in pages:
            if len(current_chunk + page) <= max_chunk_size:
                current_chunk += page + "\f" if current_chunk else page
            else:
                if current_chunk:
                    chunks.append(current_chunk.rstrip("\f"))
                current_chunk = page

        if current_chunk:
            chunks.append(current_chunk.rstrip("\f"))

        print(f"Processing {len(chunks)} chunks...")

        # Extract data from each chunk
        all_tsv_lines = []
        header_added = False

        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}...")

            try:
                chunk_tsv = await self._extract_single_chunk(chunk, field_mapping)
                lines = chunk_tsv.strip().split("\n")

                if not header_added:
                    # Include header from first chunk
                    all_tsv_lines.extend(lines)
                    header_added = True
                else:
                    # Skip header for subsequent chunks
                    all_tsv_lines.extend(lines[1:])

            except Exception as e:
                print(f"Warning: Error processing chunk {i+1}: {e}")
                continue

        # Remove duplicate data rows (can happen at chunk boundaries)
        unique_lines = []
        seen_data_rows = set()

        for line in all_tsv_lines:
            if not line.strip():
                continue

            # Keep header row
            if line.startswith("line_nos\t") or line.startswith("line_ref\t"):
                if not unique_lines:  # Only add header once
                    unique_lines.append(line)
            else:
                # For data rows, check for duplicates based on line number
                line_ref = line.split("\t")[0] if "\t" in line else line
                if line_ref not in seen_data_rows:
                    seen_data_rows.add(line_ref)
                    unique_lines.append(line)

        return "\n".join(unique_lines)

    def _extract_tsv_from_response(self, response_content: str) -> str:
        """Extract TSV content from agent response."""
        # Look for TSV content between ```tsv markers
        tsv_pattern = r"```(?:tsv)?\n(.*?)```"
        match = re.search(tsv_pattern, response_content, re.DOTALL)

        if match:
            result = match.group(1).strip()
            return result

        # Look for TSV content without markdown markers
        lines = response_content.strip().split("\n")
        tsv_lines = []
        in_tsv_section = False

        for line in lines:
            line = line.strip()

            # Start collecting when we see a header line
            if (
                line.startswith("line_nos\t")
                or line.startswith("line_ref\t")
                or ("line_nos" in line and "\t" in line)
            ):
                in_tsv_section = True
                tsv_lines.append(line)
                continue

            # If we're in TSV section, collect data lines
            if in_tsv_section:
                # Check if line looks like data with line reference
                if re.match(r"^0x[0-9a-fA-F]+", line) or (
                    line and "\t" in line and not line.startswith("#")
                ):
                    tsv_lines.append(line)
                elif line == "":
                    # Empty line might be acceptable
                    continue
                else:
                    # Non-TSV content, stop collecting
                    break

        if tsv_lines:
            result = "\n".join(tsv_lines)
            return result

        # Last resort: return the entire response if it looks like TSV
        if "\t" in response_content and (
            "0x" in response_content or "line_nos" in response_content
        ):
            return response_content.strip()

        return ""

    def tsv_array_tab_normalizer(self, tsv_file_path: str) -> str:
        """Normalize simplified TSV format by properly aligning array field values to their correct columns.

        Handles the simplified sub-row format: line_nos\tarray_field1\tarray_field2\t...
        Converts to: line_nos\t[empty_tabs]\tarray_field1\tarray_field2\t...

        Args:
            tsv_file_path: Path to the TSV file to normalize

        Returns:
            Path to the normalized TSV file (overwrites original)
        """
        print(f"Normalizing simplified TSV format: {tsv_file_path}")

        # Read the TSV file
        with open(tsv_file_path, encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            print("Empty TSV file, nothing to normalize")
            return tsv_file_path

        # Parse header to identify array fields and their positions
        header_line = lines[0].strip()
        headers = header_line.split("\t")

        # Find array field columns and their positions
        array_field_positions = []
        for i, header in enumerate(headers):
            if "[" in header and "]" in header:
                array_field_positions.append(i)

        if not array_field_positions:
            print("No array fields found, no normalization needed")
            return tsv_file_path

        print(f"Array field positions: {array_field_positions}")

        # Calculate how many empty tabs needed before array fields
        first_array_position = min(array_field_positions)
        empty_tabs_needed = (
            first_array_position - 1
        )  # -1 because first column is line_nos

        print(f"Empty tabs needed before array fields: {empty_tabs_needed}")

        normalized_lines = [lines[0]]  # Keep header as-is

        # Process each data row
        for line_num, line in enumerate(lines[1:], start=2):
            line = line.rstrip("\n\r")
            if not line.strip():
                normalized_lines.append(line + "\n")
                continue

            fields = line.split("\t")

            # Check if this is a simplified array sub-row
            if self._is_simplified_array_row(fields, len(headers)):
                # This is a simplified array sub-row: line_nos\tarray_field1\tarray_field2\t...
                normalized_line = self._normalize_simplified_array_row(
                    fields, empty_tabs_needed
                )
                normalized_lines.append(normalized_line + "\n")
                print(f"Normalized line {line_num}: simplified array row")
            else:
                # Regular row, keep as-is
                normalized_lines.append(line + "\n")

        # Write normalized content back to file
        with open(tsv_file_path, "w", encoding="utf-8") as f:
            f.writelines(normalized_lines)

        print(f"TSV normalization complete: {tsv_file_path}")
        return tsv_file_path

    def _is_simplified_array_row(self, fields: list[str], header_count: int) -> bool:
        """Determine if a row is a simplified array sub-row.

        Simplified array rows have:
        1. line_nos in first column (hex format)
        2. Much fewer fields than the header count
        3. Only contain array field data after line_nos
        """
        if len(fields) < 2:
            return False

        # First field should be a line number (hex format)
        if not fields[0].startswith("0x"):
            return False

        # Simplified array rows have significantly fewer fields than the full header
        # They contain: line_nos + array_field_values only
        # Regular rows have all or most header fields
        if len(fields) < header_count // 2:  # Heuristic: less than half the header count
            return True

        return False

    def _normalize_simplified_array_row(
        self, fields: list[str], empty_tabs_needed: int
    ) -> str:
        """Normalize a simplified array row by adding proper tab alignment.

        Converts: line_nos\tarray_field1\tarray_field2
        To: line_nos\t\t\t...\tarray_field1\tarray_field2

        Args:
            fields: The simplified array row fields
            empty_tabs_needed: Number of empty tabs to insert after line_nos

        Returns:
            Properly aligned row string
        """
        if not fields:
            return ""

        # Start with line_nos
        normalized_parts = [fields[0]]

        # Add empty tabs to reach array field positions
        normalized_parts.extend([""] * empty_tabs_needed)

        # Add the array field values (everything after line_nos)
        normalized_parts.extend(fields[1:])

        return "\t".join(normalized_parts)
