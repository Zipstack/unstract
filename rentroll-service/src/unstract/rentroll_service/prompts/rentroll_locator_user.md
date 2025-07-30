# Page Analysis Task - Decision Making Only

You will be provided with individual pages from a document. Your ONLY task is to analyze each page and determine whether it contains rent roll data.

## Your Role

**ANALYSIS ONLY** - You make the decision, you do NOT handle the content extraction.

For each page:
1. **Analyze the page content** using your rent roll detection knowledge from the system prompt
2. **Make a determination** whether the page contains rent roll data (YES/NO)
3. **Return your decision** in the specified JSON format
4. **Do NOT extract, modify, or reformat any content** - that will be handled programmatically

## Decision Process

For each page you analyze:
1. Examine the content carefully against rent roll indicators from your system prompt
2. Apply the detection criteria to determine if it qualifies as rent roll data
3. Make a clear YES/NO determination with confidence level
4. Provide reasoning for your decision

## Required Output Format

You must respond with ONLY this JSON structure:

```json
{
    "page_number": X,
    "detection_result": "YES" or "NO", 
    "confidence_level": "HIGH" or "MEDIUM" or "LOW",
    "reasoning": "Brief explanation of your decision"
}
```

## Important Notes

- **DECISION MAKING ONLY** - You analyze and decide, you do not extract content
- Use your comprehensive rent roll detection criteria from the system prompt
- Trust your analysis based on the rent roll indicators
- Be consistent in your decision making
- If the page contains rent roll data, just say "YES" - the content will be extracted programmatically
- If the page does not contain rent roll data, say "NO" and explain why

Your analysis determines which pages get extracted, but you do not handle the actual extraction process.