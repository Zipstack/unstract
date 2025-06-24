"""
Controller for agentic context extraction v2 API endpoint.
"""
from typing import Any, Dict, Optional
import logging

from flask import Blueprint, request, current_app

from unstract.prompt_service.constants import IndexingConstants as IKeys
from unstract.prompt_service.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service.helpers.auth import AuthHelper
from unstract.prompt_service.agents.context_extraction.orchestrator import AgentyContextExtractorV2
from unstract.prompt_service.utils.request import validate_request_payload

extraction_v2_bp = Blueprint("extract_v2", __name__)

REQUIRED_FIELDS = [
    "x2text_instance_id",
    "file_path",
    "execution_source",
    "run_id",
]


@AuthHelper.auth_required
@extraction_v2_bp.route("/extract/v2", methods=["POST"])
def extract_v2() -> Any:
    """
    API endpoint for agentic context extraction v2.
    Uses AutoGen framework with X2Text for context extraction.
    """
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload: dict[Any, Any] = request.json
    validate_request_payload(payload, REQUIRED_FIELDS)

    x2text_instance_id: str = payload.get(IKeys.X2TEXT_INSTANCE_ID, "")
    file_path: str = payload.get(IKeys.FILE_PATH, "")
    output_file_path: str | None = payload.get(IKeys.OUTPUT_FILE_PATH, "")
    enable_highlight: bool = payload.get(IKeys.ENABLE_HIGHLIGHT, False)
    usage_kwargs: dict[Any, Any] = payload.get(IKeys.USAGE_KWARGS, {})
    run_id: str = payload.get(PSKeys.RUN_ID, "")
    execution_source = payload.get(IKeys.EXECUTION_SOURCE, None)
    tags: str = payload.get(IKeys.TAGS, "")
    tool_exec_metadata = payload.get(IKeys.TOOL_EXECUTION_METATADA, {})
    execution_run_data_folder = payload.get(IKeys.EXECUTION_DATA_DIR, "")
    
    # Optional model configuration
    model_config = payload.get("model_config", {})

    # Initialize the agentic extractor with model config
    extractor = AgentyContextExtractorV2(platform_key=platform_key, model_config=model_config)
    
    # Extract context using the agent-based approach
    extracted_text = extractor.extract_context(
        file_path=file_path,
        x2text_instance_id=x2text_instance_id,
        output_file_path=output_file_path,
        enable_highlight=enable_highlight,
        usage_kwargs=usage_kwargs,
        run_id=run_id,
        execution_source=execution_source,
        tags=tags,
        tool_exec_metadata=tool_exec_metadata,
        execution_run_data_folder=execution_run_data_folder,
    )
    
    # Return the extracted text
    response = {IKeys.EXTRACTED_TEXT: extracted_text}
    return response
