"""
TSV to JSON Converter Agent - Multi-Phase

Phase 1: Simple converter that transforms TSV files to JSON format without array field consolidation.
Phase 2: Array field consolidation to create proper nested structure.
"""

import json
from typing import Dict, List, Any


class TSVToJSONConverter:
    """
    Multi-phase TSV to JSON converter.
    Phase 1: Converts each TSV row to a JSON object without array field handling.
    Phase 2: Consolidates array fields into proper nested structure.
    """
    
    def __init__(self):
        """Initialize the converter."""
        pass
    
    async def convert(self, tsv_file: str, json_schema: Dict[str, Any], output_file: str) -> str:
        """
        Convert TSV file to JSON based on the provided schema.
        
        Args:
            tsv_file: Path to the input TSV file
            json_schema: JSON schema defining the output structure
            output_file: Path to save the output JSON file
            
        Returns:
            Path to the output JSON file
        """
        # Parse the TSV file
        rows = self._parse_tsv(tsv_file)
        if not rows:
            raise ValueError("No data found in TSV file")
        
        # Convert each row to JSON object
        json_objects = []
        for row in rows:
            json_obj = self._build_json_object(row, json_schema)
            json_objects.append(json_obj)
        
        # Write output JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_objects, f, indent=2, ensure_ascii=False)
        
        return output_file
    
    def _parse_tsv(self, tsv_file: str) -> List[Dict[str, str]]:
        """
        Parse TSV file handling both main rows and simplified sub-rows.
        
        Main rows align with header columns.
        Simplified sub-rows have format: line_nos\tarray_field1\tarray_field2\t...
        
        Args:
            tsv_file: Path to TSV file
            
        Returns:
            List of dictionaries representing each row
        """
        rows = []
        
        with open(tsv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            return rows
        
        # Parse header
        header_line = lines[0].strip()
        headers = header_line.split('\t')
        
        # Identify array field positions and names
        array_field_info = self._get_array_field_info(headers)
        
        # Process each data line
        for line_num, line in enumerate(lines[1:], start=2):
            line = line.strip()
            if not line:
                continue
                
            fields = line.split('\t')
            
            if self._is_simplified_sub_row(fields, len(headers)):
                # This is a simplified sub-row: line_nos + array field values
                row_dict = self._parse_simplified_sub_row(fields, array_field_info, headers)
            else:
                # This is a main row: parse normally with header alignment
                row_dict = self._parse_main_row(fields, headers)
            
            if row_dict:
                rows.append(row_dict)
        
        return rows
    
    def _get_array_field_info(self, headers: List[str]) -> Dict[str, Any]:
        """
        Extract array field information from headers.
        
        Args:
            headers: List of header column names
            
        Returns:
            Dictionary with array field info
        """
        array_info = {
            'positions': [],
            'field_names': [],
            'array_name': None
        }
        
        for i, header in enumerate(headers):
            if '[' in header and ']' in header:
                array_info['positions'].append(i)
                array_info['field_names'].append(header)
                if array_info['array_name'] is None:
                    # Extract array name (e.g., "charge_codes" from "charge_codes[0].charge_code")
                    array_info['array_name'] = header.split('[')[0]
        
        return array_info
    
    def _is_simplified_sub_row(self, fields: List[str], header_count: int) -> bool:
        """
        Determine if a row is a simplified sub-row.
        
        Args:
            fields: Row fields
            header_count: Number of header columns
            
        Returns:
            True if this is a simplified sub-row
        """
        if len(fields) < 2:
            return False
        
        # First field should be a line number (hex format)
        if not fields[0].startswith('0x'):
            return False
        
        # Simplified sub-rows have significantly fewer fields than the header
        # Heuristic: less than half the header count
        return len(fields) < header_count // 2
    
    def _parse_simplified_sub_row(self, fields: List[str], array_field_info: Dict[str, Any], headers: List[str]) -> Dict[str, str]:
        """
        Parse a simplified sub-row into a dictionary.
        
        Args:
            fields: Row fields (line_nos + array field values)
            array_field_info: Information about array fields
            headers: Full header list
            
        Returns:
            Dictionary representing the sub-row
        """
        row_dict = {}
        
        # Set line_nos
        row_dict['line_nos'] = fields[0]
        
        # Initialize all header fields as empty
        for header in headers:
            if header != 'line_nos':
                row_dict[header] = ""
        
        # Map array field values to their corresponding headers
        array_field_names = array_field_info['field_names']
        array_values = fields[1:]  # Skip line_nos
        
        for i, value in enumerate(array_values):
            if i < len(array_field_names):
                header_name = array_field_names[i]
                row_dict[header_name] = value.strip() if value else ""
        
        return row_dict
    
    def _parse_main_row(self, fields: List[str], headers: List[str]) -> Dict[str, str]:
        """
        Parse a main row into a dictionary.
        
        Args:
            fields: Row fields
            headers: Header column names
            
        Returns:
            Dictionary representing the main row
        """
        row_dict = {}
        
        for i, header in enumerate(headers):
            if i < len(fields):
                value = fields[i].strip() if fields[i] else ""
                row_dict[header] = value
            else:
                row_dict[header] = ""
        
        return row_dict
    
    def _build_json_object(self, row: Dict[str, str], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a JSON object from a single TSV row ensuring all schema fields are present.
        
        Args:
            row: Single TSV row data
            schema: Field mapping schema (defines all expected fields)
            
        Returns:
            JSON object with all schema fields
        """
        json_obj = {}
        
        # Include ALL fields from schema, even if not present in TSV
        for schema_field in schema.keys():
            # Include ALL fields regardless of mapping value (null or non-null)
            if schema_field in row:
                # Field present in TSV row
                value = row[schema_field]
                json_obj[schema_field] = value if value else None
            else:
                # Field not present in TSV, set to null
                json_obj[schema_field] = None
        
        # Handle line reference
        if 'line_nos' in row:
            json_obj['_line_ref'] = row['line_nos']
        
        return json_obj
    
    async def convert_phase2(self, phase1_json_file: str, output_file: str, user_schema: str = None) -> str:
        """
        Phase 2: Consolidate array fields from Phase 1 JSON output.
        
        Args:
            phase1_json_file: Path to Phase 1 JSON output file
            output_file: Path to save the consolidated JSON file
            user_schema_file: Optional path to user schema JSON file for array field detection
            
        Returns:
            Path to the output JSON file
        """
        # Load Phase 1 JSON data
        with open(phase1_json_file, 'r', encoding='utf-8') as f:
            phase1_data = json.load(f)
        
        if not phase1_data:
            raise ValueError("No data found in Phase 1 JSON file")
        
        # Load user schema to identify expected array fields
        expected_arrays = set()
        if user_schema:
            #TODO : validate JSON
            # user_schema_dict = json.loads(user_schema)
            expected_arrays = self._get_array_fields_from_schema(user_schema)
        
        # Consolidate array fields
        consolidated_data = self._consolidate_array_fields(phase1_data, expected_arrays)
        
        # Write output JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)
        
        # Generate normalised TSV output for Excel visualization
        normalised_tsv_file = output_file.replace('.json', '_normalised.tsv')
        self._generate_normalised_tsv(consolidated_data, normalised_tsv_file)
        
        return output_file
    
    def _get_array_fields_from_schema(self, user_schema: Dict[str, Any]) -> set:
        """
        Extract array field names from user schema.
        
        Args:
            user_schema: User JSON schema
            
        Returns:
            Set of array field names
        """
        array_fields = set()
        for key, value in user_schema.items():
            if isinstance(value, list):
                array_fields.add(key)
        return array_fields
    
    def _consolidate_array_fields(self, json_data: List[Dict[str, Any]], expected_arrays: set = None) -> List[Dict[str, Any]]:
        """
        Consolidate array fields by merging sub-rows into parent objects.
        
        Args:
            json_data: List of JSON objects from Phase 1
            expected_arrays: Set of expected array field names from schema
            
        Returns:
            List of consolidated JSON objects
        """
        if expected_arrays is None:
            expected_arrays = set()
            
        consolidated = []
        
        for i, current_obj in enumerate(json_data):
            if self._is_sub_row(current_obj):
                # This is a sub-row, merge it into the previous parent
                if consolidated:
                    parent_obj = consolidated[-1]
                    self._merge_sub_row_into_parent(parent_obj, current_obj)
                else:
                    # No parent found, this shouldn't happen but handle gracefully
                    print(f"Warning: Found sub-row without parent at index {i}")
                    consolidated.append(current_obj)
            else:
                # This is a parent row, add it to consolidated list
                # But first convert any flattened array fields to proper structure
                converted_obj = self._convert_flattened_arrays(current_obj)
                consolidated.append(converted_obj)
        
        # Ensure all expected array fields are present in final output
        for obj in consolidated:
            for array_name in expected_arrays:
                if array_name not in obj:
                    obj[array_name] = []
        
        return consolidated
    
    def _is_sub_row(self, json_obj: Dict[str, Any]) -> bool:
        """
        Determine if a JSON object is a sub-row (contains only array field data).
        
        Args:
            json_obj: JSON object to check
            
        Returns:
            True if this is a sub-row, False otherwise
        """
        # Get all array field keys (keys with bracket notation)
        array_fields = [key for key in json_obj.keys() if '[' in key and ']' in key]
        
        # Get all non-array fields (excluding special fields like _line_ref)
        non_array_fields = [
            key for key in json_obj.keys() 
            if '[' not in key and ']' not in key and not key.startswith('_')
        ]
        
        # Check if all non-array fields are null/empty
        non_array_values = [json_obj[key] for key in non_array_fields]
        all_non_array_null = all(value is None or value == "" for value in non_array_values)
        
        # Check if at least one array field has a value
        array_values = [json_obj[key] for key in array_fields]
        has_array_data = any(value is not None and value != "" for value in array_values)
        
        return all_non_array_null and has_array_data
    
    def _merge_sub_row_into_parent(self, parent_obj: Dict[str, Any], sub_row: Dict[str, Any]) -> None:
        """
        Merge sub-row array data into parent object.
        
        Args:
            parent_obj: Parent JSON object to merge into
            sub_row: Sub-row containing array field data
        """
        # Find array fields in sub-row
        array_fields = {}
        for key, value in sub_row.items():
            if '[' in key and ']' in key and value is not None and value != "":
                # Extract array name and field name
                # e.g., "charge_codes[0].charge_code" -> array: "charge_codes", field: "charge_code"
                array_name = key.split('[')[0]
                field_name = key.split('.')[1] if '.' in key else key
                
                if array_name not in array_fields:
                    array_fields[array_name] = {}
                array_fields[array_name][field_name] = value
        
        # Add array data to parent
        for array_name, field_data in array_fields.items():
            if array_name not in parent_obj or parent_obj[array_name] is None:
                parent_obj[array_name] = []
            
            # Add _line_ref to array item if available in sub_row
            if '_line_ref' in sub_row:
                field_data['_line_ref'] = sub_row['_line_ref']
            
            parent_obj[array_name].append(field_data)
    
    def _convert_flattened_arrays(self, json_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert flattened array fields in a JSON object to proper nested structure.
        
        Args:
            json_obj: JSON object with flattened array fields
            
        Returns:
            JSON object with proper nested array structure
        """
        converted = {}
        array_data = {}
        
        for key, value in json_obj.items():
            if '[' in key and ']' in key:
                # This is a flattened array field
                array_name = key.split('[')[0]
                field_name = key.split('.')[1] if '.' in key else key
                
                if value is not None and value != "":
                    if array_name not in array_data:
                        array_data[array_name] = {}
                    array_data[array_name][field_name] = value
            else:
                # Regular field
                converted[key] = value
        
        # Add array data to converted object
        for array_name, field_data in array_data.items():
            if field_data:  # Only add if there's actual data
                # Add _line_ref to array item if available in parent
                if '_line_ref' in json_obj:
                    field_data['_line_ref'] = json_obj['_line_ref']
                converted[array_name] = [field_data]
            else:
                converted[array_name] = []
        
        return converted
    
    def _generate_normalised_tsv(self, json_data: List[Dict[str, Any]], output_file: str) -> None:
        """
        Generate a normalised TSV file from JSON data that mimics the original TSV format.
        
        This reconstructs a TSV structure similar to the original extracted TSV,
        but with correct tab alignment for array columns and proper formatting.
        
        Args:
            json_data: List of consolidated JSON objects
            output_file: Path to save the normalised TSV file
        """
        if not json_data:
            return
        
        # Determine the schema structure similar to original TSV extraction
        # First, identify all non-array fields and array fields
        non_array_fields = set()
        array_fields = {}
        
        # Sample the data to understand the structure
        for obj in json_data:
            for key, value in obj.items():
                if key.startswith('_'):  # Skip internal fields like _line_ref
                    continue
                if isinstance(value, list):
                    # This is an array field, collect its subfields
                    if key not in array_fields:
                        array_fields[key] = set()
                    for item in value:
                        if isinstance(item, dict):
                            for subkey in item.keys():
                                if not subkey.startswith('_'):
                                    array_fields[key].add(subkey)
                else:
                    non_array_fields.add(key)
        
        # Create column structure similar to original TSV extraction
        # Format: line_nos + non_array_fields + array_field[0].subfield1 + array_field[0].subfield2 + ...
        columns = ['line_nos']
        columns.extend(sorted(non_array_fields))
        
        # Add array field columns in bracket notation
        for array_name in sorted(array_fields.keys()):
            for subfield in sorted(array_fields[array_name]):
                columns.append(f"{array_name}[0].{subfield}")
        
        # Write TSV file
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            # Write header
            f.write('\t'.join(columns) + '\n')
            
            # Write data rows
            for obj in json_data:
                # Check if object has array data
                array_data = {}
                for array_name in array_fields.keys():
                    if array_name in obj and obj[array_name]:
                        array_data[array_name] = obj[array_name]
                
                if array_data:
                    # Generate rows for each array item (similar to original TSV extraction)
                    max_items = max(len(items) for items in array_data.values()) if array_data else 1
                    
                    for i in range(max_items):
                        row_values = []
                        
                        # Line reference
                        if i == 0:
                            # First row: use object's line reference
                            row_values.append(obj.get('_line_ref', ''))
                        else:
                            # Subsequent rows: use array item's line reference if available
                            line_ref = ''
                            for array_name, items in array_data.items():
                                if i < len(items) and isinstance(items[i], dict):
                                    line_ref = items[i].get('_line_ref', '')
                                    if line_ref:
                                        break
                            row_values.append(line_ref)
                        
                        # Non-array fields (only on first row)
                        for field in sorted(non_array_fields):
                            if i == 0:
                                value = obj.get(field)
                                row_values.append('' if value is None else str(value))
                            else:
                                row_values.append('')  # Empty for subsequent array rows
                        
                        # Array fields
                        for array_name in sorted(array_fields.keys()):
                            for subfield in sorted(array_fields[array_name]):
                                value = ''
                                if array_name in array_data and i < len(array_data[array_name]):
                                    item = array_data[array_name][i]
                                    if isinstance(item, dict):
                                        item_value = item.get(subfield)
                                        value = '' if item_value is None else str(item_value)
                                row_values.append(value)
                        
                        # Write the row
                        f.write('\t'.join(row_values) + '\n')
                else:
                    # No array data, write single row
                    row_values = []
                    
                    # Line reference
                    row_values.append(obj.get('_line_ref', ''))
                    
                    # Non-array fields
                    for field in sorted(non_array_fields):
                        value = obj.get(field)
                        row_values.append('' if value is None else str(value))
                    
                    # Array fields (all empty)
                    for array_name in sorted(array_fields.keys()):
                        for subfield in sorted(array_fields[array_name]):
                            row_values.append('')
                    
                    # Write the row
                    f.write('\t'.join(row_values) + '\n')
        
        print(f"Generated normalised TSV file: {output_file}")


# Standalone conversion functions for direct use
async def convert_tsv_to_json(tsv_file: str, json_schema: Dict[str, Any], output_file: str) -> str:
    """
    Convert TSV file to JSON using the TSVToJSONConverter.
    
    Args:
        tsv_file: Path to input TSV file
        json_schema: JSON schema for mapping
        output_file: Path to output JSON file
        
    Returns:
        Path to output file
    """
    converter = TSVToJSONConverter()
    return await converter.convert(tsv_file, json_schema, output_file)


async def convert_phase2_json(phase1_json_file: str, output_file: str, user_schema_file: str = None) -> str:
    """
    Convert Phase 1 JSON to Phase 2 (consolidated) JSON using the TSVToJSONConverter.
    
    Args:
        phase1_json_file: Path to Phase 1 JSON file
        output_file: Path to output JSON file
        user_schema_file: Optional path to user schema JSON file
        
    Returns:
        Path to output file
    """
    converter = TSVToJSONConverter()
    return await converter.convert_phase2(phase1_json_file, output_file, user_schema_file)


if __name__ == "__main__":
    import sys
    import asyncio
    
    if len(sys.argv) != 4:
        print("Usage: python tsv_to_json_converter.py <tsv_file> <field_mapping_file> <output_json_file>")
        sys.exit(1)
    
    tsv_file = sys.argv[1]
    field_mapping_file = sys.argv[2]
    output_json_file = sys.argv[3]
    
    # Load field mapping as schema
    with open(field_mapping_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    async def run_conversion():
        converter = TSVToJSONConverter()
        
        # Phase 1: Convert TSV to JSON
        phase1_output = output_json_file.replace('.json', '_phase1.json')
        await converter.convert(tsv_file, schema, phase1_output)
        print(f"Phase 1 complete: {phase1_output}")
        
        # Phase 2: Consolidate array fields
        await converter.convert_phase2(phase1_output, output_json_file)
        print(f"Phase 2 complete: {output_json_file}")
    
    asyncio.run(run_conversion())