"""Resource-type mapping shared between the direct-share and group-share
notification paths, so a new adapter or pipeline type only needs registering
once.
"""

from __future__ import annotations


def adapter_notification_type(adapter_type: str) -> str:
    """Map an ``AdapterInstance.adapter_type`` to the plugin's ``ResourceType``.

    Unknown types fall back to ``LLM`` so a newly added adapter kind still
    mails rather than silently going quiet.
    """
    from plugins.notification.constants import ResourceType

    return {
        "LLM": ResourceType.LLM.value,
        "EMBEDDING": ResourceType.EMBEDDING.value,
        "VECTOR_DB": ResourceType.VECTOR_DB.value,
        "X2TEXT": ResourceType.X2TEXT.value,
    }.get(adapter_type, ResourceType.LLM.value)


def pipeline_notification_type(pipeline_type: str | None) -> str | None:
    """Map a ``Pipeline.pipeline_type`` to the plugin's ``ResourceType``.

    Only ETL/TASK pipelines are notifiable; anything else returns ``None``.
    """
    from plugins.notification.constants import ResourceType

    if pipeline_type in (ResourceType.ETL.value, ResourceType.TASK.value):
        return pipeline_type
    return None
