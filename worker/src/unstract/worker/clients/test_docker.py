import logging
import os
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound
from unstract.worker.constants import Env

from .docker import Client, DockerContainer

DOCKER_MODULE = "unstract.worker.clients.docker"


@pytest.fixture
def docker_container():
    container = MagicMock()
    return DockerContainer(container)


@pytest.fixture
def docker_client():
    image_name = "test-image"
    image_tag = "latest"
    logger = logging.getLogger("test-logger")
    return Client(image_name, image_tag, logger)


def test_logs(docker_container, mocker):
    """Test the logs method to ensure it yields log lines."""
    mock_container = mocker.patch.object(docker_container, "container")
    mock_container.logs.return_value = [b"log line 1", b"log line 2"]

    logs = list(docker_container.logs(follow=True))
    assert logs == ["log line 1", "log line 2"]


def test_cleanup(docker_container, mocker):
    """Test the cleanup method to ensure it removes the container."""
    mock_container = mocker.patch.object(docker_container, "container")
    mocker.patch(f"{DOCKER_MODULE}.Utils.remove_container_on_exit", return_value=True)

    docker_container.cleanup()
    mock_container.remove.assert_called_once_with(force=True)


def test_cleanup_skip(docker_container, mocker):
    """Test the cleanup method to ensure it doesn't remove the container."""
    mock_container = mocker.patch.object(docker_container, "container")
    mocker.patch(f"{DOCKER_MODULE}.Utils.remove_container_on_exit", return_value=False)

    docker_container.cleanup()
    mock_container.remove.assert_not_called()


def test_client_init(mocker):
    """Test the Client initialization."""
    mock_from_env = mocker.patch(f"{DOCKER_MODULE}.DockerClient.from_env")
    client_instance = Client("test-image", "latest", logging.getLogger("test-logger"))

    mock_from_env.assert_called_once()
    assert client_instance.client is not None


def test_get_image_exists(docker_client, mocker):
    """Test the __image_exists method."""
    # Mock the client object
    mock_client = mocker.patch.object(docker_client, "client")
    # Create a mock for the 'images' attribute
    mock_images = mocker.MagicMock()
    # Attach the mock to the client object
    mock_client.images = mock_images
    # Patch the 'get' method of the 'images' attribute
    mock_images.get.side_effect = ImageNotFound("Image not found")

    assert not docker_client._Client__image_exists("test-image:latest")
    mock_images.get.assert_called_once_with("test-image:latest")


def test_get_image(docker_client, mocker):
    """Test the get_image method."""
    # Patch the client object to control its behavior
    mock_client = mocker.patch.object(docker_client, "client")
    # Patch the images attribute of the client to control its behavior
    mock_images = mocker.MagicMock()
    mock_client.images = mock_images

    # Case 1: Image exists
    mock_images.get.side_effect = MagicMock()  # Mock that image exists
    assert docker_client.get_image() == "test-image:latest"
    mock_images.get.assert_called_once_with("test-image:latest")  # Ensure get is called

    # Case 2: Image does not exist
    mock_images.get.side_effect = ImageNotFound(
        "Image not found"
    )  # Mock that image doesn't exist
    mock_pull = mocker.patch.object(
        docker_client.client.api, "pull"
    )  # Patch pull method
    mock_pull.return_value = iter([{"status": "pulling"}])  # Simulate pull process
    assert docker_client.get_image() == "test-image:latest"
    mock_pull.assert_called_once_with(
        repository="test-image",
        tag="latest",
        stream=True,
        decode=True,
    )


def test_get_container_run_config(docker_client, mocker):
    """Test the get_container_run_config method."""
    os.environ[Env.WORKFLOW_DATA_DIR] = "/source"
    os.environ[Env.FLIPT_SERVICE_AVAILABLE] = "False"
    os.environ[Env.EXECUTION_RUN_DATA_FOLDER_PREFIX] = "/app/workflow_data"
    command = ["echo", "hello"]
    organization_id = "org123"
    workflow_id = "wf123"
    execution_id = "ex123"
    run_id = "run123"

    mocker.patch.object(docker_client, "_Client__image_exists", return_value=True)
    mocker_normalize = mocker.patch(
        "unstract.core.utilities.UnstractUtils.build_tool_container_name",
        return_value="test-image",
    )
    config = docker_client.get_container_run_config(
        command,
        organization_id,
        workflow_id,
        execution_id,
        run_id,
        envs={"KEY": "VALUE"},
        auto_remove=True,
    )

    mocker_normalize.assert_called_once_with(
        tool_image="test-image", tool_version="latest", run_id=run_id
    )
    assert config["name"] == "test-image"
    assert config["image"] == "test-image:latest"
    assert config["command"] == ["echo", "hello"]
    assert config["environment"] == {
        "KEY": "VALUE",
        "EXECUTION_RUN_DATA_FOLDER": ("/app/workflow_data/org123/wf123/ex123"),
    }
    assert config["mounts"] == [
        {
            "type": "bind",
            "source": f"/source/{organization_id}/{workflow_id}/{execution_id}",
            "target": "/data",
        }
    ]


def test_get_container_run_config_without_mount(docker_client, mocker):
    """Test the get_container_run_config method."""
    os.environ[Env.WORKFLOW_DATA_DIR] = "/source"
    command = ["echo", "hello"]
    execution_id = "ex123"
    run_id = "run123"

    mocker.patch.object(docker_client, "_Client__image_exists", return_value=True)
    mocker_normalize = mocker.patch(
        "unstract.core.utilities.UnstractUtils.build_tool_container_name",
        return_value="test-image",
    )
    config = docker_client.get_container_run_config(
        command,
        None,
        None,
        execution_id,
        run_id,
        auto_remove=True,
    )

    mocker_normalize.assert_called_once_with(
        tool_image="test-image", tool_version="latest", run_id=run_id
    )
    assert config["name"] == "test-image"
    assert config["image"] == "test-image:latest"
    assert config["command"] == ["echo", "hello"]
    assert config["environment"] == {}
    assert config["mounts"] == []


def test_run_container(docker_client, mocker):
    """Test the run_container method."""
    # Patch the client object to control its behavior
    mock_client = mocker.patch.object(docker_client, "client")

    config = {
        "name": "test-image",
        "image": "test-image:latest",
        "command": ["echo", "hello"],
        "detach": True,
        "stream": True,
        "auto_remove": True,
        "environment": {"KEY": "VALUE"},
        "stderr": True,
        "stdout": True,
        "network": "",
        "mounts": [],
    }

    assert isinstance(docker_client.run_container(config), DockerContainer)
    mock_client.containers.run.assert_called_once_with(**config)


if __name__ == "__main__":
    pytest.main()
