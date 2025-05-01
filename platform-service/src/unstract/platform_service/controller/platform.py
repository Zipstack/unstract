import json
import uuid
from datetime import datetime
from typing import Any

import redis
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, Request, jsonify, make_response, request
from flask import current_app as app

from unstract.core.flask.exceptions import APIError
from unstract.platform_service.constants import DBTable
from unstract.platform_service.env import Env
from unstract.platform_service.extensions import db
from unstract.platform_service.helper.adapter_instance import (
    AdapterInstanceRequestHelper,
)
from unstract.platform_service.helper.cost_calculation import CostCalculationHelper
from unstract.platform_service.helper.prompt_studio import PromptStudioRequestHelper

platform_bp = Blueprint("platform", __name__)


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


def get_organization_from_bearer_token(token: str) -> tuple[int | None, str]:
    """Fetch organization by platform key.

    Args:
        token (str): platform key

    Returns:
        tuple[int, str]: organization uid and organization identifier
    """
    query = f"""
        SELECT organization_id FROM "{Env.DB_SCHEMA}".{DBTable.PLATFORM_KEY}
        WHERE key=%s
    """
    organization_uid: int = execute_query(query, (token,))
    query_org = f"""
        SELECT organization_id FROM "{Env.DB_SCHEMA}".{DBTable.ORGANIZATION}
        WHERE id=%s
    """
    organization_identifier: str = execute_query(query_org, (organization_uid,))
    return organization_uid, organization_identifier


def execute_query(query: str, params: tuple = ()) -> Any:
    cursor = db.execute_sql(query, params)
    result_row = cursor.fetchone()
    cursor.close()
    if not result_row or len(result_row) == 0:
        return None
    return result_row[0]


def validate_bearer_token(token: str | None) -> bool:
    try:
        if token is None:
            app.logger.error("Authentication failed. Empty bearer token")
            return False

        platform_key_table = DBTable.PLATFORM_KEY
        query = f"""
            SELECT * FROM \"{Env.DB_SCHEMA}\".{platform_key_table}
            WHERE key = '{token}'
        """

        cursor = db.execute_sql(query)
        result_row = cursor.fetchone()
        cursor.close()
        if not result_row or len(result_row) == 0:
            app.logger.error(f"Authentication failed. bearer token not found {token}")
            return False
        platform_key = str(result_row[1])
        is_active = bool(result_row[2])
        if not is_active:
            app.logger.error(
                f"Token is not active. Activate before using it. token {token}"
            )
            return False
        if platform_key != token:
            app.logger.error(f"Authentication failed. Invalid bearer token: {token}")
            return False

    except Exception as e:
        app.logger.error(
            f"Error while validating bearer token: {e}",
            stack_info=True,
            exc_info=True,
        )
        return False
    return True


