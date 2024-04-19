from abc import ABC, abstractmethod


class UnstratcWorkerInterface(ABC):
    @abstractmethod
    def __init__(self, image_name: str, image_tag: str):
        pass

    @abstractmethod
    def _get_image(self) -> str:
        pass

    @abstractmethod
    def _image_exists(self, image_name_with_tag: str) -> bool:
        pass

    @abstractmethod
    def normalize_container_name(self, name: str) -> str:
        pass

    @abstractmethod
    def stream_logs(self, container):
        pass

    @abstractmethod
    def get_valid_log_message(self, log_line: str):
        pass

    @abstractmethod
    def process_log_message(self, log_line: str, channel):
        pass

    @abstractmethod
    def is_valid_log_type(self, log_type: str) -> bool:
        pass

    @abstractmethod
    def get_log_type(self, log_dict: dict) -> str:
        pass

    @abstractmethod
    def get_spec(self):
        pass

    @abstractmethod
    def get_properties(self):
        pass

    @abstractmethod
    def get_icon(self):
        pass

    @abstractmethod
    def get_variables(self):
        pass

    @abstractmethod
    def run_container(
        self,
        organization_id,
        workflow_id,
        execution_id,
        settings,
        envs,
        messaging_channel,
    ):
        pass

    @abstractmethod
    def get_container_run_config(
        self, organization_id, workflow_id, execution_id, settings, envs
    ):
        pass

    @abstractmethod
    def _cleanup_container(self, container):
        pass
