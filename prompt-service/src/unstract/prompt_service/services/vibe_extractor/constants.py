"""Constants for Vibe Extractor generation service."""


class VibeExtractorBootstrapPrompts:
    """Bootstrap prompts for generating document extraction components."""

    DOCUMENT_METADATA = """Generate metadata for a document type called "{doc_type}".
Based on your knowledge of this document type, provide all the fields shown in the reference template below.
Focus on generating appropriate values for:
1. name_identifier (lowercase, hyphens instead of spaces)
2. name (human-readable name)
3. description (3-4 sentences explaining what this document type is)
4. description_seo (SEO-optimized version of description)
5. html_meta_description (HTML meta description)
6. tags (3-6 relevant tags)
7. status (typically "beta" for new document types)
8. visibility (typically "public")
IMPORTANT: For multiline text fields (description, description_seo, html_meta_description), use the YAML pipe syntax (|) to properly format multiline content. For example:
description: |
  This is a multiline description
  that spans multiple lines
  and maintains proper formatting.
Use the reference template structure but adapt the content for "{doc_type}":
{reference_template}
Return your response as a YAML structure matching the exact format above, but with content appropriate for "{doc_type}".
Make sure to use the pipe syntax (|) for all description fields.
Only return the YAML structure, no additional text."""

    DOCUMENT_EXTRACTION_FIELDS = """Generate an extraction.yaml structure for document type: "{doc_type}".
Document description: {metadata_description}
Create a YAML structure that defines the fields to extract from this document type.
Follow these IMPORTANT rules:
1. Include all relevant fields that would typically be found in a {doc_type}
2. Use descriptive field names with underscores (e.g., invoice_number, customer_name)
3. Add comments after each field using # to describe what it extracts
4. **CRITICAL**: List type fields should and can ONLY be one level deep
5. Use List ONLY for items that are actual lists in the document (e.g., line_items, taxes, discounts)
6. Do NOT generate nested items or objects in the extraction YAML file
7. The extraction YAML should ONLY contain:
   - Scalar items: items with single values (e.g., invoice_number, date, total_amount, vendor_name)
   - List type items: items that are lists/arrays (e.g., line_items, taxes, discounts)
8. List items should be one level deep with sub-fields, but no nested objects
9. Include both scalar fields and list fields where appropriate for {doc_type} documents
Example format:
# Scalar items (single values)
field_name: <placeholder>  # Description of field
another_scalar: <placeholder>  # Description of another scalar field
# List items (one level deep only)
list_field:  # Description of list
  - sub_field: <placeholder>  # Description
    another_field: <placeholder>  # Description
IMPORTANT: Do NOT create nested objects or multi-level lists. Keep it simple:
- Scalar items for single values
- List items for arrays/lists (one level deep only)
Generate a comprehensive extraction structure for {doc_type} documents.
Return ONLY the YAML structure, no additional text."""

    PAGE_EXTRACTION_SYSTEM = """Generate a system prompt for page extraction for document type: "{doc_type}".
Document description: {metadata_description}
Context: Some documents may have many pages of irrelevant data. The LLM needs to identify
pages that contain relevant data for this document type.
The LLM will be given a page of the document (including bottom half of previous page and
top half of next page for context). The LLM must decide whether the page contains relevant
data and respond with only "yes" or "no".
Generate a system prompt that:
1. Explains what this document type is
2. Describes what relevant data looks like for this document type
3. Lists what irrelevant data might be present
4. Provides clear instructions to respond only with "yes" or "no"
5. Gives examples of what to look for
Make the prompt comprehensive but concise. Focus on the specific characteristics of {doc_type} documents."""

    PAGE_EXTRACTION_USER = """Generate a user prompt for page extraction for document type: "{doc_type}".
Document description: {metadata_description}
Context: This is the user prompt that will be sent along with the system prompt. The user
will provide a page of the document (including bottom half of previous page and top half
of next page for context). The LLM must decide whether the page contains relevant data
and respond with only "yes" or "no".
Generate a concise user prompt that:
1. Asks the LLM to analyze the provided page
2. Reminds the LLM to look for relevant {doc_type} data
3. Instructs to respond with only "yes" or "no"
Keep it short and direct - this will be used as a template for each page analysis."""

    SCALARS_EXTRACTION_SYSTEM = """Generate a system prompt for scalar field extraction for document type: "{doc_type}".
Document description: {metadata_description}
Context: The LLM needs to extract scalar values from the document. Each line in the document
is numbered in hexadecimal format (0x0001, 0x0002, etc.). The LLM must extract values and
their line numbers.
The prompt must:
1. Have dedicated section with exact format:
   ## Extraction Items
   ```yaml
   {{{{extraction_items}}}}
   ```
2. Use the handlebars variable only once in the prompt, refer to "## Extraction Items" section elsewhere
3. Have a section called "## Expected Variations of requested to available items" that lists possible variations of the scalar items based on the document type
4. Instruct to extract ONLY from the provided document (no prior knowledge)
5. Require ALL fields in output (use null if not found)
6. Include line numbers for each extracted value (format: _line_number_fieldname)
7. Output ONLY YAML format, no other text
8. Handle {doc_type}-specific extraction challenges
9. **CRITICAL**: Emphasize that the LLM must NOT perform any arithmetic operations, calculations, or other operations on values. Extract values exactly as they appear in the document. If a calculated field is required but not present in the document, it should be set to null.
Example output format (showing extracted values, not field names):
field_name: "extracted value from document"
_line_number_field_name: 0x0002
missing_field: null
_line_number_missing_field: null
Example scalar fields: {scalar_fields}
Generate a comprehensive system prompt for scalar extraction with:
1. Dedicated section using exact format:
   ## Extraction Items
   ```yaml
   {{{{extraction_items}}}}
   ```
2. Expected Variations section with {doc_type}-specific field variations"""

    SCALARS_EXTRACTION_USER = """Generate a concise user prompt for scalar field extraction for document type: "{doc_type}".
The user prompt should be very simple and direct. It should:
1. Ask the LLM to extract the specified fields from the document
2. Remind to follow the system instructions for format and line numbers
3. Be very brief - just 1-2 sentences
4. Not repeat detailed instructions (those are in the system prompt)
The prompt should be something like:
"Extract the specified fields from this {doc_type} document following the format requirements."
Generate a very concise user prompt."""

    TABLES_EXTRACTION_SYSTEM = """Generate a system prompt for table/list extraction for document type: "{doc_type}".
Document description: {metadata_description}
Context: The LLM needs to extract table/list data in TSV format. Tables can span multiple pages,
have multi-line cells, and sometimes what appears to be a table is actually a simple list.
The prompt must:
1. Have dedicated section with exact format:
   ## Extraction Items
   ```yaml
   {{{{extraction_items}}}}
   ```
2. Use the handlebars variable only once in the prompt, refer to "## Extraction Items" section elsewhere
3. Have a section called "## Expected Variations of requested to available items" that lists possible variations of the table items based on the document type
4. Handle rolling window documents (partial pages)
5. Handle tables spanning multiple pages with headers/footers
6. Handle multi-line cell content
7. Distinguish between tables and simple lists
8. Extract ONLY from provided document (no prior knowledge)
9. Include line numbers for each row (format: _line_no column)
10. Output TSV format with headers
11. Handle {doc_type}-specific table structures
12. **CRITICAL**: Emphasize that the LLM must NOT perform any arithmetic operations, calculations, or other operations on values. Extract values exactly as they appear in the document. If a calculated field is required but not present in the document, it should be set to null.
13. If the table is not present in the document, return an empty TSV file with header only
14. Output ONLY TSV format with no explanations, commentary, or other text
Include these specific examples in the prompt (use \\t to represent tabs in examples):
TYPE 1 - Normal tables example:
Document:
```
0x0001:
0x0002: No       Description          Unit     Discount
0x0004:                               Cost
0x0005: 1        Item 1              100.00    10.00
0x0006: 2        Item 2              200.00    20.00
0x0007: 3        Item 3              300.00    30.00
```
Note: "Unit Cost" spans two lines.
Output should be:
```tsv
_line_no\\tline_item_no\\tdescription\\tunit_cost\\tdiscount_percentage
0x0005\\t1\\tItem 1\\t100.00\\t10.00
0x0006\\t2\\tItem 2\\t200.00\\t20.00
0x0007\\t3\\tItem 3\\t300.00\\t30.00
```
TYPE 2 - Simple list example:
Document:
```
0x0001:
0x0002: Special instructions:
0x0003: • Item 1
0x0004: • Item 2
0x0005: • Item 3
```
Output should be:
```tsv
_line_no\\titem
0x0003\\tItem 1
0x0004\\tItem 2
0x0005\\tItem 3
```
Generate a comprehensive system prompt for table/list extraction with:
1. Dedicated section using exact format:
   ## Extraction Items
   ```yaml
   {{{{extraction_items}}}}
   ```
2. Expected Variations section with {doc_type}-specific field variations
3. Include these examples with \\t notation"""

    TABLES_EXTRACTION_USER = """Generate a concise user prompt for table extraction for document type: "{doc_type}".
The user prompt should be very simple and direct. It should:
1. Ask the LLM to extract the specified table/list from the document
2. Remind to follow the system instructions for TSV format
3. Be very brief - just 1-2 sentences
4. Not repeat detailed instructions (those are in the system prompt)
The prompt should be something like:
"Extract the table if it is present. If there is no matching table, reply No table found."
Generate a very concise user prompt."""

    DOCUMENT_TYPE_IDENTIFICATION = """You are an expert document analyzer. Your task is to identify the type of document based on its content.

Analyze the provided document content carefully and identify its type with high accuracy.

## Document Analysis Guidelines

When analyzing the document, look for these key indicators:

### 1. Structural Elements
- Headers, footers, and watermarks
- Document layout and formatting
- Presence of logos or official seals
- Table structures and data organization
- Section headings and labels

### 2. Content Markers
- Specific terminology and jargon
- Date formats and references
- Monetary values and calculations
- Legal or regulatory language
- Contact information and addresses

### 3. Functional Purpose
- What is the primary purpose of this document?
- Who are the typical stakeholders (issuer, recipient)?
- What transaction or process does it document?
- What obligations or information does it convey?

## Common Document Types

Consider these common business document categories:

**Financial Documents:**
- Invoice: Itemized bill for goods/services with payment terms, invoice number, vendor details
- Receipt: Proof of payment showing transaction details, payment method, timestamp
- Purchase Order: Request to purchase goods/services with PO number, quantities, pricing
- Credit Note: Document issued for refunds or corrections to invoices
- Debit Note: Document for additional charges or corrections
- Bill of Lading: Shipping document detailing goods being transported
- Packing Slip: List of items included in a shipment
- Delivery Note: Confirmation of goods delivered
- Statement of Account: Summary of transactions over a period
- Payment Voucher: Authorization for payment

**Banking Documents:**
- Bank Statement: Record of account transactions over a period
- Check/Cheque: Payment instrument drawn on a bank account
- Deposit Slip: Record of funds deposited into account
- Wire Transfer: Electronic fund transfer documentation
- Letter of Credit: Bank guarantee for international trade

**Payroll & Employment:**
- Pay Stub/Payslip: Earnings statement showing salary breakdown
- W-2 Form: Annual wage and tax statement (US)
- Employment Contract: Agreement between employer and employee
- Offer Letter: Job offer with terms and conditions
- Timesheet: Record of hours worked

**Tax & Compliance:**
- Tax Form (W-9, 1099, 1040, etc.): Various tax-related forms
- Tax Invoice: Invoice showing tax breakdown (VAT, GST, sales tax)
- Tax Return: Annual tax filing document
- Customs Declaration: Import/export declaration

**Healthcare:**
- Medical Record: Patient medical history and treatment notes
- Prescription: Medication authorization from healthcare provider
- Lab Report: Medical test results and findings
- Insurance Claim: Request for insurance coverage/reimbursement
- EOB (Explanation of Benefits): Insurance payment explanation
- Medical Bill/Invoice: Healthcare services billing

**Legal Documents:**
- Contract/Agreement: Legal binding agreement between parties
- NDA (Non-Disclosure Agreement): Confidentiality agreement
- Power of Attorney: Legal authorization document
- Certificate (Birth, Death, Marriage, etc.): Official certification
- License/Permit: Official authorization or permission
- Lease Agreement: Property rental contract
- Deed: Property ownership transfer document

**Shipping & Logistics:**
- Shipping Label: Package destination and tracking information
- Air Waybill: Air cargo shipping document
- Commercial Invoice: International trade invoice
- Certificate of Origin: Document certifying product origin
- Customs Invoice: Invoice for customs clearance

**HR & Administrative:**
- Application Form: Form for requesting service or admission
- Resume/CV: Career and qualifications summary
- Reference Letter: Professional or character reference
- Resignation Letter: Notice of employment termination
- Performance Review: Employee evaluation document

**Correspondence:**
- Business Letter: Formal business correspondence
- Memo: Internal communication document
- Notice: Formal announcement or notification
- Minutes of Meeting: Record of meeting proceedings

**Reports:**
- Business Report: Analysis or summary of business matters
- Financial Report: Financial performance analysis
- Audit Report: Financial or operational audit findings
- Technical Report: Technical analysis or specifications
- Research Report: Research findings and analysis

**Other:**
- Warranty: Product or service guarantee
- Manual: Instruction or user guide
- Catalog: Product or service listings
- Brochure: Marketing or information material
- Quote/Estimate: Price proposal for goods/services
- RFP (Request for Proposal): Solicitation for vendor proposals
- Inventory List: Stock or asset listing

## Response Format

After analyzing the document, respond with **ONLY** a valid JSON object in this exact format:

```json
{{
    "document_type": "identified-document-type",
    "confidence": "high|medium|low",
    "primary_indicators": [
        "specific indicator 1 that led to identification",
        "specific indicator 2 that led to identification",
        "specific indicator 3 that led to identification"
    ],
    "document_category": "category of the document",
    "alternative_types": [
        "possible alternative document type if confidence is not high"
    ],
    "reasoning": "brief explanation of why this document type was identified"
}}
```

### Field Specifications:

1. **document_type**: Use lowercase with hyphens (e.g., "invoice", "purchase-order", "medical-record", "bank-statement")
   - Be specific: Use "tax-invoice" instead of just "invoice" if tax details are prominent
   - Use compound names when necessary: "proof-of-delivery", "certificate-of-origin"

2. **confidence**:
   - "high": Multiple clear indicators, structure matches perfectly
   - "medium": Good indicators but some ambiguity or missing elements
   - "low": Limited indicators, could be multiple types

3. **primary_indicators**: List 3-5 specific elements from the document that led to identification
   - Example: "Invoice number INV-2024-001", "Payment terms: Net 30", "Itemized line items with tax"

4. **document_category**: High-level category
   - Examples: "financial", "legal", "healthcare", "shipping", "employment", "tax"

5. **alternative_types**: If confidence is not high, list 1-2 possible alternatives
   - Leave empty array if confidence is high

6. **reasoning**: Brief 1-2 sentence explanation
   - Focus on why this type fits best
   - Mention key distinguishing features

## Important Instructions

1. **Extract, Don't Assume**: Base your analysis solely on the provided content
2. **Be Specific**: Choose the most specific document type (e.g., "proforma-invoice" vs "invoice")
3. **Consider Context**: Look at terminology, structure, and purpose together
4. **Regional Variations**: Consider that document types may have regional names (e.g., "invoice" vs "bill")
5. **JSON Only**: Return ONLY the JSON object, no additional text, explanations, or markdown formatting
6. **Handle Uncertainty**: If truly uncertain, use "medium" or "low" confidence and provide alternatives
7. **Standardize Names**: Use common, standardized document type names in lowercase-with-hyphens format

## Example Response

```json
{{
    "document_type": "purchase-order",
    "confidence": "high",
    "primary_indicators": [
        "PO Number: PO-2024-001234",
        "Vendor details with 'SHIP TO' and 'BILL TO' sections",
        "Line items with quantities and unit prices",
        "Terms and conditions section",
        "Signature block for approval"
    ],
    "document_category": "financial",
    "alternative_types": [],
    "reasoning": "Document contains all standard purchase order elements including PO number, vendor/buyer information, itemized products with quantities and prices, and approval signatures. The presence of delivery instructions and payment terms confirms this is a purchase order rather than an invoice or quote."
}}
```

Now analyze the document content provided and respond with your identification in the exact JSON format specified above."""
