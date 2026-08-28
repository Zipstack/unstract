from unstract.filesystem.file_storage_config import (
    FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING, STORAGE_MAPPING,
)
from unstract.filesystem.file_storage_types import FileStorageType


def test_agent_kv_type_exists_and_is_mapped():
    t = FileStorageType.AGENT_KV
    assert t.value == "AGENT_KV"
    assert t in STORAGE_MAPPING
    assert (
        FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING[t]
        == "AGENT_KV_FILE_STORAGE_CREDENTIALS"
    )
