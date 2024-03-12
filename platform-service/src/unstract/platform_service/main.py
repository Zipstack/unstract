import datetime
import json
import logging
import os
import uuid
from typing import Any, Literal, Optional

import peewee
import redis
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import Flask, Request, Response, jsonify, request
from unstract.platform_service.exceptions import CustomException
from unstract.platform_service.helper import (
    AdapterInstanceRequestHelper,
    PromptStudioRequestHelper,
)
from unstract.platform_service.utils import EnvManager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s : %(message)s",
)
# Configuring envs
MAX_FILE_SIZE = 100 * 1024 * 1024
INVALID_ORGANIZATOIN = "Invalid organization"
INVALID_PAYLOAD = "Bad Request / No payload"
BAD_REQUEST = "Bad Request"
REDIS_HOST = EnvManager.get_required_setting("REDIS_HOST")
REDIS_PORT = int(EnvManager.get_required_setting("REDIS_PORT", 6379))
REDIS_USERNAME = os.environ.get("REDIS_USERNAME")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
PG_BE_HOST = os.environ.get("PG_BE_HOST")
PG_BE_PORT = int(os.environ.get("PG_BE_PORT", 5432))
PG_BE_USERNAME = os.environ.get("PG_BE_USERNAME")
PG_BE_PASSWORD = os.environ.get("PG_BE_PASSWORD")
PG_BE_DATABASE = os.environ.get("PG_BE_DATABASE")
ENCRYPTION_KEY = EnvManager.get_required_setting("ENCRYPTION_KEY")

EnvManager.raise_for_missing_envs()

# TODO: Follow Flask best practices and refactor accordingly
app = Flask("platform_service")

be_db = peewee.PostgresqlDatabase(
    PG_BE_DATABASE,
    user=PG_BE_USERNAME,
    password=PG_BE_PASSWORD,
    host=PG_BE_HOST,
    port=PG_BE_PORT,
)
be_db.init(PG_BE_DATABASE)
be_db.connect()


