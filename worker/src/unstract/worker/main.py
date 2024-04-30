from typing import Any, Optional

from flask import Blueprint, Flask, Response, jsonify, request
from unstract.worker import UnstractWorker
from unstract.worker.constants import ToolCommandKey
from unstract.worker.utils import Utils

app = Flask(__name__)

log_level = Utils.get_log_level()
app.logger.setLevel(log_level.value)

# Define a Blueprint with a root URL path
bp = Blueprint("v1", __name__, url_prefix="/v1/api")


# Define a route to ping test
@bp.route("/ping", methods=["GET"])
def get_items() -> Response:
    return jsonify({"message": "pong!!!"})


# Run container
@bp.route("container/run", methods=["POST"])
def run_container() -> Optional[Any]:
    data = request.get_json()
    image_name = data["image_name"]
    image_tag = data["image_tag"]
    organization_id = data["organization_id"]
    workflow_id = data["workflow_id"]
    execution_id = data["execution_id"]
    settings = data["settings"]
    envs = data["envs"]
    messaging_channel = data["messaging_channel"]

    worker = UnstractWorker(image_name, image_tag, app=app)
    result = worker.run_container(
        organization_id=organization_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        settings=settings,
        envs=envs,
        messaging_channel=messaging_channel,
    )
    return result


@bp.route("container/spec", methods=["GET"])
def get_spec() -> Optional[Any]:
    return get_resource(ToolCommandKey.SPEC)


@bp.route("container/properties", methods=["GET"])
def get_properties() -> Optional[Any]:
    return get_resource(ToolCommandKey.PROPERTIES)


@bp.route("container/icon", methods=["GET"])
def get_icon() -> Optional[Any]:
    return get_resource(ToolCommandKey.ICON)


@bp.route("container/variables", methods=["GET"])
def get_variables() -> Optional[Any]:
    return get_resource(ToolCommandKey.VARIABLES)


def get_resource(endpoint: str) -> Optional[Any]:
    image_name = request.args.get("image_name")
    image_tag = request.args.get("image_tag")
    worker = UnstractWorker(image_name, image_tag)

    if endpoint == ToolCommandKey.PROPERTIES:
        return worker.get_properties()
    elif endpoint == ToolCommandKey.ICON:
        return worker.get_icon()
    elif endpoint == ToolCommandKey.VARIABLES:
        return worker.get_variables()
    elif endpoint == ToolCommandKey.SPEC:
        return worker.get_spec()
    else:
        return None


# Register the Blueprint with the Flask app
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(debug=True)
