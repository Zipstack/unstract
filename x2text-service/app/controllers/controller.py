"""Basic Controller."""

import logging
from io import BytesIO
from typing import Any

import requests
from flask import Blueprint, request, send_file

from app.authentication_middleware import (
    AuthenticationMiddleware,
    authentication_middleware,
)
from app.models import X2TextAudit
from app.util import X2TextUtil

basic = Blueprint("basic", __name__)
# Configure the logging format and level
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

UNSTRUCTURED_URL = "unstructured-url"
UNSTRUCTURED_API_KEY = "unstructured-api-key"


@basic.route("/health", methods=["GET"])
def health() -> str:
    logging.info("Checking health from : %s", request.remote_addr)
    return "OK"


@basic.route("/test-connection", methods=["POST"])
@authentication_middleware
def test_connection() -> Any:
    logging.info("Received a test connection request from %s", request.remote_addr)
    form_data = dict(request.form)
    unstructured_api_key = X2TextUtil.get_value_for_key(UNSTRUCTURED_API_KEY, form_data)
    url = X2TextUtil.get_value_for_key(UNSTRUCTURED_URL, form_data)
    if not url:
        return {"message": "Missing or empty url in form data"}, 400

    headers = {
        "accept": "application/json",
        "unstructured-api-key": unstructured_api_key,
    }

    files = {"files": ("test")}

    try:
        response = requests.request(
            "POST",
            url,
            headers=headers,
            data=None,
            files=files,
            timeout=None,
        )

        if response.status_code == 400:
            """Response is 400 as we are not sending a file to test connection.

            But it has passed credential check and url check
            """

            return {"message": "Test connection sucessful"}, 200
        return response.text, response.status_code
    except requests.ConnectionError as e:
        logging.error(e)
        return {"message": "Test connection Failed"}, 400
    except Exception as ex:
        logging.error(ex)
        return {"message": "Test connection Failed"}, 400


@basic.route("/process", methods=["POST"])
@authentication_middleware
def process() -> Any:
    logging.info("Received a doc processing request from %s", request.remote_addr)
    form_data = dict(request.form)
    url = X2TextUtil.get_value_for_key(UNSTRUCTURED_URL, form_data)
    if not url:
        return {"message": "Missing or empty url in form data"}, 400
    if "file" not in request.files:
        return {"message": "No file part"}, 400

    uploaded_file = request.files["file"]

    if uploaded_file.filename == "":
        return {"message": "No selected file"}, 400

    file_size_in_kb = int(request.headers["Content-Length"]) / 1024

    bearer_token = AuthenticationMiddleware.get_token_from_auth_header(request)
    _, org_id = AuthenticationMiddleware.get_organization_from_bearer_token(bearer_token)

    x2_text_audit: X2TextAudit = X2TextAudit.create(
        org_id=org_id,
        file_name=uploaded_file.filename,
        file_type=uploaded_file.mimetype,
        file_size_in_kb=round(file_size_in_kb, 2),
    )

    files = {
        "files": (
            uploaded_file.filename,
            uploaded_file.stream,
            uploaded_file.content_type,
        )
    }

    unstructured_api_key = X2TextUtil.get_value_for_key(UNSTRUCTURED_API_KEY, form_data)
    headers = {
        "accept": "application/json",
        "unstructured-api-key": unstructured_api_key,
    }
    payload = form_data

    response = requests.request(
        "POST",
        url,
        headers=headers,
        data=payload,
        files=files,
        timeout=None,
    )
    if response.ok:
        json_response = response.json()
        response_text = X2TextUtil.get_text_content(json_response)
        file_stream = BytesIO(response_text.encode("utf-8"))
        x2_text_audit.status = "Success"
        x2_text_audit.save()
        return send_file(file_stream, download_name="infile.txt", as_attachment=True)
    x2_text_audit.status = "Failed"
    x2_text_audit.save()
    return_val = X2TextUtil.read_response(response=response)
    logging.error("Text extraction failed: [%s] %s", response.status_code, return_val)
    return return_val, response.status_code
