from typing import Any, Optional

from flask import Blueprint, request
from unstract.prompt_service_v2.constants import IndexingConstants as IKeys
from unstract.prompt_service_v2.constants import PromptServiceContants as PSKeys
from unstract.prompt_service_v2.helper.auth_helper import AuthHelper
from unstract.prompt_service_v2.services.extraction_service import ExtractionService
from unstract.prompt_service_v2.utils.request import validate_request_payload

extraction_bp = Blueprint("extract", __name__)

REQUIRED_FIELDS = [
    "x2text_instance_id",
    "file_path",
    "execution_source",
    "run_id",
]


@AuthHelper.auth_required
@extraction_bp.route("extract", methods=["POST"])
def extract() -> Any:
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload: dict[Any, Any] = request.json
    validate_request_payload(payload, REQUIRED_FIELDS)

    x2text_instance_id: str = payload.get(IKeys.X2TEXT_INSTANCE_ID, "")
    file_path: str = payload.get(IKeys.FILE_PATH, "")
    output_file_path: Optional[str] = payload.get(IKeys.OUTPUT_FILE_PATH, "")
    enable_highlight: bool = payload.get(IKeys.ENABLE_HIGHLIGHT, False)
    usage_kwargs: dict[Any, Any] = payload.get(IKeys.USAGE_KWARGS, {})
    run_id: str = payload.get(PSKeys.RUN_ID, "")
    execution_source = payload.get(IKeys.EXECUTION_SOURCE, None)
    run_id: str = payload.get(PSKeys.RUN_ID, "")

    extracted_text = ExtractionService(
        file_path=file_path,
        x2text_instance_id=x2text_instance_id,
        output_file_path=output_file_path,
        enable_highlight=enable_highlight,
        usage_kwargs=usage_kwargs,
        run_id=run_id,
        execution_source=execution_source,
        platform_key=platform_key,
    )
    response = {IKeys.EXTRACTED_TEXT: extracted_text}
    return response
