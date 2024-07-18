class PromptStudioOutputManagerKeys:
    TOOL_ID = "tool_id"
    PROMPT_ID = "prompt_id"
    PROFILE_MANAGER = "profile_manager"
    DOCUMENT_MANAGER = "document_manager"
    IS_SINGLE_PASS_EXTRACT = "is_single_pass_extract"
    NOTES = "NOTES"


class PromptOutputManagerErrorMessage:
    TOOL_VALIDATION = "tool_id parameter is required"
    TOOL_NOT_FOUND = "Tool not found"
