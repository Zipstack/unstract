from pathlib import Path

from workflow_manager.endpoint.constants import UnstractFSConnector


class UnstractFsConnectorHelper:

    @staticmethod
    def get_fs_root_dir(fs_cls_name: str, root_path: str, input_dir: str) -> str:
        if fs_cls_name in UnstractFSConnector.GOOGLE_DRIVE_FS:
            input_dir = str(Path(root_path, input_dir.lstrip("/")))
            return f"{input_dir.strip('/')}/"
        elif fs_cls_name in UnstractFSConnector.DROPBOX_FS:
            return f"/{input_dir.strip('/')}"
        else:
            return f"{input_dir.strip('/')}/"