class UnstractUsage(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = peewee.DateTimeField(default=datetime.datetime.now)
    organization_id = peewee.CharField()
    workflow_id = peewee.CharField()
    execution_id = peewee.CharField()
    status = peewee.CharField()
    usage_type = peewee.CharField()
    external_service = peewee.CharField()
    tokens_valid = peewee.BooleanField(default=False)
    embedding_tokens = peewee.IntegerField()
    prompt_tokens = peewee.IntegerField()
    completion_tokens = peewee.IntegerField()
    total_tokens = peewee.IntegerField()
    usage_value_valid = peewee.BooleanField(peewee.BooleanField(default=False))
    usage_value = peewee.FloatField()
    usage_units = peewee.CharField()

    class Meta:
        database = be_db  # This model uses the "BE_DB" database.
        table_name = "unstract_usage"


UnstractUsage.create_table()


def get_token_from_auth_header(request: Request) -> Any:
    try:
        bearer_token = request.headers.get("Authorization")
        if not bearer_token:
            return None
        token = bearer_token.strip().replace("Bearer ", "")
        return token
    except Exception as e:
        app.logger.info(f"Exception while getting token {e}")
        return None


def authentication_middleware(func: Any) -> Any:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = get_token_from_auth_header(request)
        # Check if bearer token exists and validate it
        if not token or not validate_bearer_token(token):
            return "Unauthorized", 401

        return func(*args, **kwargs)

    return wrapper


def get_account_from_bearer_token(token: Optional[str]) -> str:
    query = (
        "SELECT organization_id FROM account_platformkey "
        f"WHERE key='{token}'"
    )
    organization = execute_query(query)
    query_org = (
        "SELECT schema_name FROM account_organization "
        f"WHERE id='{organization}'"
    )
    schema_name: str = execute_query(query_org)
    return schema_name


def execute_query(query: str) -> Any:
    cursor = be_db.execute_sql(query)
    result_row = cursor.fetchone()
    cursor.close()
    if not result_row or len(result_row) == 0:
        return None
    return result_row[0]


def validate_bearer_token(token: Optional[str]) -> bool:
    try:
        if token is None:
            app.logger.error("Authentication failed. Empty bearer token")
            return False

        query = f"SELECT * FROM account_platformkey WHERE key = '{token}'"
        cursor = be_db.execute_sql(query)
        result_row = cursor.fetchone()
        cursor.close()
        if not result_row or len(result_row) == 0:
            app.logger.error(
                f"Authentication failed. bearer token not found {token}"
            )
            return False
        platform_key = str(result_row[1])
        is_active = bool(result_row[2])
        if not is_active:
            app.logger.error(
                f"Token is not active. Activate before using it. token {token}"
            )
            return False
        if platform_key != token:
            app.logger.error(
                f"Authentication failed. Invalid bearer token: {token}"
            )
            return False

    except Exception as e:
        app.logger.error(f"Error while validating bearer token: {e}")
        return False
    return True


@app.route("/health", methods=["GET"], endpoint="health_check")
def health_check() -> str:
    return "OK"


@app.route("/usage", methods=["POST"])
@authentication_middleware
def usage() -> Any:
    """Usage endpoint.
    Sample Usage:
    curl -X POST  http://localhost:3001/usage \
    -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
    -H "Content-Type: application/json" \
    -d '{
            "workflow_id": "test",
            "execution_id": "test",
            ....
        }'
    """
    bearer_token = get_token_from_auth_header(request)
    organization_id = get_account_from_bearer_token(bearer_token)
    result: dict[str, Any] = {
        "status": "ERROR",
        "error": "",
        "unique_id": "",
    }
    payload: Optional[dict[Any, Any]] = request.json
    if not payload:
        result["error"] = INVALID_PAYLOAD
        return result, 400

    org_id = organization_id
    workflow_id = payload.get("workflow_id")
    execution_id = payload.get("execution_id", "")
    status = payload.get("status", "")
    usage_type = payload.get("usage_type", "")
    external_service = payload.get("external_service", "")
    tokens_valid = payload.get("tokens_valid", False)
    embedding_tokens = payload.get("embedding_tokens", 0)
    prompt_tokens = payload.get("prompt_tokens", 0)
    completion_tokens = payload.get("completion_tokens", 0)
    total_tokens = payload.get("total_tokens", 0)
    usage_value_valid = payload.get("usage_value_valid", False)
    usage_value = payload.get("usage_value", 0.0)
    usage_units = payload.get("usage_units", "")

    usage: UnstractUsage = UnstractUsage.create(
        organization_id=org_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        status=status,
        usage_type=usage_type,
        external_service=external_service,
        tokens_valid=tokens_valid,
        embedding_tokens=embedding_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        usage_value_valid=usage_value_valid,
        usage_value=usage_value,
        usage_units=usage_units,
    )
    app.logger.info(
        "Entry created with id %s for %s", usage.id, organization_id
    )
    result["status"] = "OK"
    result["unique_id"] = usage.id
    return result


@app.route(
    "/platform_details",
    methods=["GET"],
    endpoint="platform_details",
)
@authentication_middleware
def platform_details() -> Any:
    """Fetch details associated with the platform. This uses the authenticated
    request to obtain details related to the platform key.

    Sample Usage:
    curl -X GET
    -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    http://localhost:3001/platform_details
    """
    result: dict[str, Any] = {"status": "ERROR", "error": ""}
    bearer_token = get_token_from_auth_header(request)
    organization_id = get_account_from_bearer_token(bearer_token)
    if not organization_id:
        result["error"] = INVALID_ORGANIZATOIN
        return result, 403
    platform_details = {"organization_id": organization_id}
    result = {"status": "OK", "details": platform_details}
    return result, 200


@app.route("/ping", methods=["GET"])
def ping() -> Literal["Pong"]:
    return "Pong"


@app.route("/cache", methods=["POST", "GET", "DELETE"], endpoint="cache")
@authentication_middleware
def cache() -> Any:
    """Cache endpoint.

    Sample Usage:
    curl -X POST  http://localhost:3001/cache \
    -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
    -H "Content-Type: application/json" \
    -d '{"key": "key1", "value": "value1"}'

    curl -X GET
    -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    http://localhost:3001/cache?key=key1
    """
    bearer_token = get_token_from_auth_header(request)
    account_id = get_account_from_bearer_token(bearer_token)
    if not REDIS_HOST:
        app.logger.error("REDIS_HOST not set")
        return "Internal Server Error", 500
    if request.method == "POST":
        payload: Optional[dict[Any, Any]] = request.json
        if not payload:
            return BAD_REQUEST, 400
        key = payload.get("key")
        value = payload.get("value")
        if key is None or value is None:
            return BAD_REQUEST, 400
        try:
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                username=REDIS_USERNAME,
                password=REDIS_PASSWORD,
            )
            redis_key = f"{account_id}:{key}"
            r.set(redis_key, value)
            r.close()
        except Exception as e:
            app.logger.error(f"Error while caching data: {e}")
            return "Internal Server Error", 500
    elif request.method == "GET":
        key = request.args.get("key")
        try:
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                username=REDIS_USERNAME,
                password=REDIS_PASSWORD,
            )
            redis_key = f"{account_id}:{key}"
            app.logger.info(f"Getting cached data for key: {redis_key}")
            value = r.get(redis_key)
            r.close()
            if value is None:
                return "Not Found", 404
            else:
                return value, 200
        except Exception as e:
            app.logger.error(f"Error while getting cached data: {e}")
            return "Internal Server Error", 500
    elif request.method == "DELETE":
        key = request.args.get("key")
        try:
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                username=REDIS_USERNAME,
                password=REDIS_PASSWORD,
            )
            redis_key = f"{account_id}:{key}"
            app.logger.info(f"Deleting cached data for key: {redis_key}")
            r.delete(redis_key)
            r.close()
            return "OK", 200
        except Exception as e:
            app.logger.error(f"Error while deleting cached data: {e}")
            return "Internal Server Error", 500

    return "OK", 200


