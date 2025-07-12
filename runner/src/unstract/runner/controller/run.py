from typing import Any

from flask import Blueprint, abort, request
from flask import current_app as app

from unstract.runner.runner import UnstractRunner

# Define a Blueprint with a root URL path
run_bp = Blueprint("run", __name__)


# Run container
@run_bp.route("container/run", methods=["POST"])
def run_container() -> Any | None:
    data = request.get_json()
    image_name = data["image_name"]
    image_tag = data["image_tag"]
    organization_id = data["organization_id"]
    workflow_id = data["workflow_id"]
    execution_id = data["execution_id"]
    file_execution_id = data["file_execution_id"]
    container_name = data["container_name"]
    settings = data["settings"]
    envs = data["envs"]
    messaging_channel = data["messaging_channel"]

    runner = UnstractRunner(image_name, image_tag, app)
    result = runner.run_container(
        container_name=container_name,
        organization_id=organization_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        file_execution_id=file_execution_id,
        settings=settings,
        envs=envs,
        messaging_channel=messaging_channel,
    )
    return result


@run_bp.route("container/run-status", methods=["GET"])
def run_status() -> Any | None:
    data = request.args
    container_name = data.get("container_name")
    runner = UnstractRunner(None, None, app)
    status = runner.get_container_status(
        container_name=container_name,
    )
    return {"status": status}


@run_bp.route("container/remove", methods=["DELETE"])
def remove_container() -> Any | None:
    data = request.get_json()
    container_name = data["container_name"]
    runner = UnstractRunner(None, None, app)
    result = runner.remove_container_by_name(container_name)
    return result


@run_bp.route("container/<command>", methods=["GET"])
def run_command(command: str) -> Any | None:
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
    runner = UnstractRunner(image_name, image_tag, app)

    return runner.run_command(command)
