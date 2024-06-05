import os
from importlib import import_module

from .interface import ContainerClientInterface


def get_container_client() -> ContainerClientInterface:
    client_path = os.getenv("CONTAINER_CLIENT_PATH", "unstract.worker.clients.docker")
    return import_module(client_path).Client