@app.route(
    "/adapter_instance",
    methods=["GET"],
    endpoint="adapter_instance",
)
@authentication_middleware
def adapter_instance() -> Any:
    """Fetch Adapter instance.

    Sample Usage:
    curl -X GET
    -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    http://localhost:3001/db/adapter_instance/adapter_instance_id=id1
    """
    bearer_token = get_token_from_auth_header(request)
    organization_id = get_account_from_bearer_token(bearer_token)
    if not organization_id:
        return INVALID_ORGANIZATOIN, 403

    if request.method == "GET":
        adapter_instance_id = request.args.get("adapter_instance_id")

        try:
            data_dict = (
                AdapterInstanceRequestHelper.get_adapter_instance_from_db(
                    db_instance=be_db,
                    organization_id=organization_id,
                    adapter_instance_id=adapter_instance_id,
                )
            )

            f: Fernet = Fernet(ENCRYPTION_KEY.encode("utf-8"))

            data_dict["adapter_metadata"] = json.loads(
                f.decrypt(
                    bytes(data_dict.pop("adapter_metadata_b")).decode("utf-8")
                )
            )

            return jsonify(data_dict)
        except Exception as e:
            print(e)
            app.logger.error(
                f"Error while getting db adapter settings for: "
                f"{adapter_instance_id} Error: {str(e)}"
            )
            return "Internal Server Error", 500
    return "Method Not Allowed", 405


@app.route(
    "/custom_tool_instance",
    methods=["GET"],
    endpoint="custom_tool_instance",
)
@authentication_middleware
def custom_tool_instance() -> Any:
    """Fetching exported custom tool instance.

    Sample Usage:
    curl -X GET
    -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    http://localhost:3001/db/custom_tool_instance/prompt_registry_id=id1
    """
    bearer_token = get_token_from_auth_header(request)
    organization_id = get_account_from_bearer_token(bearer_token)
    if not organization_id:
        return INVALID_ORGANIZATOIN, 403

    if request.method == "GET":
        prompt_registry_id = request.args.get("prompt_registry_id")

        try:
            data_dict = PromptStudioRequestHelper.get_prompt_instance_from_db(
                db_instance=be_db,
                organization_id=organization_id,
                prompt_registry_id=prompt_registry_id,
            )
            return jsonify(data_dict)
        except Exception as e:
            print(e)
            app.logger.error(
                f"Error while getting db adapter settings for: "
                f"{prompt_registry_id} Error: {str(e)}"
            )
            return "Internal Server Error", 500
    return "Method Not Allowed", 405


@app.errorhandler(CustomException)
def handle_custom_exception(error: Any) -> tuple[Response, Any]:
    response = jsonify({"error": error.message})
    response.status_code = error.code  # You can customize the HTTP status code
    return jsonify(response), error.code


if __name__ == "__main__":
    # Start the server
    app.run()
