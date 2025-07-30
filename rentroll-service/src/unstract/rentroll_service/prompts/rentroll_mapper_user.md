# Field Mapping Task

You are provided with rent roll data and a user's JSON schema. Your task is to analyze the document structure and create a mapping between the user's field names and the actual field names in the document.

## Input Data

### 1. Rent Roll Document
The following pages contain rent roll data with various field names, column headers, and data labels:

{rent_roll_content}

### 2. User's JSON Schema
The user wants to map the following fields from their JSON structure to the document:

{user_json_schema}

## Your Task

Analyze the rent roll document and identify which field names, column headers, or data labels correspond to each field in the user's JSON schema. 

**CRITICAL**: Many documents have column headers split across multiple lines. You MUST reconstruct complete header names by combining vertically aligned text fragments.

Examples:
- "Trans" (line 1) + "Code" (line 2) = "Trans Code"
- "Market" (line 1) + "+ Addl." (line 2) = "Market + Addl."
- "Unit/Lease" (line 1) + "Status" (line 2) = "Unit/Lease Status"

Create a mapping object that translates the user's field names to the exact field names found in the document (using reconstructed complete names).

**BEFORE mapping charge_codes, verify the umbrella header context:**
1. **Umbrella Header Check**: Are "Cat", "Code", "Type", "Amount" columns positioned UNDER an umbrella header like "Future Rent Increases"?
2. **Spatial Analysis**: Look at the hierarchical structure - do these columns inherit future/projection context from their umbrella header?
3. **Escalation Patterns**: Do the data rows show progressive amounts with future dates (indicating projections)?
4. **Current vs Future**: Are there separate sections for actual current operational charges vs future projections?
5. **Context Override Rule**: If columns appear under future/projection umbrella headers, exclude from charge_codes mapping even if column names look like charge fields

**IMPORTANT**: These exclusions apply ONLY to charge_codes fields. Users may legitimately want to extract future rent data for other purposes.

## Important Instructions

1. **Reconstruct multi-line headers** - Combine text fragments that are vertically aligned in the same column
2. **Map field names only** - Do not extract actual data values
3. **Use complete reconstructed names** - Always prefer "Trans Code" over just "Code" if both parts exist
4. **Preserve exact spelling** - Use the original spelling, capitalization, spacing, and punctuation from the document (after reconstruction)
5. **Return null for missing fields** - If a user field has no corresponding field in the document, map it to `null`
6. **Consider variations** - Recognize abbreviations, synonyms, and industry-specific terminology
7. **One-to-one mapping** - Each user field should map to at most one document field
8. **Use OR syntax for alternative column names** - When the same data might appear under different column names, use pipe (|) separator
9. **List alternatives only** - Only use OR for columns that represent the exact same data type

## Handling Alternative Column Names

If the document might use different column names for the same data (common across different property management systems), use the OR syntax:
- Different naming conventions: `"tenant_name": "Tenant Name | Lessee | Resident Name"`
- Various unit identifiers: `"unit_ref_id": "Unit # | Apt | Suite"`
- Alternative rent labels: `"rent_monthly": "Monthly Rent | Base Rent | Contract Rent"`

## Handling Alternative Amount Columns for Arrays

For charge codes or fee arrays, amounts might appear in different columns based on the charge type:
- Mutually exclusive amounts: `"charge_codes[0].value": "Lease Rent | Other Charges/Credits"`
- Different fee categories: `"fees[0].amount": "Base Amount | Additional Charges | Misc Fees"`

**Pattern to Look For:**
- Different charge types have amounts in different columns
- One column has the amount, others have zero or are empty
- Example: RENT charges in "Lease Rent" column, CABLE/PEST in "Other Charges/Credits" column

**Important Notes:**
- Only use OR for true alternatives where the document will have ONE of these columns with data per row
- Do NOT use OR if both columns can have non-zero values simultaneously
- The extraction agent will check each alternative in order and use the first column with a non-zero value

## Special Case: Future Rent Increases vs Current Charges

**CRITICAL DISTINCTION**: Many rent roll documents contain both current charges and future rent increase schedules.

### What are Future Rent Increases?
- Projected rent amounts for upcoming years
- Usually contain escalation codes like "BM1", "EM1", "FM1" 
- Show progressive amounts increasing over time
- Appear under headers like "Future Rent Increases", "-- Future Rent Increases"

### Current Charges vs Future Projections
- **Current charges**: Active fees like CAM, utilities, parking that tenants pay NOW
- **Future increases**: Scheduled rent escalations that will happen in the future
- **Key difference**: Current charges are operational costs; future increases are rent adjustments

### Mapping Rules for Charge Codes:
1. **If you see explicit "Charge Schedules" or "Additional Charges" sections** → Map those to charge_codes
2. **If you ONLY see "Future Rent Increases" sections** → Map charge_codes to null
3. **If both exist** → Map ONLY the current charges section, ignore future increases
4. **When in doubt** → Look for operational charges (CAM, utilities, fees) vs rent escalations

### Example Decision Process:
```
Document has "Future Rent Increases" with BM1 codes → charge_codes should be null
Document has "Charge Schedules" with CAM, utilities → charge_codes should map to that section
Document has both sections → map charge_codes to "Charge Schedules", ignore "Future Rent Increases"
```

### Critical Pattern Example (Sample 2 Type):
```
                                Future Rent Increases
    Suite ID  Tenant  Rent  NNN  Deposit  Cat  Date  Monthly Amount  PSF
```
**Analysis**: Even though "Cat" and "Monthly Amount" look like charge fields, they appear under "Future Rent Increases" umbrella header.
**Decision**: Map charge_codes to null (exclude the future projection columns)
**Reasoning**: Umbrella header context overrides individual column name similarity

### Other Sections to Exclude from Mapping:
- **Historical/Past**: "Rent History", "Former Tenants", "Expired Leases", "Prior Year"
- **Summary/Totals**: "Property Totals", "Building Summary", "Grand Totals", "Average Rent"
- **Budget/Projections**: "Budget Rent", "Pro Forma", "Projected", "Estimated", "Target Rents"
- **Options/Contingent**: "Lease Options", "Extension Options", "Percentage Rent", "Contingent"
- **Reconciliation**: "Reconciliation", "True-Up", "Year-End Adjustments", "Budget vs Actual"
- **Inactive/Pending**: "Pending Leases", "Letters of Intent", "Proposed", "Terminating"
- **Notes/Commentary**: "Notes", "Comments", "Remarks", "Special Conditions"

**Key Principle**: Only map data from sections that represent CURRENT, ACTIVE, CONFIRMED lease and charge information.

## Output Format

Return your mapping as a JSON object:

```json
{{
  "unit_ref_id": "Unit # | Suite | Space",
  "tenant_name": "Tenant Name | Lessee",
  "charge_codes[0].charge_code": "Type | Charge Type",
  "charge_codes[0].value": "Amount | Monthly Amt",
  "missing_field": null
}}
```

Note: 
- Use the pipe (|) separator with spaces when mapping alternative column names
- For array fields, use bracket notation directly (e.g., `"field[0].property"`)
- NEVER use nested objects for arrays - always use the flat bracket notation format

Begin your analysis and provide the field mapping.