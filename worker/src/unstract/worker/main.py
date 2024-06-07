from typing import Any, Optional

from flask import Blueprint, Flask, Response, abort, jsonify, request
from unstract.worker import UnstractWorker
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

    worker = UnstractWorker(image_name, image_tag, app)
    result = worker.run_container(
        organization_id=organization_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        settings=settings,
        envs=envs,
        messaging_channel=messaging_channel,
    )
    return result


@bp.route("container/<command>", methods=["GET"])
def run_command(command: str) -> Optional[Any]:
    """Endpoint which will can execute any of the below commands.

    Args:
        command (str): AnyOf("properties","spec","variables","icon")

    Returns:
        Optional[Any]: Response from container for the specific command.
                       Returns None in case of error.
    """
    if command not in {"properties", "spec", "variables", "icon"}:
        abort(404)
    image_name = request.args.get("image_name")
    image_tag = request.args.get("image_tag")
    worker = UnstractWorker(image_name, image_tag, app)

    return worker.run_command(command)


# Register the Blueprint with the Flask app
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(debug=True)
