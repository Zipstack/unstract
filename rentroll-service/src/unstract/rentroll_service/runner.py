"""
RentRollExtractorRunner - Coordinates the rent roll extraction workflow.

This module provides a high-level interface for running the complete rent roll
extraction pipeline, from locating tables to generating structured JSON output.
"""

import asyncio
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any


# Import the necessary agents and tools
from agents.rent_roll_locator import RentRollLocatorAgent
from agents.rent_roll_mapper import RentRollMapper
from agents.tsv_to_json_converter import TSVToJSONConverter
from agents.rent_roll_extractor import RentRollExtractorAgent
from constants import USER_FIELDS
import logging

DEBUG = os.getenv("DEBUG", "true").lower() == "true"
logger = logging.getLogger(__name__)
class RentRollExtractorRunner:
    """Orchestrates the rent roll extraction workflow."""
    
    def __init__(
        self,
        llm_client: Any,
        debug: bool = False,
        output_dir: Optional[str] = None,
    ):
        """
        Initialize the RentRollExtractorRunner.
        
        Args:
            llm_client: Configured LLM client for agent communication
            debug: Enable debug logging
        """
        self.llm_client = llm_client
        self.debug = debug
        self.output_dir = output_dir
        # Initialize agents
        self.locator_agent = RentRollLocatorAgent(llm_client)
        self.mapper_agent = RentRollMapper(llm_client)
        self.extractor_agent = RentRollExtractorAgent(llm_client)
        self.converter_agent = TSVToJSONConverter()
        
    async def run(
        self,
        input_file: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the complete rent roll extraction pipeline.
        
        Args:
            input_file: Path to the input document
            schema: Schema definition for the output JSON
            
        Returns:
            Dictionary containing the extraction results and metadata
        """
        # Set default schema if not provided
        if schema is None:
            schema = self._get_default_schema()
        # Generate base output filenames
        input_path = Path(input_file)
        base_name = input_path.stem
        extracted_file = str(f"{self.output_dir}/{base_name}_extracted.txt")
        mapping_file = str(f"{self.output_dir}/{base_name}_mapping.json")
        tsv_file = str(f"{self.output_dir}/{base_name}_output.tsv")
        json_file_phase1 = str(f"{self.output_dir}/{base_name}_phase1.json")
        json_file_final = str(f"{self.output_dir}/{base_name}_final.json")
        user_fields_file = str(f"{self.output_dir}/{base_name}_user_fields.json")

        # Track execution results
        results = {
            "success": False
        }
        
        try:
            
            # Step 1: Locate rent roll tables and add line numbers
            logger.info("STEP 1: Locating rent roll tables...")
            await self.locator_agent.process_file(input_file, extracted_file)
            # Step 2: Map document fields to user fields
            logger.info("STEP 2: Mapping document fields to user fields...")
            
            # Write the user fields from constants to a temporary file for the agent
            with open(user_fields_file, "w", encoding="utf-8") as f:
                json.dump(USER_FIELDS, f, indent=2)

            try:
                mapping_result = await self.mapper_agent.map_fields(
                    extracted_file,
                    user_fields_file,
                )

                # Save the mapping result
                with open(mapping_file, "w", encoding="utf-8") as f:
                    json.dump(mapping_result, f, indent=2)
                
                # Step 3: Extract data
                logger.info("STEP 3: Extracting data...")
                result_file = await self.extractor_agent.extract_data(
                    extracted_text_file=extracted_file,
                    field_mapping_file=mapping_file,
                    output_tsv_file=tsv_file,
                )
                logger.info(f"✓ Extraction completed successfully")
                logger.info(f"✓ TSV file saved: {result_file}")

                # Step 4: Convert TSV to JSON (Phase 1)
                logger.info("STEP 4: Converting to JSON (Phase 1)...")
                filtered_mapping = filter_array_parent_fields(mapping_result)
                mapping_result_schema = {field: field for field in filtered_mapping.keys()}
                phase1_result = await self.converter_agent.convert(
                    result_file,  # Pass the generated TSV file
                    mapping_result_schema,
                    json_file_phase1
                )

                # Step 5: Process and refine JSON (Phase 2)
                logger.info("STEP 5: Refining JSON (Phase 2)...")
                final_result = await self.converter_agent.convert_phase2(
                    json_file_phase1,
                    json_file_final,
                    schema
                )
                with open(final_result, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("✓ Extraction completed successfully")
                return data
                # # Update results with success status
                # results.update({
                #     "success": True,
                #     "extracted_records": len(final_result.get("data", [])),
                #     "metrics": {
                #         "extraction_quality": final_result.get("quality_metrics", {}),
                #         "processing_time": final_result.get("processing_time", 0)
                #     }
                # })
                
            finally:
                # Clean up temporary files
                if os.path.exists(user_fields_file):
                    os.unlink(user_fields_file)
                
                # Clean up intermediate files if not keeping them
                if not DEBUG:
                    for file_path in [extracted_file, mapping_file, tsv_file, json_file_phase1]:
                        if os.path.exists(file_path):
                            os.unlink(file_path)
            
            return results
            
        except Exception as e:
            logger.error(f"Error during rent roll extraction: {str(e)}")
            results["error"] = str(e)
            return results
    
    def _get_default_schema(self) -> Dict[str, Any]:
        """Get default schema for rent roll data."""
        return {
            "type": "object",
            "properties": {
                "unit": {"type": "string", "description": "Unit identifier (e.g., A101)"},
                "unit_type": {"type": "string", "description": "Type of unit (e.g., 1BHK, 2BHK)"},
                "area": {"type": "number", "description": "Area in square feet"},
                "tenant_name": {"type": "string", "description": "Name of the tenant"},
                "rent_monthly": {"type": "number", "description": "Monthly rent amount"},
                "lease_start_date": {"type": "string", "format": "date", "description": "Lease start date (YYYY-MM-DD)"},
                "lease_end_date": {"type": "string", "format": "date", "description": "Lease end date (YYYY-MM-DD)"},
                "status": {"type": "string", "description": "Occupancy status (e.g., Occupied, Vacant)"}
            },
            "required": ["unit", "unit_type", "area", "rent_monthly"]
        }


def filter_array_parent_fields(field_mapping: dict) -> dict:
    """
    Filter out parent array fields when array element fields exist.
    Same logic as in RentRollExtractor agent.
    """
    # Identify array element fields (contain bracket notation)
    array_element_fields = {}
    for field_name in field_mapping.keys():
        if '[' in field_name and ']' in field_name:
            # Extract parent array name (e.g., "charge_codes" from "charge_codes[0].charge_code")
            parent_name = field_name.split('[')[0]
            if parent_name not in array_element_fields:
                array_element_fields[parent_name] = []
            array_element_fields[parent_name].append(field_name)
    
    # Filter out parent array fields that have element fields
    filtered_mapping = {}
    for field_name, field_value in field_mapping.items():
        # If this is a parent array field that has element fields, skip it
        if field_name in array_element_fields:
            print(f"  Filtering out parent array field '{field_name}' (has element fields: {array_element_fields[field_name]})")
            continue
        # Otherwise, include the field
        filtered_mapping[field_name] = field_value
    
    return filtered_mapping
