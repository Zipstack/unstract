# Unstract LLMWWhisperer v2 X2Text Adapter

## Env variables

The below env variables are resolved by LLMWhisperer adapter

| Variable                     | Description                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------------- |
| `ADAPTER_LLMW_POLL_INTERVAL` | Time in seconds to wait before polling LLMWhisperer's status API. Defaults to 30s            |
| `ADAPTER_LLMW_MAX_POLLS`     | Total number of times to poll the status API. Defaults to 30                                 |


---
id: llm_whisperer_apis_changelog
---

# Changelog

## Version 2.0.0

:::warning
This version of the API is not backward compatible with the previous version.
:::

### API endpoint

- The base URL for the **V2** APIs is `https://llmwhisperer-api.unstract.com/api/v2`

### Global change in parameter naming

- All use of `whisper-hash` as a parameter has been replaced with `whisper_hash` for consistency. 

### Whisper parameters

#### Added
- `mode` (str, optional): The processing mode. 
- `mark_vertical_lines` (bool, optional): Whether to reproduce vertical lines in the document.
- `mark_horizontal_lines` (bool, optional): Whether to reproduce horizontal lines in the document. 
- `line_splitter_strategy` (str, optional): The line splitter strategy to use. An advanced option for customizing the line splitting process. 
- `lang` (str, optional): The language of the document. 
- `tag` (str, optional): A tag to associate with the document. Used for auditing and tracking purposes.
- `file_name` (str, optional): The name of the file being processed. Used for auditing and tracking purposes.
- `use_webhook` (str, optional): The name of the webhook to call after the document is processed.
- `webhook_metadata` (str, optional): Metadata to send to the webhook after the document is processed.

#### Removed
- `timeout` (int, optional): The timeout for API requests. *There is no sync mode now. All requests are async.*
- `force_text_processing` (bool, optional): Whether to force text processing. *This is feature is removed*
- `ocr_provider` (str, optional): The OCR provider to use. *This is superseded by `mode`*
- `processing_mode` (str, optional): The processing mode. *This is superseded by `mode`*
- `store_metadata_for_highlighting` (bool, optional): Whether to store metadata for highlighting. *Feature is removed. Data still available and set back when retrieve is called*


### New features

#### Webhooks

- Added support for webhooks. You can now register a webhook and use it to receive the processed document.
