# TSV to JSON Converter Agent - User Prompt

Please convert the provided TSV file to JSON format using the given schema.

## Input Files
- **TSV File**: `{tsv_file_path}` - Contains extracted rent roll data in tab-separated format
- **JSON Schema**: `{json_schema}` - Defines the target JSON structure and field mappings

## Conversion Requirements

### Data Structure
The TSV data may contain:
- **Parent Rows**: Main records with primary field data
- **Sub-Rows**: Additional rows containing array field data (e.g., charge codes, fees)
- **Line References**: Each row includes a line number reference for traceability

### Schema Mapping
The JSON schema defines:
- **Field Names**: Target JSON field names
- **Array Fields**: Fields that should be converted to arrays (identified by bracket notation like `field[0].property`)
- **Nested Structure**: Complex object relationships

### Expected Output Format
```json
[
  {
    "unit_ref_id": "1001",
    "tenant_name": "Example Tenant",
    "rent_monthly": "2500.00",
    "charge_codes": [
      {
        "charge_code": "rent",
        "value": "2500.00"
      },
      {
        "charge_code": "cam",
        "value": "150.00"
      }
    ],
    "_line_ref": "0x001a"
  }
]
```

## Conversion Instructions

1. **Use the Converter Tool**: Utilize the dedicated TSV to JSON converter tool for processing
2. **Maintain Data Integrity**: Preserve all original values from the TSV file
3. **Handle Missing Data**: Set missing fields to `null` rather than omitting them
4. **Consolidate Rows**: Combine sub-rows containing array data with their parent records
5. **Preserve References**: Maintain line number references for data traceability

## Output Requirements

- **Complete JSON File**: All records converted to structured JSON format
- **Schema Compliance**: Every field from the schema present in each record
- **Array Consolidation**: Multiple charge codes, fees, etc. grouped as arrays
- **Line Traceability**: Original line references preserved in `_line_ref` field

Please proceed with the conversion using the converter tool and provide the resulting JSON file.