@platform_bp.route("/page-usage", methods=["POST"], endpoint="page_usage")
@authentication_middleware
def page_usage() -> Any:
    """Usage endpoint."""
    result: dict[str, Any] = {
        "status": "ERROR",
        "error": "",
        "unique_id": "",
    }
    payload: dict[Any, Any] | None = request.json
    if not payload:
        result["error"] = Env.INVALID_PAYLOAD
        return make_response(result, 400)

    bearer_token = get_token_from_auth_header(request)
    _, org_id = get_organization_from_bearer_token(bearer_token)

    page_count = payload.get("page_count", "")
    file_name = payload.get("file_name", "")
    file_size = payload.get("file_size", "")
    file_type = payload.get("file_type", "")
    run_id = payload.get("run_id", "")

    query = f"""
        INSERT INTO \"{Env.DB_SCHEMA}\".{DBTable.PAGE_USAGE} (id, organization_id,
        pages_processed, file_name, file_size, file_type, run_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    usage_id = uuid.uuid4()
    current_time = datetime.now()
    params = (
        usage_id,
        org_id,
        page_count,
        file_name,
        file_size,
        file_type,
        run_id,
        current_time,
    )

    try:
        with db.atomic():
            db.execute_sql(query, params)
            app.logger.info("Page usage recorded with id %s for %s", usage_id, org_id)
            result["status"] = "OK"
            result["unique_id"] = usage_id

            # Check if the subscription_usage table exists
            check_table_query = f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = '{Env.DB_SCHEMA}'
                    AND table_name = '{DBTable.SUBSCRIPTION_USAGE}'
                );
            """
            app.logger.info("Checking if subscription_usage table exists")

            table_exists = db.execute_sql(check_table_query).fetchone()[0]

            if table_exists:
                app.logger.info("subscription_usage table exists")

                # Query to get subscription_id and stripe_subscription_id
                #  from Subscription table.
                subscription_query = f"""
                    SELECT id, stripe_subscription_id
                    FROM \"{Env.DB_SCHEMA}\".{DBTable.SUBSCRIPTION}
                    WHERE organization_id = %s AND is_active = TRUE;
                """
                subscription_query_params = (org_id,)
                app.logger.info(
                    "Executing subscription query for organization %s", org_id
                )

                subscription_result = db.execute_sql(
                    subscription_query, subscription_query_params
                ).fetchone()

                if subscription_result:
                    subscription_id, stripe_subscription_id = subscription_result
                    app.logger.info(
                        "Found subscription: id=%s, stripe_subscription_id=%s",
                        subscription_id,
                        stripe_subscription_id,
                    )

                    stripe_subscription_id = (
                        stripe_subscription_id if stripe_subscription_id else "trial"
                    )

                    # Insert or update data in the subscription_usage table
                    subscription_usage_query = f"""
                        INSERT INTO
                        \"{Env.DB_SCHEMA}\".{DBTable.SUBSCRIPTION_USAGE} (
                        subscription_id, stripe_subscription_id,
                        organization_id, pages_processed, record_date,
                        created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (
                        subscription_id, stripe_subscription_id, record_date
                        ) DO UPDATE
                        SET pages_processed =
                        {DBTable.SUBSCRIPTION_USAGE}.pages_processed
                        + EXCLUDED.pages_processed;
                    """
                    subscription_usage_params = (
                        subscription_id,
                        stripe_subscription_id,
                        org_id,
                        page_count,
                        current_time.date(),
                        current_time,
                        current_time,
                    )
                    app.logger.info("Executing subscription usage insert/update query.")

                    db.execute_sql(subscription_usage_query, subscription_usage_params)
                    app.logger.info("Subscription usage updated for %s", org_id)
                else:
                    app.logger.warning("No active subscription found for %s", org_id)

            return make_response(result, 200)
    except Exception as e:
        app.logger.error(f"Error while creating page usage entry: {e}")
        result["error"] = "Internal Server Error"
        return make_response(result, 500)


