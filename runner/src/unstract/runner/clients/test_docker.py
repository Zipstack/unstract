import logging
import os
from unittest.mock import MagicMock

import pytest

from docker.errors import ImageNotFound
from unstract.runner.constants import Env

from .docker_client import Client, DockerContainer

DOCKER_MODULE = "unstract.runner.clients.docker_client"


@pytest.fixture
def docker_container():
    container = MagicMock()
    logger = logging.getLogger("test-logger")
    return DockerContainer(container, logger)


@pytest.fixture
def docker_client(mocker):
    # Mock the DockerClient.from_env to avoid connecting to a real Docker daemon
    mock_client = MagicMock()
    mocker.patch(f"{DOCKER_MODULE}.DockerClient.from_env", return_value=mock_client)
    # Mock the private login method to avoid any actual login attempts
    mocker.patch(f"{DOCKER_MODULE}.Client._Client__private_login")

    image_name = "test-image"
    image_tag = "latest"
    logger = logging.getLogger("test-logger")
    return Client(image_name, image_tag, logger, sidecar_enabled=False)


@pytest.fixture
def docker_client_with_sidecar():
    image_name = "test-image"
    image_tag = "latest"
    logger = logging.getLogger("test-logger")
    return Client(image_name, image_tag, logger, sidecar_enabled=True)


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
    # Create a mock for the 'images' attribute
    mock_images = mocker.MagicMock()
    # Attach the mock to the client object
    docker_client.client.images = mock_images
    # Patch the 'get' method of the 'images' attribute
    mock_images.get.side_effect = ImageNotFound("Image not found")

    assert not docker_client._Client__image_exists("test-image:latest")
    mock_images.get.assert_called_once_with("test-image:latest")


def test_get_image(docker_client, mocker):
    """Test the get_image method."""
    # Create a mock for the 'images' attribute
    mock_images = mocker.MagicMock()
    # Attach the mock to the client object
    docker_client.client.images = mock_images
    # Create a mock for the 'api' attribute
    mock_api = mocker.MagicMock()
    # Attach the mock to the client object
    docker_client.client.api = mock_api

    # Case 1: Image exists
    mock_images.get.side_effect = None  # Mock that image exists
    assert docker_client.get_image() == "test-image:latest"
    mock_images.get.assert_called_with("test-image:latest")  # Ensure get is called

    # Case 2: Image does not exist
    mock_images.get.side_effect = ImageNotFound(
        "Image not found"
    )  # Mock that image doesn't exist
    mock_pull = mocker.patch.object(docker_client.client.api, "pull")  # Patch pull method
    mock_pull.return_value = iter([{"status": "pulling"}])  # Simulate pull process
    assert docker_client.get_image() == "test-image:latest"
    mock_api.pull.assert_called_with(
        repository="test-image",
        tag="latest",
        stream=True,
        decode=True,
    )


def test_get_container_run_config(docker_client, mocker):
    """Test the get_container_run_config method."""
    command = ["echo", "hello"]
    file_execution_id = "run123"
    shared_log_dir = "/shared/logs"

    mocker.patch.object(docker_client, "_Client__image_exists", return_value=True)
    mocker_normalize = mocker.patch(
        "unstract.core.utilities.UnstractUtils.build_tool_container_name",
        return_value="test-image",
    )
    config = docker_client.get_container_run_config(
        command,
        file_execution_id,
        shared_log_dir,
        envs={"KEY": "VALUE"},
        auto_remove=True,
    )

    mocker_normalize.assert_called_once_with(
        tool_image="test-image",
        tool_version="latest",
        file_execution_id=file_execution_id,
    )
    assert config["name"] == "test-image"
    assert config["image"] == "test-image:latest"
    assert config["entrypoint"] == ["echo", "hello"]
    assert config["environment"] == {"KEY": "VALUE"}
    assert config["mounts"] == []


