import logging
import os
from importlib import import_module

from .interface import ContainerClientInterface

logger = logging.getLogger(__name__)


class ContainerClientHelper:
    @staticmethod
    def get_container_client() -> ContainerClientInterface:
        client_path = os.getenv(
            "CONTAINER_CLIENT_PATH", "unstract.worker.clients.docker"
        )
        logger.info("Loading the container client from path:", client_path)
        return import_module(client_path).Client

    @staticmethod
    def normalize_container_name(name: str, execution_id: str) -> str:
        return name.replace("/", "-") + "-" + execution_id