@platform_bp.route("/usage", methods=["POST"])
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
    result: dict[str, Any] = {
        "status": "ERROR",
        "error": "",
        "unique_id": "",
    }
    payload: dict[Any, Any] | None = request.json
    if not payload:
        result["error"] = Env.INVALID_PAYLOAD
        return make_response(result, 400)
    bearer_token = get_token_from_auth_header(request)
    organization_uid, org_id = get_organization_from_bearer_token(bearer_token)
    workflow_id = payload.get("workflow_id")
    execution_id = payload.get("execution_id", "")
    adapter_instance_id = payload.get("adapter_instance_id", "")
    run_id = payload.get("run_id")
    usage_type = payload.get("usage_type", "")
    llm_usage_reason = payload.get("llm_usage_reason", "")
    model_name = payload.get("model_name", "")
    provider = payload.get("provider", "")
    embedding_tokens = payload.get("embedding_tokens", 0)
    prompt_tokens = payload.get("prompt_tokens", 0)
    completion_tokens = payload.get("completion_tokens", 0)
    total_tokens = payload.get("total_tokens", 0)
    input_tokens = prompt_tokens
    if usage_type == "embedding":
        input_tokens = embedding_tokens
    cost_in_dollars = 0.0
    if provider:
        cost_calculation_helper = CostCalculationHelper()
        cost_in_dollars = cost_calculation_helper.calculate_cost(
            model_name=model_name,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=completion_tokens,
        )
    usage_id = uuid.uuid4()
    current_time = datetime.now()
    query = f"""
        INSERT INTO \"{Env.DB_SCHEMA}\".{DBTable.TOKEN_USAGE} (
        id, organization_id, workflow_id,
        execution_id, adapter_instance_id, run_id, usage_type,
        llm_usage_reason, model_name, embedding_tokens, prompt_tokens,
        completion_tokens, total_tokens, cost_in_dollars, created_at, modified_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    usage_id = uuid.uuid4()
    current_time = datetime.now()
    params = (
        usage_id,
        organization_uid,
        workflow_id,
        execution_id,
        adapter_instance_id,
        run_id,
        usage_type,
        llm_usage_reason,
        model_name,
        embedding_tokens,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        cost_in_dollars,
        current_time,
        current_time,
    )

    try:
        with db.atomic() as transaction:
            db.execute_sql(query, params)
            transaction.commit()
            app.logger.info("Adapter usage recorded with id %s for %s", usage_id, org_id)
            result["status"] = "OK"
            result["unique_id"] = usage_id
            return jsonify(result, 200)
    except Exception as e:
        app.logger.error(f"Error while creating usage entry: {e}")
        result["error"] = "Internal Server Error"
        return jsonify({"message": "Deleted successfully"})


@platform_bp.route(
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
    _, organization_id = get_organization_from_bearer_token(bearer_token)
    if not organization_id:
        result["error"] = Env.INVALID_ORGANIZATOIN
        return result, 403
    platform_details = {"organization_id": organization_id}
    result = {"status": "OK", "details": platform_details}
    return result, 200


@platform_bp.route("/cache", methods=["POST", "GET", "DELETE"], endpoint="cache")
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
    _, account_id = get_organization_from_bearer_token(bearer_token)
    if request.method == "POST":
        payload: dict[Any, Any] | None = request.json
        if not payload:
            return Env.BAD_REQUEST, 400
        key = payload.get("key")
        value = payload.get("value")
        if key is None or value is None:
            return Env.BAD_REQUEST, 400
        try:
            r = redis.Redis(
                host=Env.REDIS_HOST,
                port=Env.REDIS_PORT,
                username=Env.REDIS_USERNAME,
                password=Env.REDIS_PASSWORD,
            )
            redis_key = f"{account_id}:{key}"
            r.set(redis_key, value)
            r.close()
        except Exception as e:
            raise APIError(message=f"Error while caching data: {e}") from e
    elif request.method == "GET":
        key = request.args.get("key")
        try:
            r = redis.Redis(
                host=Env.REDIS_HOST,
                port=Env.REDIS_PORT,
                username=Env.REDIS_USERNAME,
                password=Env.REDIS_PASSWORD,
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
            raise APIError(message=f"Error while getting cached data: {e}") from e
    elif request.method == "DELETE":
        key = request.args.get("key")
        try:
            r = redis.Redis(
                host=Env.REDIS_HOST,
                port=Env.REDIS_PORT,
                username=Env.REDIS_USERNAME,
                password=Env.REDIS_PASSWORD,
            )
            redis_key = f"{account_id}:{key}"
            app.logger.info(f"Deleting cached data for key: {redis_key}")
            r.delete(redis_key)
            r.close()
            return "OK", 200
        except Exception as e:
            raise APIError(message=f"Error while deleting cached data: {e}") from e
    else:
        raise APIError(message="Method Not Allowed", code=405)

    return "OK", 200


@platform_bp.route(
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
    organization_uid, organization_id = get_organization_from_bearer_token(bearer_token)
    if not organization_id:
        return Env.INVALID_ORGANIZATOIN, 403

    adapter_instance_id = request.args.get("adapter_instance_id")

    try:
        data_dict = AdapterInstanceRequestHelper.get_adapter_instance_from_db(
            organization_id=organization_id,
            adapter_instance_id=adapter_instance_id,
            organization_uid=organization_uid,
        )

        f: Fernet = Fernet(Env.ENCRYPTION_KEY.encode("utf-8"))

        data_dict["adapter_metadata"] = json.loads(
            f.decrypt(bytes(data_dict.pop("adapter_metadata_b")).decode("utf-8"))
        )

        return jsonify(data_dict)
    except InvalidToken:
        msg = (
            "Platform encryption key for storing adapter credentials has "
            "changed! All adapters are inaccessible. Please inform "
            "the platform admin immediately."
        )
        app.logger.error(
            f"Error while getting db adapter settings for: "
            f"{adapter_instance_id}, Error: {msg}"
        )
        raise APIError(message=msg, code=403)
    except Exception as e:
        msg = f"Error while getting db adapter settings for {adapter_instance_id}: {e}"
        raise APIError(message=msg)


@platform_bp.route(
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
    _, organization_id = get_organization_from_bearer_token(bearer_token)
    if not organization_id:
        return Env.INVALID_ORGANIZATOIN, 403

    prompt_registry_id = request.args.get("prompt_registry_id")

    try:
        data_dict = PromptStudioRequestHelper.get_prompt_instance_from_db(
            organization_id=organization_id,
            prompt_registry_id=prompt_registry_id,
        )
        return jsonify(data_dict)
    except Exception as e:
        if isinstance(e, APIError):
            raise e
        msg = (
            f"Error while getting data for Prompt Studio project "
            f"{prompt_registry_id}: {e}"
        )
        raise APIError(message=msg) from e