def test_get_container_run_config_without_mount(docker_client, mocker):
    """Test the get_container_run_config method."""
    os.environ[Env.EXECUTION_DATA_DIR] = "/source"
    command = ["echo", "hello"]
    file_execution_id = "run123"
    shared_log_dir = "/shared/logs"

    mocker.patch.object(docker_client, "_Client__image_exists", return_value=True)
    mocker_normalize = mocker.patch(
        "unstract.core.utilities.UnstractUtils.build_tool_container_name",
        return_value="test-image",
    )
    config = docker_client.get_container_run_config(
        command, file_execution_id, shared_log_dir, auto_remove=True
    )

    mocker_normalize.assert_called_once_with(
        tool_image="test-image",
        tool_version="latest",
        file_execution_id=file_execution_id,
    )
    assert config["name"] == "test-image"
    assert config["image"] == "test-image:latest"
    assert config["entrypoint"] == ["echo", "hello"]
    assert config["environment"] == {}
    assert config["mounts"] == []


def test_run_container(docker_client, mocker):
    """Test the run_container method."""
    # Create a mock for the containers.run method
    mock_container = mocker.MagicMock()
    docker_client.client.containers.run.return_value = mock_container

    config = {
        "name": "test-image",
        "image": "test-image:latest",
        "entrypoint": ["echo", "hello"],
        "detach": True,
        "stream": True,
        "auto_remove": True,
        "environment": {"KEY": "VALUE"},
        "stderr": True,
        "stdout": True,
        "network": "",
        "mounts": [],
    }

    result = docker_client.run_container(config)
    assert isinstance(result, DockerContainer)
    docker_client.client.containers.run.assert_called_once_with(**config)


def test_get_image_for_sidecar(docker_client_with_sidecar, mocker):
    """Test the get_image method."""
    # Mock environment variables
    mocker.patch.dict(
        os.environ,
        {
            Env.TOOL_SIDECAR_IMAGE_NAME: "test-sidecar-image",
            Env.TOOL_SIDECAR_IMAGE_TAG: "latest",
        },
    )

    # Re-initialize client to pick up mocked env vars
    docker_client_with_sidecar.sidecar_image_name = os.getenv(Env.TOOL_SIDECAR_IMAGE_NAME)
    docker_client_with_sidecar.sidecar_image_tag = os.getenv(Env.TOOL_SIDECAR_IMAGE_TAG)

    # Patch the client object to control its behavior
    mock_client = mocker.patch.object(docker_client_with_sidecar, "client")
    # Patch the images attribute of the client to control its behavior
    mock_images = mocker.MagicMock()
    mock_client.images = mock_images

    # Case 1: Image exists
    mock_images.get.side_effect = MagicMock()
    assert (
        docker_client_with_sidecar.get_image(sidecar=True) == "test-sidecar-image:latest"
    )
    mock_images.get.assert_called_once_with("test-sidecar-image:latest")

    # Case 2: Image does not exist
    mock_images.get.side_effect = ImageNotFound("Image not found")
    mock_pull = mocker.patch.object(docker_client_with_sidecar.client.api, "pull")
    mock_pull.return_value = iter([{"status": "pulling"}])
    assert (
        docker_client_with_sidecar.get_image(sidecar=True) == "test-sidecar-image:latest"
    )
    mock_pull.assert_called_once_with(
        repository="test-sidecar-image",
        tag="latest",
        stream=True,
        decode=True,
    )


def test_sidecar_container(docker_client_with_sidecar, mocker):
    """Test the sidecar_container method."""
    # Patch the client object to control its behavior
    mock_client = mocker.patch.object(docker_client_with_sidecar, "client")

    config = {
        "name": "test-image",
        "image": "test-image:latest",
        "entrypoint": ["echo", "hello"],
        "detach": True,
        "stream": False,
        "auto_remove": True,
        "environment": {"KEY": "VALUE"},
        "stderr": True,
        "stdout": True,
        "network": "",
        "mounts": [
            {
                "Type": "volume",
                "Source": "logs-test-id",
                "Target": "/shared",
            }
        ],
    }

    shared_log_dir = "/shared/logs"
    test_config = docker_client_with_sidecar.get_container_run_config(
        command=["echo", "hello"],
        file_execution_id="test-id",
        shared_log_dir=shared_log_dir,
        envs={"KEY": "VALUE"},
        auto_remove=True,
        sidecar=True,
    )

    # Test the actual configuration generated
    assert test_config["stream"] is False
    assert test_config["mounts"] == config["mounts"]
    assert isinstance(
        docker_client_with_sidecar.run_container(test_config), DockerContainer
    )
    mock_client.containers.run.assert_called_once_with(**test_config)


if __name__ == "__main__":
    pytest.main()
