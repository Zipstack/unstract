import json
import os

from dotenv import load_dotenv
from flask.testing import FlaskClient
from unstract.prompt_service_v2.helper.auth_helper import AuthHelper

load_dotenv(".env.test")


def test_index(client: FlaskClient, mocker):
    # Mock the AuthHelper to bypass authentication
    mocker.patch.object(AuthHelper, "auth_required", lambda x: x)
    mocker.patch.object(
        AuthHelper,
        "get_token_from_auth_header",
        return_value=os.getenv("TEST_PLATFORM_KEY"),
    )

    # Define the payload
    payload = {
        "tool_id": "mock_tool_id",
        "embedding_instance_id": os.getenv("TEST_EMBEDDING_ID"),
        "vector_db_instance_id": os.getenv("TEST_VECTOR_DB_ID"),
        "x2text_instance_id": os.getenv("TEST_X2TEXT_ID"),
        "chunk_size": os.getenv("TEST_CHUNK_SIZE"),
        "chunk_overlap": os.getenv("TEST_CHUNK_OVERLAP"),
        "execution_source": "ide",
        "run_id": os.getenv("TEST_RUN_ID"),
        "extracted_text": os.getenv("TEST_EXTRACTED_TEXT"),
        "usage_kwargs": {},
        "tags": os.getenv("TEST_TAGS"),
        "reindex": False,
        "enable_highlight": False,
    }

    # Send a POST request to the index endpoint
    try:
        response = client.post(
            "/index", data=json.dumps(payload), content_type="application/json"
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        assert False, f"Test failed due to: {e}"
    # Assert the response
    print(response.data.decode())  # Full response content
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert "doc_id" in response_data


def test_extract(client: FlaskClient, mocker):
    # Mock the AuthHelper to bypass authentication
    mocker.patch.object(AuthHelper, "auth_required", lambda x: x)
    mocker.patch.object(
        AuthHelper,
        "get_token_from_auth_header",
        return_value=os.getenv("TEST_PLATFORM_KEY"),
    )

    # Define the payload
    payload = {
        "x2text_instance_id": os.getenv("X2TEXT_INSTANCE_ID"),
        "file_path": os.getenv("TEST_SOURCE_FILE_PATH"),
        "execution_source": "ide",
        "run_id": "mock_run_id",
        "tags": "mock_tag",
        "output_file_path": os.getenv("TEST_OUTPUT_FILE_PATH"),
        "enable_highlight": False,
        "usage_kwargs": {},
    }

    # Send a POST request to the extract endpoint
    response = client.post(
        "/extract", data=json.dumps(payload), content_type="application/json"
    )

    # Assert the response
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert "extracted_text" in response_data
