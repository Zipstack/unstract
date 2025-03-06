from typing import Any

from flask import Blueprint
from unstract.prompt_service_v2.helper.auth_helper import AuthHelper

extraction_bp = Blueprint("extract", __name__)


@AuthHelper.auth_required
@extraction_bp.route("extract", methods=["POST"])
def extract() -> Any:
    pass


# TODO
